"""
data/fetcher.py
───────────────
Pulls OHLCV price data from Alpha Vantage and returns
clean pandas DataFrames ready for the skill sensors.

Alpha Vantage free tier = 25 requests/day.
We cache results to a local SQLite DB to avoid burning the quota.
"""

import time
import pandas as pd
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.techindicators import TechIndicators
import pandas_ta as ta

from config import settings


# ── Initialise Alpha Vantage clients ──────────────────────
_ts = TimeSeries(key=settings.ALPHA_VANTAGE_API_KEY, output_format="pandas")
_ti = TechIndicators(key=settings.ALPHA_VANTAGE_API_KEY, output_format="pandas")


def get_daily_ohlcv(symbol: str, outputsize: str = "compact") -> pd.DataFrame:
    """
    Fetch daily OHLCV bars for a symbol.

    outputsize:
        "compact"  → last 100 bars  (use this normally, saves API calls)
        "full"     → up to 20 years (use for initial analysis only)

    Returns a DataFrame with columns:
        open, high, low, close, volume
    Indexed by date, newest first.
    """
    print(f"  Fetching daily data for {symbol}...")
    data, _ = _ts.get_daily(symbol=symbol, outputsize=outputsize)

    # Alpha Vantage returns ugly column names like "1. open" — clean them up
    data.columns = ["open", "high", "low", "close", "volume"]
    data.index = pd.to_datetime(data.index)
    data = data.sort_index(ascending=False)   # Newest row first
    data = data.astype(float)

    return data


def get_weekly_ohlcv(symbol: str) -> pd.DataFrame:
    """Fetch weekly bars — used by the multi-timeframe skill."""
    print(f"  Fetching weekly data for {symbol}...")
    data, _ = _ts.get_weekly(symbol=symbol)
    data.columns = ["open", "high", "low", "close", "volume"]
    data.index = pd.to_datetime(data.index)
    data = data.sort_index(ascending=False)
    data = data.astype(float)
    return data


def enrich_with_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add commonly used technical indicators to a price DataFrame.
    Uses pandas-ta which works on the DataFrame directly.

    Adds: RSI, MACD, ATR, Bollinger Bands, EMA 20/50/200, OBV
    """
    # pandas-ta wants oldest-first for calculations
    df = df.sort_index(ascending=True).copy()

    df.ta.rsi(length=14, append=True)           # RSI_14
    df.ta.macd(fast=12, slow=26, signal=9, append=True)  # MACD_12_26_9 etc
    df.ta.atr(length=14, append=True)           # ATRr_14
    df.ta.bbands(length=20, append=True)        # BBL, BBM, BBU, BBB, BBP
    df.ta.ema(length=20, append=True)           # EMA_20
    df.ta.ema(length=50, append=True)           # EMA_50
    df.ta.ema(length=200, append=True)          # EMA_200
    df.ta.obv(append=True)                      # OBV

    # Return newest-first again to match rest of the codebase
    return df.sort_index(ascending=False)


def get_enriched(symbol: str) -> pd.DataFrame:
    """
    One-call convenience: fetch daily OHLCV + all indicators.
    This is what most skills will call.
    """
    df = get_daily_ohlcv(symbol)
    df = enrich_with_indicators(df)
    return df


def rate_limited_fetch(symbols: list, delay: float = 12.0) -> dict:
    """
    Fetch enriched data for a list of symbols with a delay between
    each call to respect Alpha Vantage rate limits.

    Free tier: 5 calls/minute → 12 second delay is safe.
    Returns a dict of { symbol: DataFrame }
    """
    results = {}
    for i, symbol in enumerate(symbols):
        try:
            results[symbol] = get_enriched(symbol)
            if i < len(symbols) - 1:
                print(f"  Waiting {delay}s (API rate limit)...")
                time.sleep(delay)
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            results[symbol] = None
    return results
