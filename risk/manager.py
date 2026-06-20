"""
risk/manager.py
────────────────
The hard rules layer. Sits between LM Studio's recommendation
and the broker. LM Studio cannot override these checks.

Usage:
    from risk.manager import RiskManager
    rm = RiskManager(portfolio)
    result = rm.validate(signal, lmstudio_recommendation)
    if result.approved:
        broker.place_order(...)
"""

from dataclasses import dataclass
from typing import Optional
from config import settings


@dataclass
class ValidationResult:
    approved:   bool
    shares:     int             # Calculated position size
    risk_dollar:float           # Dollar amount at risk
    stop_price: float           # Calculated stop loss price
    target_price:float          # Calculated 2R target
    reason:     str             # Why approved or rejected


class RiskManager:

    def __init__(self, portfolio):
        """
        portfolio: the Portfolio object (from broker/paper_portfolio.py)
        Gives the risk manager visibility of current state.
        """
        self.portfolio = portfolio

    def validate(self, symbol: str, entry_price: float,
                 stop_price: float, direction: str) -> ValidationResult:
        """
        Run all hard rule checks for a proposed trade.

        Parameters
        ----------
        symbol      : ticker
        entry_price : proposed entry price
        stop_price  : proposed stop loss price
        direction   : "long" or "short"

        Returns a ValidationResult — check .approved before placing order.
        """

        stop_distance = abs(entry_price - stop_price)
        if stop_distance == 0:
            return self._reject("Stop price cannot equal entry price")

        # ── Position sizing ──────────────────────────────────────
        account_value = self.portfolio.total_value()
        risk_dollar   = account_value * (settings.RISK_PER_TRADE_PCT / 100)
        shares        = int(risk_dollar / stop_distance)

        if shares < 1:
            return self._reject(
                f"Position size rounds to 0 shares. "
                f"Stop too wide for account size "
                f"(stop distance ${stop_distance:.2f}, risk budget ${risk_dollar:.2f})"
            )

        position_value = shares * entry_price
        position_pct   = (position_value / account_value) * 100

        # ── Rule: max position size ──────────────────────────────
        if position_pct > settings.MAX_POSITION_PCT:
            # Shrink shares to fit within max position limit
            max_value = account_value * (settings.MAX_POSITION_PCT / 100)
            shares    = int(max_value / entry_price)
            if shares < 1:
                return self._reject(
                    f"Position would exceed {settings.MAX_POSITION_PCT}% of portfolio "
                    f"and cannot be reduced further"
                )
            position_value = shares * entry_price
            risk_dollar    = shares * stop_distance

        # ── Rule: R:R ratio ─────────────────────────────────────
        target_price = self._calculate_target(entry_price, stop_price, direction)
        reward       = abs(target_price - entry_price)
        rr_ratio     = reward / stop_distance if stop_distance > 0 else 0

        if rr_ratio < settings.MIN_REWARD_RISK_RATIO:
            return self._reject(
                f"R:R ratio {rr_ratio:.1f} is below minimum "
                f"{settings.MIN_REWARD_RISK_RATIO:.1f}. "
                f"Move target or tighten stop."
            )

        # ── Rule: max open trades ────────────────────────────────
        open_count = self.portfolio.open_trade_count()
        if open_count >= settings.MAX_OPEN_TRADES:
            return self._reject(
                f"Already at max open trades ({open_count}/{settings.MAX_OPEN_TRADES}). "
                f"Wait for a position to close."
            )

        # ── Rule: already holding this symbol ───────────────────
        if self.portfolio.has_position(symbol):
            return self._reject(f"Already holding {symbol}. No adding to positions.")

        # ── Rule: portfolio heat ─────────────────────────────────
        current_heat = self.portfolio.total_open_risk_pct()
        new_heat     = current_heat + (risk_dollar / account_value * 100)
        if new_heat > settings.MAX_PORTFOLIO_HEAT_PCT:
            return self._reject(
                f"Adding this trade would bring portfolio heat to "
                f"{new_heat:.1f}% (max {settings.MAX_PORTFOLIO_HEAT_PCT}%)"
            )

        # ── Rule: circuit breakers ───────────────────────────────
        cb = self._check_circuit_breakers()
        if cb:
            return self._reject(cb)

        # ── All checks passed ────────────────────────────────────
        return ValidationResult(
            approved     = True,
            shares       = shares,
            risk_dollar  = round(risk_dollar, 2),
            stop_price   = round(stop_price, 2),
            target_price = round(target_price, 2),
            reason       = (
                f"Approved. {shares} shares @ ${entry_price:.2f}. "
                f"Stop ${stop_price:.2f} | Target ${target_price:.2f} | "
                f"Risk ${risk_dollar:.2f} ({settings.RISK_PER_TRADE_PCT}%) | "
                f"R:R {rr_ratio:.1f}"
            ),
        )

    # ── Private helpers ───────────────────────────────────────

    def _calculate_target(self, entry: float, stop: float,
                          direction: str) -> float:
        """Calculate 2R target price."""
        stop_distance = abs(entry - stop)
        target_distance = stop_distance * settings.MIN_REWARD_RISK_RATIO
        if direction == "long":
            return entry + target_distance
        else:
            return entry - target_distance

    def _check_circuit_breakers(self) -> Optional[str]:
        """Returns an error message string if any circuit breaker is tripped."""
        daily_pnl_pct = self.portfolio.daily_pnl_pct()
        if daily_pnl_pct <= -settings.DAILY_LOSS_LIMIT_PCT:
            return (f"Daily loss circuit breaker tripped: "
                    f"{daily_pnl_pct:.1f}% (limit -{settings.DAILY_LOSS_LIMIT_PCT}%)")

        weekly_pnl_pct = self.portfolio.weekly_pnl_pct()
        if weekly_pnl_pct <= -settings.WEEKLY_LOSS_LIMIT_PCT:
            return (f"Weekly loss circuit breaker tripped: "
                    f"{weekly_pnl_pct:.1f}% (limit -{settings.WEEKLY_LOSS_LIMIT_PCT}%)")

        drawdown_pct = self.portfolio.max_drawdown_pct()
        if drawdown_pct >= settings.MAX_DRAWDOWN_PCT:
            return (f"MAX DRAWDOWN KILL SWITCH: {drawdown_pct:.1f}% drawdown. "
                    f"Bot requires manual restart.")

        return None

    def _reject(self, reason: str) -> ValidationResult:
        return ValidationResult(
            approved=False, shares=0, risk_dollar=0.0,
            stop_price=0.0, target_price=0.0, reason=reason
        )
