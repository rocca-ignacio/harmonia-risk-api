from pydantic import BaseModel, Field
from typing import List, Optional


class VelocityRule(BaseModel):
    """Detect too many transactions in a short time window."""
    enabled: bool = True
    max_transactions: int = Field(5, description="Max allowed transactions in the window")
    time_window_minutes: int = Field(10, description="Time window in minutes")
    max_score: int = Field(65, description="Max score contribution (0-100)")


class AmountAnomalyRule(BaseModel):
    """Detect transaction amounts abnormally high vs user's history."""
    enabled: bool = True
    threshold_multiplier: float = Field(3.0, description="Flag if amount > X * user's average")
    min_history_count: int = Field(3, description="Minimum transactions needed to establish a baseline")
    no_history_large_amount: float = Field(500.0, description="Flag if no history and amount exceeds this")
    max_score: int = Field(65, description="Max score contribution (0-100)")


class GeoMismatchRule(BaseModel):
    """Detect geographic anomalies between account country and IP country."""
    enabled: bool = True
    max_score: int = Field(50, description="Max score contribution (0-100)")


class NewAccountRule(BaseModel):
    """Detect high-risk payouts from newly created accounts."""
    enabled: bool = True
    new_account_days: int = Field(7, description="Account younger than X days is considered new")
    suspicious_amount: float = Field(200.0, description="Trigger if new account AND amount exceeds this")
    max_score: int = Field(30, description="Max score contribution (0-100)")


class MoneyMuleRule(BaseModel):
    """Detect recipients receiving payouts from many different merchants (money mule indicator)."""
    enabled: bool = True
    min_merchant_count: int = Field(3, description="Flag if recipient received from >= X distinct merchants")
    max_score: int = Field(40, description="Max score contribution (0-100)")


class TimeOfDayRule(BaseModel):
    """Detect transactions at unusual hours."""
    enabled: bool = True
    suspicious_hours: List[int] = Field(
        default=[0, 1, 2, 3, 4, 5],
        description="UTC hours considered suspicious"
    )
    max_score: int = Field(10, description="Max score contribution (0-100)")


class MaxPayoutRule(BaseModel):
    """Hard cap on payout amount — auto-blocks if exceeded."""
    enabled: bool = True
    max_amount: float = Field(10000.0, description="Maximum allowed payout amount")


class ScoreThresholds(BaseModel):
    """Define score bands for risk levels."""
    low_max: int = Field(30, description="Scores 0-low_max → LOW risk → APPROVE")
    medium_max: int = Field(60, description="Scores low_max+1 to medium_max → MEDIUM risk → REVIEW")
    # Scores above medium_max → HIGH risk → BLOCK


class MerchantRules(BaseModel):
    """Complete configurable risk rules for a merchant."""
    merchant_id: str
    velocity: VelocityRule = Field(default_factory=VelocityRule)
    amount_anomaly: AmountAnomalyRule = Field(default_factory=AmountAnomalyRule)
    geo_mismatch: GeoMismatchRule = Field(default_factory=GeoMismatchRule)
    new_account: NewAccountRule = Field(default_factory=NewAccountRule)
    money_mule: MoneyMuleRule = Field(default_factory=MoneyMuleRule)
    time_of_day: TimeOfDayRule = Field(default_factory=TimeOfDayRule)
    max_payout: MaxPayoutRule = Field(default_factory=MaxPayoutRule)
    score_thresholds: ScoreThresholds = Field(default_factory=ScoreThresholds)
    allowlist_auto_approve: bool = Field(True, description="Auto-approve if recipient on merchant allowlist")
