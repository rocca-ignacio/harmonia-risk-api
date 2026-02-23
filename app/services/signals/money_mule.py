import aiosqlite
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules
from app.services.signals.base import BaseSignal


class MoneyMuleSignal(BaseSignal):
    """
    Detects recipient accounts that receive payouts from many different merchants.
    Legitimate recipients (like a contractor) may use a few platforms, but receiving
    from many unrelated merchants is a classic money mule indicator.
    """

    @property
    def signal_name(self) -> str:
        return "money_mule"

    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        rule = rules.money_mule
        if not rule.enabled:
            return SignalResult(signal=self.signal_name, triggered=False, score_contribution=0,
                                description="Money mule check disabled")

        # Collect distinct merchants from history, then include the current one
        all_merchants = set()
        async with db.execute(
            "SELECT DISTINCT merchant_id FROM transactions WHERE recipient_account = ?",
            (tx.recipient_account,),
        ) as cursor:
            async for r in cursor:
                all_merchants.add(r[0])
        all_merchants.add(tx.merchant_id)
        total_merchants = len(all_merchants)

        if total_merchants < rule.min_merchant_count:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Recipient seen across {total_merchants} merchant(s) — within normal range",
                details={"merchant_count": total_merchants, "threshold": rule.min_merchant_count,
                         "recipient_account": tx.recipient_account},
            )

        # Score scales with merchant count beyond threshold
        excess = total_merchants - rule.min_merchant_count
        ratio = min(1.0, 0.5 + excess * 0.25)
        score = round(rule.max_score * ratio, 1)

        return SignalResult(
            signal=self.signal_name,
            triggered=True,
            score_contribution=score,
            description=f"Money mule indicator: recipient account has received from {total_merchants} distinct merchants",
            details={"merchant_count": total_merchants, "threshold": rule.min_merchant_count,
                     "recipient_account": tx.recipient_account},
        )
