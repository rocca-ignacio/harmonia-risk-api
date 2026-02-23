import aiosqlite
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules
from app.services.signals.base import BaseSignal


class AmountAnomalySignal(BaseSignal):
    """
    Compares the current payout amount to the user's historical average.
    A sudden spike far above baseline strongly indicates fraud.
    """

    @property
    def signal_name(self) -> str:
        return "amount_anomaly"

    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        rule = rules.amount_anomaly
        if not rule.enabled:
            return SignalResult(signal=self.signal_name, triggered=False, score_contribution=0,
                                description="Amount anomaly check disabled")

        async with db.execute(
            """
            SELECT AVG(amount) AS avg_amount, COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ?
              AND merchant_id = ?
              AND id != ?
            """,
            (tx.user_id, tx.merchant_id, tx.transaction_id),
        ) as cursor:
            row = await cursor.fetchone()
            avg_amount = row[0]
            history_count = row[1] if row else 0

        if history_count is None:
            history_count = 0

        # Not enough history — check against absolute threshold
        if history_count < rule.min_history_count or avg_amount is None or avg_amount == 0:
            if tx.amount > rule.no_history_large_amount:
                score = round(rule.max_score * 0.6, 1)
                return SignalResult(
                    signal=self.signal_name,
                    triggered=True,
                    score_contribution=score,
                    description=f"Large amount (${tx.amount:.2f}) with no established history",
                    details={"current_amount": tx.amount, "history_count": history_count,
                             "no_history_threshold": rule.no_history_large_amount},
                )
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Insufficient history ({history_count} transactions) to establish baseline",
                details={"history_count": history_count, "min_required": rule.min_history_count},
            )

        multiplier = tx.amount / avg_amount
        if multiplier < rule.threshold_multiplier:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Amount ${tx.amount:.2f} is {multiplier:.1f}x user average ${avg_amount:.2f} — within threshold",
                details={"current_amount": tx.amount, "user_avg": round(avg_amount, 2), "multiplier": round(multiplier, 2)},
            )

        # Score: 3x = 40%, 5x = 70%, 8x+ = 100%
        excess_ratio = (multiplier - rule.threshold_multiplier) / (8.0 - rule.threshold_multiplier)
        ratio = min(1.0, 0.4 + excess_ratio * 0.6)
        score = round(rule.max_score * ratio, 1)

        return SignalResult(
            signal=self.signal_name,
            triggered=True,
            score_contribution=score,
            description=f"Amount ${tx.amount:.2f} is {multiplier:.1f}x above user average ${avg_amount:.2f} (threshold: {rule.threshold_multiplier}x)",
            details={"current_amount": tx.amount, "user_avg": round(avg_amount, 2),
                     "multiplier": round(multiplier, 2), "threshold": rule.threshold_multiplier},
        )
