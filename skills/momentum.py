"""
skills/momentum.py
───────────────────
Momentum skill sensor.

Detects:
  - RSI oversold/overbought conditions
  - RSI divergence vs price (leading reversal signal)
  - MACD bullish/bearish crossovers
  - MACD histogram momentum shifts

Signals it can produce:
  bullish_rsi_oversold        RSI dipped below 30 and is turning up
  bullish_macd_crossover      MACD line crossed above signal line
  bullish_divergence          Price made lower low, RSI made higher low
  bearish_rsi_overbought      RSI above 70 and turning down
  bearish_macd_crossover      MACD line crossed below signal line
  bearish_divergence          Price made higher high, RSI made lower high
"""

import pandas as pd
import numpy as np
from typing import Optional

from skills.base_skill import BaseSkill, Signal


class MomentumSkill(BaseSkill):

    def __init__(self):
        super().__init__()
        self.name = "momentum"

        # Thresholds — tune these over time
        self.RSI_OVERSOLD   = 35    # Below = oversold territory
        self.RSI_OVERBOUGHT = 65    # Above = overbought territory
        self.LOOKBACK       = 14    # Bars to look back for divergence

    def analyse(self, symbol: str, df: pd.DataFrame) -> Optional[Signal]:
        """
        Run all momentum checks and return the strongest signal found.
        Returns None if nothing worth acting on.
        """
        # Need at least 30 bars for reliable signals
        if len(df) < 30:
            print(f"  [momentum] Not enough data for {symbol}")
            return None

        # Column names pandas-ta generates
        rsi_col    = "RSI_14"
        macd_col   = "MACD_12_26_9"
        signal_col = "MACDs_12_26_9"
        hist_col   = "MACDh_12_26_9"

        # Check all required columns exist
        required = [rsi_col, macd_col, signal_col, hist_col]
        missing = [c for c in required if c not in df.columns]
        if missing:
            print(f"  [momentum] Missing columns for {symbol}: {missing}")
            return None

        current_price = float(df["close"].iloc[0])
        current_rsi   = float(df[rsi_col].iloc[0])

        # ── 1. Check for bullish RSI divergence ─────────────────
        bull_div = self._check_bullish_divergence(df, rsi_col)
        if bull_div:
            strength = self._rsi_strength(current_rsi, bullish=True)
            return Signal(
                symbol    = symbol,
                skill     = self.name,
                signal    = "bullish_divergence",
                direction = "bullish",
                strength  = min(0.9, strength + 0.15),   # Divergence = bonus strength
                timeframe = "daily",
                price     = current_price,
                notes     = (f"Bullish divergence: price lower low but RSI higher low. "
                             f"RSI={current_rsi:.1f}"),
            )

        # ── 2. Check for bearish RSI divergence ─────────────────
        bear_div = self._check_bearish_divergence(df, rsi_col)
        if bear_div:
            strength = self._rsi_strength(current_rsi, bullish=False)
            return Signal(
                symbol    = symbol,
                skill     = self.name,
                signal    = "bearish_divergence",
                direction = "bearish",
                strength  = min(0.9, strength + 0.15),
                timeframe = "daily",
                price     = current_price,
                notes     = (f"Bearish divergence: price higher high but RSI lower high. "
                             f"RSI={current_rsi:.1f}"),
            )

        # ── 3. MACD crossover (current bar vs previous bar) ─────
        macd_now  = float(df[macd_col].iloc[0])
        macd_prev = float(df[macd_col].iloc[1])
        sig_now   = float(df[signal_col].iloc[0])
        sig_prev  = float(df[signal_col].iloc[1])

        # Bullish crossover: MACD just crossed above signal line
        if macd_prev < sig_prev and macd_now > sig_now:
            return Signal(
                symbol    = symbol,
                skill     = self.name,
                signal    = "bullish_macd_crossover",
                direction = "bullish",
                strength  = self._rsi_strength(current_rsi, bullish=True),
                timeframe = "daily",
                price     = current_price,
                notes     = (f"MACD crossed above signal. "
                             f"RSI={current_rsi:.1f}, MACD={macd_now:.3f}"),
            )

        # Bearish crossover: MACD just crossed below signal line
        if macd_prev > sig_prev and macd_now < sig_now:
            return Signal(
                symbol    = symbol,
                skill     = self.name,
                signal    = "bearish_macd_crossover",
                direction = "bearish",
                strength  = self._rsi_strength(current_rsi, bullish=False),
                timeframe = "daily",
                price     = current_price,
                notes     = (f"MACD crossed below signal. "
                             f"RSI={current_rsi:.1f}, MACD={macd_now:.3f}"),
            )

        # ── 4. Simple RSI extreme conditions ────────────────────
        if current_rsi < self.RSI_OVERSOLD:
            return Signal(
                symbol    = symbol,
                skill     = self.name,
                signal    = "bullish_rsi_oversold",
                direction = "bullish",
                strength  = self._rsi_strength(current_rsi, bullish=True),
                timeframe = "daily",
                price     = current_price,
                notes     = f"RSI oversold at {current_rsi:.1f}",
            )

        if current_rsi > self.RSI_OVERBOUGHT:
            return Signal(
                symbol    = symbol,
                skill     = self.name,
                signal    = "bearish_rsi_overbought",
                direction = "bearish",
                strength  = self._rsi_strength(current_rsi, bullish=False),
                timeframe = "daily",
                price     = current_price,
                notes     = f"RSI overbought at {current_rsi:.1f}",
            )

        # No signal worth reporting
        return None

    # ── Helper methods ────────────────────────────────────────

    def _rsi_strength(self, rsi: float, bullish: bool) -> float:
        """
        Convert an RSI value to a 0.0–1.0 signal strength score.
        Lower RSI = stronger bullish signal. Higher RSI = stronger bearish.
        """
        if bullish:
            # RSI 30 → 0.9, RSI 50 → 0.5, RSI 70 → 0.1
            return round(max(0.1, min(0.9, (70 - rsi) / 40)), 2)
        else:
            # RSI 70 → 0.9, RSI 50 → 0.5, RSI 30 → 0.1
            return round(max(0.1, min(0.9, (rsi - 30) / 40)), 2)

    def _check_bullish_divergence(self, df: pd.DataFrame, rsi_col: str) -> bool:
        """
        True if: price made a lower low in the last LOOKBACK bars
        but RSI made a higher low (bullish divergence).
        """
        lookback = self.LOOKBACK
        if len(df) < lookback:
            return False

        prices = df["close"].iloc[:lookback].values
        rsis   = df[rsi_col].iloc[:lookback].values

        # Find most recent and second most recent price lows
        recent_price_low  = min(prices[:5])
        earlier_price_low = min(prices[5:])

        # Find corresponding RSI lows in same windows
        recent_rsi_low  = min(rsis[:5])
        earlier_rsi_low = min(rsis[5:])

        # Divergence: price lower low but RSI higher low
        price_lower_low = recent_price_low < earlier_price_low
        rsi_higher_low  = recent_rsi_low > earlier_rsi_low

        return price_lower_low and rsi_higher_low

    def _check_bearish_divergence(self, df: pd.DataFrame, rsi_col: str) -> bool:
        """
        True if: price made a higher high in the last LOOKBACK bars
        but RSI made a lower high (bearish divergence).
        """
        lookback = self.LOOKBACK
        if len(df) < lookback:
            return False

        prices = df["close"].iloc[:lookback].values
        rsis   = df[rsi_col].iloc[:lookback].values

        recent_price_high  = max(prices[:5])
        earlier_price_high = max(prices[5:])

        recent_rsi_high  = max(rsis[:5])
        earlier_rsi_high = max(rsis[5:])

        price_higher_high = recent_price_high > earlier_price_high
        rsi_lower_high    = recent_rsi_high < earlier_rsi_high

        return price_higher_high and rsi_lower_high
