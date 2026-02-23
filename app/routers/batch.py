import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.db import get_db
from app.models.risk import BatchRescoreRequest, BatchRescoreResult
from app.models.transaction import PayoutRequest
from app.services import risk_engine

router = APIRouter()


class BatchRescoreResponse(BaseModel):
    rescored_count: int
    updated_in_db: bool
    results: List[BatchRescoreResult]
    summary: dict


@router.post(
    "/rescore",
    response_model=BatchRescoreResponse,
    summary="Batch re-score historical transactions",
    description="""
Re-evaluate historical transactions against the **current** risk rules.

Useful after updating merchant rules to see how the new thresholds would have
affected past decisions (e.g., "would tighter velocity rules have caught the
RideFleet fraud weekend?").

**Selection:**
- Provide `transaction_ids` for a specific list, OR
- Provide `start_date` / `end_date` (ISO format) to select a date range
- `merchant_id` is always required

**Updating scores:**
Set `update_scores: true` to overwrite the stored risk_score / action for each
transaction with the newly computed values.
""",
)
async def batch_rescore(req: BatchRescoreRequest) -> BatchRescoreResponse:
    db = await get_db()
    try:
        # Build query
        if req.transaction_ids:
            placeholders = ",".join("?" * len(req.transaction_ids))
            query = f"""
                SELECT id, merchant_id, user_id, recipient_account, recipient_email,
                       recipient_phone, amount, currency, user_ip, device_id,
                       user_country, ip_country, account_created_at, timestamp,
                       risk_score, action
                FROM transactions
                WHERE merchant_id = ? AND id IN ({placeholders})
            """
            params: list = [req.merchant_id] + list(req.transaction_ids)
        elif req.start_date or req.end_date:
            query = """
                SELECT id, merchant_id, user_id, recipient_account, recipient_email,
                       recipient_phone, amount, currency, user_ip, device_id,
                       user_country, ip_country, account_created_at, timestamp,
                       risk_score, action
                FROM transactions
                WHERE merchant_id = ?
            """
            params = [req.merchant_id]
            if req.start_date:
                query += " AND timestamp >= ?"
                params.append(req.start_date)
            if req.end_date:
                query += " AND timestamp <= ?"
                params.append(req.end_date)
            query += " ORDER BY timestamp"
        else:
            raise HTTPException(
                status_code=422,
                detail="Provide either transaction_ids or start_date/end_date",
            )

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return BatchRescoreResponse(
                rescored_count=0, updated_in_db=False, results=[],
                summary={"total": 0, "approve": 0, "review": 0, "block": 0}
            )

        results: list[BatchRescoreResult] = []
        summary = {"total": 0, "approve": 0, "review": 0, "block": 0, "changed": 0}

        for row in rows:
            row_dict = dict(row)
            old_score = row_dict.get("risk_score")
            old_action = row_dict.get("action")

            # Reconstruct PayoutRequest from stored row
            tx_data = {
                "transaction_id": row_dict["id"],
                "merchant_id": row_dict["merchant_id"],
                "user_id": row_dict["user_id"],
                "recipient_account": row_dict["recipient_account"],
                "recipient_email": row_dict.get("recipient_email"),
                "recipient_phone": row_dict.get("recipient_phone"),
                "amount": row_dict["amount"],
                "currency": row_dict["currency"],
                "user_ip": row_dict.get("user_ip"),
                "device_id": row_dict.get("device_id"),
                "user_country": row_dict.get("user_country"),
                "ip_country": row_dict.get("ip_country"),
                "account_created_at": row_dict.get("account_created_at"),
                "timestamp": row_dict["timestamp"],
            }
            tx = PayoutRequest(**tx_data)

            assessment = await risk_engine.score_transaction(tx, db)
            new_score = assessment.risk_score
            new_action = assessment.action

            delta = round(new_score - old_score, 1) if old_score is not None else None

            results.append(BatchRescoreResult(
                transaction_id=tx.transaction_id,
                old_score=old_score,
                old_action=old_action,
                new_score=new_score,
                new_risk_level=assessment.risk_level,
                new_action=new_action,
                score_delta=delta,
            ))

            summary["total"] += 1
            summary[new_action.lower()] += 1
            if old_action and old_action != new_action:
                summary["changed"] += 1

        if req.update_scores:
            for result in results:
                await db.execute(
                    """
                    UPDATE transactions
                    SET risk_score = ?, risk_level = ?, action = ?
                    WHERE id = ? AND merchant_id = ?
                    """,
                    (result.new_score, result.new_risk_level,
                     result.new_action, result.transaction_id, req.merchant_id),
                )
            await db.commit()

        return BatchRescoreResponse(
            rescored_count=len(results),
            updated_in_db=req.update_scores,
            results=results,
            summary=summary,
        )
    finally:
        await db.close()
