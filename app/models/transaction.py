from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class PayoutRequest(BaseModel):
    """Incoming payout transaction to be risk-scored."""
    transaction_id: str = Field(..., description="Unique transaction identifier")
    merchant_id: str = Field(..., description="Merchant submitting the payout")
    user_id: str = Field(..., description="User/sender initiating the payout")
    recipient_account: str = Field(..., description="Destination bank account number")
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    amount: float = Field(..., gt=0, description="Payout amount")
    currency: str = Field(default="USD", description="ISO 4217 currency code")
    user_ip: Optional[str] = Field(None, description="IP address of the request")
    device_id: Optional[str] = Field(None, description="Device fingerprint")
    user_country: Optional[str] = Field(None, description="ISO 3166-1 alpha-3 country of user's registered account")
    ip_country: Optional[str] = Field(None, description="ISO 3166-1 alpha-3 country resolved from IP")
    account_created_at: Optional[datetime] = Field(None, description="When the user's account was created")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Transaction timestamp")
    metadata: Optional[dict] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "transaction_id": "TXN-2024-001",
                "merchant_id": "MER001",
                "user_id": "USR_RF_001",
                "recipient_account": "PH-ACC-7812345678",
                "recipient_email": "driver@example.com",
                "amount": 52.50,
                "currency": "PHP",
                "user_ip": "203.177.12.45",
                "device_id": "DEV-ABC123",
                "user_country": "PHL",
                "ip_country": "PHL",
                "account_created_at": "2023-01-15T00:00:00Z",
                "timestamp": "2024-06-15T14:30:00Z"
            }
        }
    }
