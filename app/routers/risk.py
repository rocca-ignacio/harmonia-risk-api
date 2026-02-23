from fastapi import APIRouter, HTTPException
from app.database.db import get_db
from app.models.transaction import PayoutRequest
from app.models.risk import RiskAssessment
from app.services import risk_engine

router = APIRouter()


@router.post(
    "/score",
    response_model=RiskAssessment,
    summary="Score a payout transaction",
    description="""
Evaluate a payout request and return a real-time risk assessment.

The engine checks (in order):
1. **Allowlist** — auto-APPROVE trusted recipients
2. **Blocklist** — auto-BLOCK known fraud identifiers
3. **Max payout cap** — BLOCK if amount exceeds merchant limit
4. **Velocity** — penalise bursts of transactions from the same user
5. **Amount anomaly** — flag amounts far above the user's historical average
6. **Geographic mismatch** — flag IP country vs account country discrepancy
7. **New account** — penalise large payouts from recently created accounts
8. **Money mule** — flag recipients receiving from many different merchants
9. **Time of day** — add soft penalty for late-night transactions

Final score is the sum of all signal contributions, capped at 100.

| Score range | Risk level | Action  |
|-------------|------------|---------|
| 0–30        | LOW        | APPROVE |
| 31–60       | MEDIUM     | REVIEW  |
| 61–100      | HIGH       | BLOCK   |

Thresholds are configurable per merchant via `PUT /api/v1/rules/{merchant_id}`.
""",
)
async def score_transaction(tx: PayoutRequest) -> RiskAssessment:
    db = await get_db()
    try:
        return await risk_engine.score_transaction(tx, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await db.close()
