import aiosqlite
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules
from app.services.signals.base import BaseSignal


class VelocitySignal(BaseSignal):
    """
    Counts how many transactions the same user has submitted in a rolling
    time window. High velocity indicates a scripted fraud attack.
    """

    @property
    def signal_name(self) -> str:
        return "velocity"

    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        rule = rules.velocity
        if not rule.enabled:
            return SignalResult(signal=self.signal_name, triggered=False, score_contribution=0,
                                description="Velocity check disabled")

        window_start = (
            tx.timestamp.replace(tzinfo=None)
            if tx.timestamp.tzinfo
            else tx.timestamp
        )
        # Compute window start as ISO string
        from datetime import timedelta
        window_dt = tx.timestamp.replace(tzinfo=None) - timedelta(minutes=rule.time_window_minutes)
        window_str = window_dt.isoformat()

        async with db.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ?
              AND timestamp > ?
              AND id != ?
            """,
            (tx.user_id, window_str, tx.transaction_id),
        ) as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0

        # The current transaction would be count+1 total in the window.
        # Only flag if that would exceed the limit.
        if count + 1 <= rule.max_transactions:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Velocity OK: {count + 1} transactions in last {rule.time_window_minutes} min (limit: {rule.max_transactions})",
                details={"transaction_count": count + 1, "window_minutes": rule.time_window_minutes, "limit": rule.max_transactions},
            )

        # excess = how many over the limit (including current transaction)
        excess = (count + 1) - rule.max_transactions
        # Score ramp: 1 over = 85% (REVIEW), 2+ over = 100% (BLOCK)
        ratio = min(1.0, 0.55 + excess * 0.30)
        score = round(rule.max_score * ratio, 1)

        return SignalResult(
            signal=self.signal_name,
            triggered=True,
            score_contribution=score,
            description=f"High velocity: {count + 1} transactions in last {rule.time_window_minutes} min (limit: {rule.max_transactions})",
            details={"transaction_count": count + 1, "window_minutes": rule.time_window_minutes, "limit": rule.max_transactions, "excess": excess},
        )
