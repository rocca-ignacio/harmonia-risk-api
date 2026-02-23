from fastapi import APIRouter, HTTPException
from app.database.db import get_db
from app.models.rules import MerchantRules
from app.services import rules_service

router = APIRouter()


@router.get(
    "/{merchant_id}",
    response_model=MerchantRules,
    summary="Get risk rules for a merchant",
)
async def get_rules(merchant_id: str) -> MerchantRules:
    db = await get_db()
    try:
        return await rules_service.get_merchant_rules(merchant_id, db)
    finally:
        await db.close()


@router.put(
    "/{merchant_id}",
    response_model=MerchantRules,
    summary="Create or update risk rules for a merchant",
    description="""
Update the configurable risk rules for a merchant. Changes take effect immediately
(the in-memory cache is invalidated on save).

**Example rule changes:**
- Tighten velocity: reduce `velocity.max_transactions` from 5 to 3
- Raise block threshold: increase `score_thresholds.medium_max` from 60 to 70
- Disable geo check: set `geo_mismatch.enabled` to false
- Set a hard payout cap: set `max_payout.max_amount` to 500.0
""",
)
async def upsert_rules(merchant_id: str, rules: MerchantRules) -> MerchantRules:
    if rules.merchant_id != merchant_id:
        raise HTTPException(
            status_code=422,
            detail=f"merchant_id in body ({rules.merchant_id}) must match path ({merchant_id})",
        )
    db = await get_db()
    try:
        await rules_service.upsert_merchant_rules(merchant_id, rules, db)
        return rules
    finally:
        await db.close()
