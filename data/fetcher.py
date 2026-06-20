"""
data/fetcher.py
───────────────
Pulls OHLCV price data from Webull and returns
clean pandas DataFrames ready for the skill sensors.
"""

import pandas as pd
import pandas_ta as ta
from webull import webull

from config import settings


# ── Initialise Webull client ─────────────────────────────
_wb = webull()


def _ensure_logged_in():
    if _wb.is_logged_in():
        return
    if not settings.WEBULL_EMAIL or not settings.WEBULL_PASSWORD:
        raise RuntimeError("Webull credentials are required to fetch market data.")
    print("  [webull] Logging in for market data...")
    _wb.login(
        username=settings.WEBULL_EMAIL,
        password=settings.WEBULL_PASSWORD,
        device_name=settings.WEBULL_DEVICE_NAME,
        save_token=False,
    )


def _clean_bars(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index(ascending=False)
    return df.astype(float)


def get_daily_ohlcv(symbol: str, outputsize: str = "compact") -> pd.DataFrame:
    """
    Fetch daily OHLCV bars for a symbol from Webull.
    Returns a DataFrame with columns: open, high, low, close, volume.
    Indexed by date, newest first.
    """
    _ensure_logged_in()
    print(f"  Fetching daily data for {symbol}...")
    df = _wb.get_bars(stock=symbol, interval="d1", count=100, extendTrading=0)
    return _clean_bars(df[["open", "high", "low", "close", "volume"]])


def get_weekly_ohlcv(symbol: str) -> pd.DataFrame:
    """Fetch weekly bars from Webull."""
    _ensure_logged_in()
    print(f"  Fetching weekly data for {symbol}...")
    df = _wb.get_bars(stock=symbol, interval="w1", count=100, extendTrading=0)
    return _clean_bars(df[["open", "high", "low", "close", "volume"]])


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


def rate_limited_fetch(symbols: list, delay: float = 0.0) -> dict:
    """
    Fetch enriched data for a list of symbols.

    Webull has relaxed rate limits compared to other data providers.
    Returns a dict of { symbol: DataFrame }
    """
    results = {}
    for symbol in symbols:
        try:
            results[symbol] = get_enriched(symbol)
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            results[symbol] = None
    return results
