import json
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.database.db import get_db

router = APIRouter()


# ── Response models ────────────────────────────────────────────────────────────

class ActionCounts(BaseModel):
    APPROVE: int
    REVIEW: int
    BLOCK: int


class MerchantSummary(BaseModel):
    merchant_id: str
    start_date: Optional[str]
    end_date: Optional[str]
    total_transactions: int
    by_action: ActionCounts
    by_action_pct: dict
    avg_risk_score: float
    avg_processing_time_ms: float


class SignalStat(BaseModel):
    signal: str
    triggered_count: int
    trigger_rate_pct: float
    avg_contribution_when_triggered: float


class SignalFrequency(BaseModel):
    merchant_id: str
    total_transactions: int
    signals: list[SignalStat]


class TrendPoint(BaseModel):
    period: str
    count: int
    avg_score: float
    approve: int
    review: int
    block: int


class TrendData(BaseModel):
    merchant_id: str
    interval: str
    data: list[TrendPoint]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/summary",
    response_model=MerchantSummary,
    summary="Transaction summary for a merchant",
    description="Aggregate action counts, percentages, average risk score, and average processing time over an optional date range.",
)
async def get_summary(
    merchant_id: str = Query(...),
    start_date: Optional[str] = Query(None, description="ISO datetime, inclusive"),
    end_date: Optional[str] = Query(None, description="ISO datetime, inclusive"),
):
    db = await get_db()
    try:
        query = "SELECT risk_score, action, processing_time_ms FROM risk_audit WHERE merchant_id = ?"
        params: list = [merchant_id]
        if start_date:
            query += " AND evaluated_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND evaluated_at <= ?"
            params.append(end_date)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        total = len(rows)
        if total == 0:
            return MerchantSummary(
                merchant_id=merchant_id, start_date=start_date, end_date=end_date,
                total_transactions=0,
                by_action=ActionCounts(APPROVE=0, REVIEW=0, BLOCK=0),
                by_action_pct={"APPROVE": 0.0, "REVIEW": 0.0, "BLOCK": 0.0},
                avg_risk_score=0.0, avg_processing_time_ms=0.0,
            )

        counts = {"APPROVE": 0, "REVIEW": 0, "BLOCK": 0}
        total_score = 0.0
        total_time = 0.0
        for row in rows:
            counts[row[1]] = counts.get(row[1], 0) + 1
            total_score += row[0] or 0.0
            total_time += row[2] or 0.0

        return MerchantSummary(
            merchant_id=merchant_id,
            start_date=start_date,
            end_date=end_date,
            total_transactions=total,
            by_action=ActionCounts(**counts),
            by_action_pct={k: round(v / total * 100, 1) for k, v in counts.items()},
            avg_risk_score=round(total_score / total, 1),
            avg_processing_time_ms=round(total_time / total, 2),
        )
    finally:
        await db.close()


@router.get(
    "/signals",
    response_model=SignalFrequency,
    summary="Signal trigger frequency for a merchant",
    description="Shows how often each fraud signal fires, its trigger rate, and average score contribution — useful for tuning thresholds.",
)
async def get_signal_frequency(
    merchant_id: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    db = await get_db()
    try:
        query = "SELECT signals_json FROM risk_audit WHERE merchant_id = ?"
        params: list = [merchant_id]
        if start_date:
            query += " AND evaluated_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND evaluated_at <= ?"
            params.append(end_date)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        total = len(rows)
        stats: dict[str, dict] = {}
        for row in rows:
            for s in json.loads(row[0]):
                name = s["signal"]
                if name not in stats:
                    stats[name] = {"triggered": 0, "total_contribution": 0.0}
                if s.get("triggered"):
                    stats[name]["triggered"] += 1
                    stats[name]["total_contribution"] += s.get("score_contribution", 0.0)

        signals = [
            SignalStat(
                signal=name,
                triggered_count=d["triggered"],
                trigger_rate_pct=round(d["triggered"] / total * 100, 1) if total else 0.0,
                avg_contribution_when_triggered=round(
                    d["total_contribution"] / d["triggered"], 1
                ) if d["triggered"] else 0.0,
            )
            for name, d in sorted(stats.items(), key=lambda x: -x[1]["triggered"])
        ]
        return SignalFrequency(merchant_id=merchant_id, total_transactions=total, signals=signals)
    finally:
        await db.close()


@router.get(
    "/trends",
    response_model=TrendData,
    summary="Risk score trends over time",
    description="Groups transactions by day or hour, returning count, average score, and action breakdown per period.",
)
async def get_trends(
    merchant_id: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval: str = Query("day", pattern="^(day|hour)$", description="Grouping interval: 'day' or 'hour'"),
):
    db = await get_db()
    try:
        fmt = "%Y-%m-%d" if interval == "day" else "%Y-%m-%dT%H"
        query = f"""
            SELECT strftime('{fmt}', evaluated_at) AS period,
                   COUNT(*) AS cnt,
                   AVG(risk_score) AS avg_score,
                   SUM(CASE WHEN action = 'APPROVE' THEN 1 ELSE 0 END) AS approve,
                   SUM(CASE WHEN action = 'REVIEW'  THEN 1 ELSE 0 END) AS review,
                   SUM(CASE WHEN action = 'BLOCK'   THEN 1 ELSE 0 END) AS block
            FROM risk_audit
            WHERE merchant_id = ?
        """
        params: list = [merchant_id]
        if start_date:
            query += " AND evaluated_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND evaluated_at <= ?"
            params.append(end_date)
        query += " GROUP BY period ORDER BY period"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return TrendData(
            merchant_id=merchant_id,
            interval=interval,
            data=[
                TrendPoint(
                    period=row[0], count=row[1],
                    avg_score=round(row[2] or 0.0, 1),
                    approve=row[3], review=row[4], block=row[5],
                )
                for row in rows
            ],
        )
    finally:
        await db.close()
