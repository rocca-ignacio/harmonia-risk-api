import aiosqlite
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules
from app.services.signals.base import BaseSignal


class TimeOfDaySignal(BaseSignal):
    """
    Flags transactions submitted during unusual hours (e.g., 12am–5am UTC).
    While not conclusive on its own, late-night activity combined with other
    signals is a meaningful fraud indicator.
    """

    @property
    def signal_name(self) -> str:
        return "time_of_day"

    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        rule = rules.time_of_day
        if not rule.enabled:
            return SignalResult(signal=self.signal_name, triggered=False, score_contribution=0,
                                description="Time-of-day check disabled")

        hour = tx.timestamp.hour

        if hour not in rule.suspicious_hours:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Transaction at {hour:02d}:00 UTC — within normal hours",
                details={"hour_utc": hour},
            )

        return SignalResult(
            signal=self.signal_name,
            triggered=True,
            score_contribution=float(rule.max_score),
            description=f"Transaction at {hour:02d}:00 UTC — outside normal business hours",
            details={"hour_utc": hour, "suspicious_hours": rule.suspicious_hours},
        )
