import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database.db import get_db

router = APIRouter()


class AuditRecord(BaseModel):
    id: int
    transaction_id: str
    merchant_id: str
    risk_score: float
    risk_level: str
    action: str
    signals: list
    processing_time_ms: float
    evaluated_at: str


class AuditDetail(AuditRecord):
    request: dict
    rules_snapshot: dict


@router.get(
    "/",
    response_model=List[AuditRecord],
    summary="List recent audit log entries",
)
async def list_audit(
    merchant_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None, description="Filter by action: APPROVE, REVIEW, BLOCK"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    db = await get_db()
    try:
        query = """
            SELECT id, transaction_id, merchant_id, risk_score, risk_level,
                   action, signals_json, processing_time_ms, evaluated_at
            FROM risk_audit WHERE 1=1
        """
        params: list = []
        if merchant_id:
            query += " AND merchant_id = ?"
            params.append(merchant_id)
        if action:
            query += " AND action = ?"
            params.append(action.upper())
        query += " ORDER BY evaluated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "id": r["id"],
                "transaction_id": r["transaction_id"],
                "merchant_id": r["merchant_id"],
                "risk_score": r["risk_score"],
                "risk_level": r["risk_level"],
                "action": r["action"],
                "signals": json.loads(r["signals_json"]),
                "processing_time_ms": r["processing_time_ms"],
                "evaluated_at": r["evaluated_at"],
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.get(
    "/{transaction_id}",
    response_model=AuditDetail,
    summary="Get full audit detail for a specific transaction",
)
async def get_audit(transaction_id: str):
    db = await get_db()
    try:
        async with db.execute(
            """
            SELECT id, transaction_id, merchant_id, request_json, risk_score, risk_level,
                   action, signals_json, rules_json, processing_time_ms, evaluated_at
            FROM risk_audit WHERE transaction_id = ?
            ORDER BY evaluated_at DESC LIMIT 1
            """,
            (transaction_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"No audit record for transaction {transaction_id!r}")

        return {
            "id": row["id"],
            "transaction_id": row["transaction_id"],
            "merchant_id": row["merchant_id"],
            "risk_score": row["risk_score"],
            "risk_level": row["risk_level"],
            "action": row["action"],
            "signals": json.loads(row["signals_json"]),
            "processing_time_ms": row["processing_time_ms"],
            "evaluated_at": row["evaluated_at"],
            "request": json.loads(row["request_json"]),
            "rules_snapshot": json.loads(row["rules_json"]),
        }
    finally:
        await db.close()
