"""
skills/base_skill.py
─────────────────────
Every skill sensor inherits from BaseSkill.
This enforces a consistent interface so the signal bus
always receives the same shape of data regardless of
which skill produced it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Signal:
    """
    The standard output of every skill sensor.
    All fields after 'strength' are optional context.
    """
    symbol:     str             # e.g. "AAPL"
    skill:      str             # e.g. "momentum"
    signal:     str             # e.g. "bullish_divergence", "bearish_crossover"
    direction:  str             # "bullish", "bearish", or "neutral"
    strength:   float           # 0.0 → 1.0  (how strong is this signal?)
    timeframe:  str             # "daily", "weekly", "4h"
    timestamp:  datetime = field(default_factory=datetime.utcnow)

    # Optional context — helps Ollama reason about the signal
    notes:      str  = ""       # Human-readable explanation
    price:      Optional[float] = None   # Price when signal fired
    stop_hint:  Optional[float] = None   # Suggested stop level
    target_hint:Optional[float] = None   # Suggested target level

    def to_dict(self) -> dict:
        """Convert to a dict for JSON serialisation into the signal bus."""
        return {
            "symbol":       self.symbol,
            "skill":        self.skill,
            "signal":       self.signal,
            "direction":    self.direction,
            "strength":     round(self.strength, 3),
            "timeframe":    self.timeframe,
            "timestamp":    self.timestamp.isoformat(),
            "notes":        self.notes,
            "price":        self.price,
            "stop_hint":    self.stop_hint,
            "target_hint":  self.target_hint,
        }

    def __repr__(self):
        return (f"Signal({self.symbol} | {self.skill} | "
                f"{self.direction} {self.signal} | "
                f"strength={self.strength:.2f})")


class BaseSkill(ABC):
    """
    Abstract base class for all skill sensors.

    To create a new skill:
        1. Inherit from BaseSkill
        2. Set self.name to something descriptive
        3. Implement the analyse() method
        4. Return a Signal (or None if no signal found)
    """

    def __init__(self):
        self.name = "base"      # Override in each subclass

    @abstractmethod
    def analyse(self, symbol: str, df) -> Optional[Signal]:
        """
        Analyse price/indicator data for a symbol.

        Parameters
        ----------
        symbol : str
            The ticker being analysed.
        df : pd.DataFrame
            Enriched OHLCV DataFrame from data.fetcher.get_enriched().
            Newest row is df.iloc[0].

        Returns
        -------
        Signal or None
            Return a Signal object if a meaningful signal is found.
            Return None if no signal worth reporting.
        """
        pass

    def safe_analyse(self, symbol: str, df) -> Optional[Signal]:
        """
        Wrapper around analyse() that catches errors so one
        bad skill doesn't crash the whole scan loop.
        """
        try:
            return self.analyse(symbol, df)
        except Exception as e:
            print(f"  [{self.name}] Error analysing {symbol}: {e}")
            return None
