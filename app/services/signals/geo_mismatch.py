import aiosqlite
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules
from app.services.signals.base import BaseSignal


class GeoMismatchSignal(BaseSignal):
    """
    Detects when the IP country differs from the user's registered account country.
    A user who normally transacts from the Philippines suddenly appearing from Nigeria
    is a strong fraud indicator.
    """

    @property
    def signal_name(self) -> str:
        return "geo_mismatch"

    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        rule = rules.geo_mismatch
        if not rule.enabled:
            return SignalResult(signal=self.signal_name, triggered=False, score_contribution=0,
                                description="Geo mismatch check disabled")

        if not tx.user_country or not tx.ip_country:
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description="Insufficient location data to evaluate",
                details={"user_country": tx.user_country, "ip_country": tx.ip_country},
            )

        if tx.user_country.upper() == tx.ip_country.upper():
            return SignalResult(
                signal=self.signal_name,
                triggered=False,
                score_contribution=0,
                description=f"Location consistent: user country {tx.user_country} matches IP country {tx.ip_country}",
                details={"user_country": tx.user_country, "ip_country": tx.ip_country},
            )

        # Check if this user has any prior transactions from the IP country
        # (could be a legitimate traveler)
        async with db.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ?
              AND ip_country = ?
              AND id != ?
            """,
            (tx.user_id, tx.ip_country, tx.transaction_id),
        ) as cursor:
            row = await cursor.fetchone()
            prior_from_ip_country = row[0] if row else 0

        if prior_from_ip_country > 0:
            # Known travel pattern — reduce score
            score = round(rule.max_score * 0.4, 1)
            return SignalResult(
                signal=self.signal_name,
                triggered=True,
                score_contribution=score,
                description=f"Location mismatch: account from {tx.user_country}, IP from {tx.ip_country} (seen {prior_from_ip_country}x before — possible travel)",
                details={"user_country": tx.user_country, "ip_country": tx.ip_country,
                         "prior_from_ip_country": prior_from_ip_country},
            )

        return SignalResult(
            signal=self.signal_name,
            triggered=True,
            score_contribution=float(rule.max_score),
            description=f"Geographic anomaly: account from {tx.user_country}, IP from {tx.ip_country} — never seen before",
            details={"user_country": tx.user_country, "ip_country": tx.ip_country,
                     "prior_from_ip_country": 0},
        )
