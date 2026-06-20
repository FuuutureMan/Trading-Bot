from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BasePortfolio(ABC):
    """Abstract portfolio/broker interface used by the trading engine."""

    @abstractmethod
    def total_value(self, prices: dict | None = None) -> float:
        pass

    @abstractmethod
    def open_trade_count(self) -> int:
        pass

    @abstractmethod
    def has_position(self, symbol: str) -> bool:
        pass

    @abstractmethod
    def summary(self) -> dict:
        pass

    @abstractmethod
    def open_long(self, symbol: str, shares: int, fill_price: float,
                  stop_price: float, target_price: float,
                  reason: str = "") -> bool:
        pass

    @abstractmethod
    def close_position(self, symbol: str, fill_price: float,
                       reason: str = "") -> Optional[dict]:
        pass

    @property
    def is_live(self) -> bool:
        return False
