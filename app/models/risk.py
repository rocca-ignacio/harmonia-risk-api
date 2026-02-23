from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from datetime import datetime


class SignalResult(BaseModel):
    """Result from a single fraud signal evaluation."""
    signal: str
    triggered: bool
    score_contribution: float = Field(0.0, description="Points added to total risk score (0-100)")
    description: str
    details: dict = {}


class RiskAssessment(BaseModel):
    """Complete risk assessment response for a payout transaction."""
    transaction_id: str
    merchant_id: str
    risk_score: float = Field(..., ge=0, le=100, description="Composite risk score 0-100")
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    action: Literal["APPROVE", "REVIEW", "BLOCK"]
    signals: List[SignalResult]
    processing_time_ms: float
    evaluated_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "transaction_id": "TXN-2024-001",
                "merchant_id": "MER001",
                "risk_score": 72.0,
                "risk_level": "HIGH",
                "action": "BLOCK",
                "signals": [
                    {
                        "signal": "velocity",
                        "triggered": True,
                        "score_contribution": 30,
                        "description": "High velocity: 6 transactions in last 10 min (limit: 3)",
                        "details": {"transaction_count": 6, "window_minutes": 10, "limit": 3}
                    }
                ],
                "processing_time_ms": 12.4,
                "evaluated_at": "2024-06-15T14:30:01Z"
            }
        }
    }


class BatchRescoreRequest(BaseModel):
    merchant_id: str
    transaction_ids: List[str] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    update_scores: bool = False


class BatchRescoreResult(BaseModel):
    transaction_id: str
    old_score: Optional[float]
    old_action: Optional[str]
    new_score: float
    new_risk_level: str
    new_action: str
    score_delta: Optional[float]
