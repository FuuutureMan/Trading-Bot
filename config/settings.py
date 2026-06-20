"""
config/settings.py
──────────────────
Single source of truth for all configuration.
Reads from your .env file so secrets never live in code.
"""

import os
from dotenv import load_dotenv

# Load the .env file automatically, overriding any existing process environment values
load_dotenv(override=True)


# ── Webull ─────────────────────────────────────────────────
WEBULL_EMAIL        = os.getenv("WEBULL_EMAIL", "")
WEBULL_PASSWORD     = os.getenv("WEBULL_PASSWORD", "")
WEBULL_TRADING_PIN  = os.getenv("WEBULL_TRADING_PIN", "")

# ── LM Studio ──────────────────────────────────────────────
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", os.getenv("OLLAMA_MODEL", "mistral"))
LM_STUDIO_HOST  = os.getenv("LM_STUDIO_HOST", os.getenv("OLLAMA_HOST", "http://localhost:11434"))

# ── Portfolio ──────────────────────────────────────────────
PAPER_BALANCE       = float(os.getenv("PAPER_BALANCE", 25000))
RISK_PER_TRADE_PCT  = float(os.getenv("RISK_PER_TRADE_PCT", 1.0))
MAX_OPEN_TRADES     = int(os.getenv("MAX_OPEN_TRADES", 6))

# ── Watchlist ──────────────────────────────────────────────
_raw_watchlist = os.getenv("WATCHLIST", "AAPL,MSFT,NVDA")
WATCHLIST = [t.strip() for t in _raw_watchlist.split(",")]

# ── Broker mode ──────────────────────────────────────────────
BROKER_MODE = os.getenv("BROKER_MODE", "paper").strip().lower()
WEBULL_DEVICE_NAME = os.getenv("WEBULL_DEVICE_NAME", "default_device")

# ── Risk hard limits ───────────────────────────────────────
MAX_POSITION_PCT        = 10.0   # Max % of portfolio in one stock
MAX_SECTOR_PCT          = 30.0   # Max % in one sector
MAX_PORTFOLIO_HEAT_PCT  = 8.0    # Max total open risk at once
MIN_REWARD_RISK_RATIO   = 2.0    # Minimum R:R to enter a trade
ATR_STOP_MULTIPLIER     = 1.5    # Stop = 1.5 × ATR(14)

# ── Circuit breakers ───────────────────────────────────────
DAILY_LOSS_LIMIT_PCT    = 3.0    # Pause bot at -3% daily
WEEKLY_LOSS_LIMIT_PCT   = 6.0    # Pause at -6% weekly
MAX_DRAWDOWN_PCT        = 15.0   # Kill switch at -15% peak-to-trough

# ── No-trade zones ─────────────────────────────────────────
EARNINGS_BLACKOUT_DAYS  = 3      # Days before/after earnings
NO_ENTRY_OPEN_MINUTES   = 30     # Skip first 30 min of session
MIN_VOLUME_RATIO        = 0.5    # Must be > 50% of 20-day avg volume
VIX_SPIKE_THRESHOLD     = 30     # No new entries when VIX > 30

# ── Timeframes ─────────────────────────────────────────────
PRIMARY_TIMEFRAME       = "daily"
CONFIRMATION_TIMEFRAME  = "weekly"

# ── Scheduler ──────────────────────────────────────────────
# When to run the main scan (market hours, Eastern time)
SCAN_TIMES = ["09:45", "12:00", "15:30"]   # HH:MM ET


def validate():
    """Call at startup to catch missing config early."""
    errors = []

    if not WEBULL_EMAIL:
        errors.append("WEBULL_EMAIL is missing from .env")
    if not WEBULL_PASSWORD:
        errors.append("WEBULL_PASSWORD is missing from .env")

    if BROKER_MODE == "webull" and not WEBULL_TRADING_PIN:
        errors.append("WEBULL_TRADING_PIN is missing from .env")
    if BROKER_MODE not in {"paper", "webull"}:
        errors.append("BROKER_MODE must be 'paper' or 'webull'")

    if errors:
        for e in errors:
            print(f"  ⚠  {e}")
        return False
    return True
