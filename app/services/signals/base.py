from abc import ABC, abstractmethod
import aiosqlite
from app.models.risk import SignalResult
from app.models.transaction import PayoutRequest
from app.models.rules import MerchantRules


class BaseSignal(ABC):
    """Abstract base class for all fraud signals."""

    @property
    @abstractmethod
    def signal_name(self) -> str:
        pass

    @abstractmethod
    async def evaluate(
        self,
        tx: PayoutRequest,
        rules: MerchantRules,
        db: aiosqlite.Connection,
    ) -> SignalResult:
        """Evaluate this signal for the given transaction. Returns a SignalResult."""
        pass
