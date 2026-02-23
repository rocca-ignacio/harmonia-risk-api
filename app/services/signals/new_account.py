import aiosqlite
from datetime import datetime, timezone
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules
from app.services.signals.base import BaseSignal


class NewAccountSignal(BaseSignal):
    """
    Flags large payouts from recently created accounts.
    Fraudsters often spin up fresh accounts and immediately attempt large payouts.
    """

    @property
    def signal_name(self) -> str:
        return "new_account"

    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        rule = rules.new_account
        if not rule.enabled:
            return SignalResult(signal=self.signal_name, triggered=False, score_contribution=0,
                                description="New account check disabled")

        if not tx.account_created_at:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description="Account creation date not provided",
            )

        # Normalize to offset-naive UTC
        created = tx.account_created_at.replace(tzinfo=None) if tx.account_created_at.tzinfo else tx.account_created_at
        now = tx.timestamp.replace(tzinfo=None) if tx.timestamp.tzinfo else tx.timestamp
        age_days = (now - created).days

        if age_days >= rule.new_account_days:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Account is {age_days} days old — established",
                details={"account_age_days": age_days, "threshold_days": rule.new_account_days},
            )

        # New account — check amount
        if tx.amount < rule.suspicious_amount:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"New account ({age_days} days) but amount ${tx.amount:.2f} below threshold ${rule.suspicious_amount:.2f}",
                details={"account_age_days": age_days, "amount": tx.amount, "threshold": rule.suspicious_amount},
            )

        # New account + large amount: score scales with age (younger = higher risk)
        age_ratio = 1.0 - (age_days / rule.new_account_days)  # 0 days old = 1.0, almost-threshold = near 0
        score = round(rule.max_score * max(0.5, age_ratio), 1)

        return SignalResult(
            signal=self.signal_name,
            triggered=True,
            score_contribution=score,
            description=f"New account ({age_days} days old) requesting large payout of ${tx.amount:.2f}",
            details={"account_age_days": age_days, "amount": tx.amount,
                     "threshold_days": rule.new_account_days, "threshold_amount": rule.suspicious_amount},
        )
