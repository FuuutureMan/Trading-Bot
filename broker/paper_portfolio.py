"""
broker/paper_portfolio.py
──────────────────────────
Simulates a brokerage account for paper trading.
Tracks positions, fills orders at next-bar-open price,
calculates P&L, and exposes portfolio state to the risk manager.

This is intentionally self-contained — when you graduate to
live trading, you swap this out for webull_client.py without
touching any other part of the bot.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional
import json, os

from config import settings
from broker.base_portfolio import BasePortfolio


@dataclass
class Position:
    symbol:       str
    shares:       int
    entry_price:  float
    stop_price:   float
    target_price: float
    direction:    str           # "long" or "short"
    opened_at:    datetime = field(default_factory=datetime.utcnow)
    entry_reason: str = ""      # Ollama's reasoning, stored for the journal

    def current_value(self, current_price: float) -> float:
        return self.shares * current_price

    def unrealised_pnl(self, current_price: float) -> float:
        if self.direction == "long":
            return self.shares * (current_price - self.entry_price)
        else:
            return self.shares * (self.entry_price - current_price)

    def risk_dollar(self) -> float:
        return self.shares * abs(self.entry_price - self.stop_price)


@dataclass
class ClosedTrade:
    symbol:       str
    shares:       int
    entry_price:  float
    exit_price:   float
    direction:    str
    pnl:          float
    pnl_pct:      float
    opened_at:    datetime
    closed_at:    datetime
    exit_reason:  str = ""


class PaperPortfolio(BasePortfolio):
    """
    Paper trading portfolio. Persists state to a JSON file
    so positions survive bot restarts.
    """

    STATE_FILE = "paper_portfolio_state.json"

    def __init__(self, starting_balance: float = None):
        self.starting_balance = starting_balance or settings.PAPER_BALANCE
        self.cash:        float = self.starting_balance
        self.positions:   Dict[str, Position] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.peak_value:  float = self.starting_balance
        self._week_start_value: float = self.starting_balance
        self._day_start_value:  float = self.starting_balance
        self._last_reset_date:  date  = date.today()

        self._load_state()
        # Save initial state immediately so the dashboard can load an empty portfolio.
        self._save_state()

    # ── Order execution ───────────────────────────────────────

    def open_long(self, symbol: str, shares: int, fill_price: float,
                  stop_price: float, target_price: float,
                  reason: str = "") -> bool:
        """Simulate a buy order fill."""
        cost = shares * fill_price
        if cost > self.cash:
            print(f"  [portfolio] Not enough cash for {symbol}: "
                  f"need ${cost:.2f}, have ${self.cash:.2f}")
            return False

        self.cash -= cost
        self.positions[symbol] = Position(
            symbol=symbol, shares=shares, entry_price=fill_price,
            stop_price=stop_price, target_price=target_price,
            direction="long", entry_reason=reason
        )
        print(f"  [portfolio] Opened LONG {symbol}: "
              f"{shares} shares @ ${fill_price:.2f}")
        self._save_state()
        return True

    def close_position(self, symbol: str, fill_price: float,
                       reason: str = "") -> Optional[ClosedTrade]:
        """Simulate a sell order fill."""
        if symbol not in self.positions:
            print(f"  [portfolio] No position in {symbol} to close")
            return None

        pos = self.positions[symbol]
        proceeds = pos.shares * fill_price
        self.cash += proceeds

        pnl = pos.unrealised_pnl(fill_price)
        pnl_pct = (pnl / (pos.shares * pos.entry_price)) * 100

        trade = ClosedTrade(
            symbol=symbol, shares=pos.shares,
            entry_price=pos.entry_price, exit_price=fill_price,
            direction=pos.direction, pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            opened_at=pos.opened_at, closed_at=datetime.utcnow(),
            exit_reason=reason
        )
        self.closed_trades.append(trade)
        del self.positions[symbol]

        print(f"  [portfolio] Closed {symbol} @ ${fill_price:.2f} | "
              f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")

        self._update_peak()
        self._save_state()
        return trade

    # ── State queries (used by RiskManager) ──────────────────

    def total_value(self, prices: dict = None) -> float:
        """Account value = cash + all open positions at current prices."""
        if not prices:
            # Without current prices, use entry prices as an estimate
            position_value = sum(
                p.shares * p.entry_price for p in self.positions.values()
            )
        else:
            position_value = sum(
                p.shares * prices.get(sym, p.entry_price)
                for sym, p in self.positions.items()
            )
        return self.cash + position_value

    def open_trade_count(self) -> int:
        return len(self.positions)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def total_open_risk_pct(self) -> float:
        """Sum of all active stop distances as % of total account value."""
        total_risk = sum(p.risk_dollar() for p in self.positions.values())
        account    = self.total_value()
        return (total_risk / account * 100) if account > 0 else 0.0

    def daily_pnl_pct(self) -> float:
        self._maybe_reset_daily()
        current = self.total_value()
        return ((current - self._day_start_value) / self._day_start_value) * 100

    def weekly_pnl_pct(self) -> float:
        current = self.total_value()
        return ((current - self._week_start_value) / self._week_start_value) * 100

    def max_drawdown_pct(self) -> float:
        current = self.total_value()
        self._update_peak()
        return ((self.peak_value - current) / self.peak_value) * 100

    def summary(self) -> dict:
        return {
            "cash":          round(self.cash, 2),
            "total_value":   round(self.total_value(), 2),
            "open_positions": self.open_trade_count(),
            "daily_pnl_pct": round(self.daily_pnl_pct(), 2),
            "weekly_pnl_pct":round(self.weekly_pnl_pct(), 2),
            "max_drawdown":  round(self.max_drawdown_pct(), 2),
            "total_trades":  len(self.closed_trades),
        }

    # ── Internal helpers ──────────────────────────────────────

    def _update_peak(self):
        current = self.total_value()
        if current > self.peak_value:
            self.peak_value = current

    def _maybe_reset_daily(self):
        today = date.today()
        if today != self._last_reset_date:
            self._day_start_value  = self.total_value()
            self._last_reset_date  = today

    def _save_state(self):
        """Persist portfolio to disk so it survives restarts."""
        state = {
            "cash":        self.cash,
            "peak_value":  self.peak_value,
            "positions": {
                sym: {
                    "shares":       p.shares,
                    "entry_price":  p.entry_price,
                    "stop_price":   p.stop_price,
                    "target_price": p.target_price,
                    "direction":    p.direction,
                    "opened_at":    p.opened_at.isoformat(),
                    "entry_reason": p.entry_reason,
                }
                for sym, p in self.positions.items()
            }
        }
        with open(self.STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        """Restore portfolio from disk if a saved state exists."""
        if not os.path.exists(self.STATE_FILE):
            return
        try:
            with open(self.STATE_FILE) as f:
                state = json.load(f)
            self.cash       = state.get("cash", self.starting_balance)
            self.peak_value = state.get("peak_value", self.cash)
            for sym, p in state.get("positions", {}).items():
                self.positions[sym] = Position(
                    symbol=sym,
                    shares=p["shares"],
                    entry_price=p["entry_price"],
                    stop_price=p["stop_price"],
                    target_price=p["target_price"],
                    direction=p["direction"],
                    opened_at=datetime.fromisoformat(p["opened_at"]),
                    entry_reason=p.get("entry_reason", ""),
                )
            print(f"  [portfolio] Restored state: "
                  f"{len(self.positions)} open positions, ${self.cash:.2f} cash")
        except Exception as e:
            print(f"  [portfolio] Could not load saved state: {e}")
