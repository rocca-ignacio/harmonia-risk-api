import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Literal

import aiosqlite

from app.config import settings
from app.models.risk import RiskAssessment, SignalResult
from app.models.transaction import PayoutRequest
from app.services import blocklist_service, rules_service
from app.services.signals.velocity import VelocitySignal
from app.services.signals.amount_anomaly import AmountAnomalySignal
from app.services.signals.geo_mismatch import GeoMismatchSignal
from app.services.signals.new_account import NewAccountSignal
from app.services.signals.money_mule import MoneyMuleSignal
from app.services.signals.time_of_day import TimeOfDaySignal

# All active signal evaluators — order matters for readability in output
SIGNALS = [
    VelocitySignal(),
    AmountAnomalySignal(),
    GeoMismatchSignal(),
    NewAccountSignal(),
    MoneyMuleSignal(),
    TimeOfDaySignal(),
]


def _determine_level_action(
    score: float, low_max: int, medium_max: int
) -> tuple[str, str]:
    if score <= low_max:
        return "LOW", "APPROVE"
    elif score <= medium_max:
        return "MEDIUM", "REVIEW"
    else:
        return "HIGH", "BLOCK"


async def score_transaction(tx: PayoutRequest, db: aiosqlite.Connection) -> RiskAssessment:
    """
    Core risk scoring pipeline:
    1. Check allowlist → auto-APPROVE if found
    2. Check blocklist → auto-BLOCK if found
    3. Check max payout rule → auto-BLOCK if exceeded
    4. Run all fraud signals
    5. Sum contributions (capped at 100)
    6. Persist result and audit log
    7. Return RiskAssessment
    """
    start = time.monotonic()
    evaluated_at = datetime.now(timezone.utc)

    rules = await rules_service.get_merchant_rules(tx.merchant_id, db)
    signals_out: list[SignalResult] = []

    # ── 1. Allowlist check ────────────────────────────────────────────────────
    if rules.allowlist_auto_approve:
        is_allowed, allow_reason = await blocklist_service.is_allowlisted(tx, db)
        if is_allowed:
            signals_out.append(SignalResult(
                signal="allowlist",
                triggered=True,
                score_contribution=0,
                description=f"Recipient is on merchant allowlist — auto-approved: {allow_reason}",
            ))
            ms = (time.monotonic() - start) * 1000
            assessment = RiskAssessment(
                transaction_id=tx.transaction_id,
                merchant_id=tx.merchant_id,
                risk_score=0.0,
                risk_level="LOW",
                action="APPROVE",
                signals=signals_out,
                processing_time_ms=round(ms, 2),
                evaluated_at=evaluated_at,
            )
            await _persist(tx, assessment, rules.model_dump_json(), db)
            return assessment

    # ── 2. Blocklist check ────────────────────────────────────────────────────
    is_blocked, block_reason = await blocklist_service.is_blocklisted(tx, db)
    if is_blocked:
        signals_out.append(SignalResult(
            signal="blocklist",
            triggered=True,
            score_contribution=100,
            description=block_reason,
        ))
        ms = (time.monotonic() - start) * 1000
        assessment = RiskAssessment(
            transaction_id=tx.transaction_id,
            merchant_id=tx.merchant_id,
            risk_score=100.0,
            risk_level="HIGH",
            action="BLOCK",
            signals=signals_out,
            processing_time_ms=round(ms, 2),
            evaluated_at=evaluated_at,
        )
        await _persist(tx, assessment, rules.model_dump_json(), db)
        return assessment

    # ── 3. Max payout hard cap ────────────────────────────────────────────────
    if rules.max_payout.enabled and tx.amount > rules.max_payout.max_amount:
        signals_out.append(SignalResult(
            signal="max_payout",
            triggered=True,
            score_contribution=100,
            description=f"Amount ${tx.amount:.2f} exceeds merchant maximum ${rules.max_payout.max_amount:.2f}",
            details={"amount": tx.amount, "max_allowed": rules.max_payout.max_amount},
        ))
        ms = (time.monotonic() - start) * 1000
        assessment = RiskAssessment(
            transaction_id=tx.transaction_id,
            merchant_id=tx.merchant_id,
            risk_score=100.0,
            risk_level="HIGH",
            action="BLOCK",
            signals=signals_out,
            processing_time_ms=round(ms, 2),
            evaluated_at=evaluated_at,
        )
        await _persist(tx, assessment, rules.model_dump_json(), db)
        return assessment

    # ── 4. Run all fraud signals ──────────────────────────────────────────────
    for signal in SIGNALS:
        try:
            result = await asyncio.wait_for(
                signal.evaluate(tx, rules, db),
                timeout=settings.SIGNAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            result = SignalResult(
                signal=signal.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Signal timed out after {settings.SIGNAL_TIMEOUT_SECONDS}s — scored as 0",
            )
        signals_out.append(result)

    # ── 5. Composite score (capped at 100) ────────────────────────────────────
    total_score = min(100.0, sum(s.score_contribution for s in signals_out))
    total_score = round(total_score, 1)

    thresholds = rules.score_thresholds
    risk_level, action = _determine_level_action(total_score, thresholds.low_max, thresholds.medium_max)

    ms = (time.monotonic() - start) * 1000
    assessment = RiskAssessment(
        transaction_id=tx.transaction_id,
        merchant_id=tx.merchant_id,
        risk_score=total_score,
        risk_level=risk_level,
        action=action,
        signals=signals_out,
        processing_time_ms=round(ms, 2),
        evaluated_at=evaluated_at,
    )

    await _persist(tx, assessment, rules.model_dump_json(), db)
    return assessment


async def _persist(
    tx: PayoutRequest,
    assessment: RiskAssessment,
    rules_json: str,
    db: aiosqlite.Connection,
) -> None:
    """Store the transaction and audit log entry."""
    ts_str = tx.timestamp.replace(tzinfo=None).isoformat() if tx.timestamp.tzinfo else tx.timestamp.isoformat()
    acct_str = tx.account_created_at.replace(tzinfo=None).isoformat() if tx.account_created_at and tx.account_created_at.tzinfo else (tx.account_created_at.isoformat() if tx.account_created_at else None)

    await db.execute(
        """
        INSERT INTO transactions
          (id, merchant_id, user_id, recipient_account, recipient_email,
           recipient_phone, amount, currency, user_ip, device_id,
           user_country, ip_country, account_created_at, timestamp,
           risk_score, risk_level, action)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          risk_score = excluded.risk_score,
          risk_level = excluded.risk_level,
          action = excluded.action
        """,
        (
            tx.transaction_id, tx.merchant_id, tx.user_id,
            tx.recipient_account, tx.recipient_email, tx.recipient_phone,
            tx.amount, tx.currency, tx.user_ip, tx.device_id,
            tx.user_country, tx.ip_country, acct_str, ts_str,
            assessment.risk_score, assessment.risk_level, assessment.action,
        ),
    )

    signals_json = json.dumps([s.model_dump() for s in assessment.signals])

    await db.execute(
        """
        INSERT INTO risk_audit
          (transaction_id, merchant_id, request_json, risk_score, risk_level,
           action, signals_json, rules_json, processing_time_ms, evaluated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            tx.transaction_id, tx.merchant_id,
            tx.model_dump_json(),
            assessment.risk_score, assessment.risk_level, assessment.action,
            signals_json, rules_json,
            assessment.processing_time_ms,
            assessment.evaluated_at.isoformat(),
        ),
    )
    await db.commit()
