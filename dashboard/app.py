"""
dashboard/app.py
────────────────
Streamlit dashboard for monitoring the paper trading portfolio.
Run with: streamlit run dashboard/app.py

Shows:
  - Portfolio summary (total value, cash, P&L, drawdown)
  - Open positions with entry/stop/target
  - Closed trades history
  - Performance charts
  - Auto-refresh
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, date
from pathlib import Path
import sys

# Add parent directory to path so we can import config/settings
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from data.fetcher import get_daily_ohlcv


# ── Setup ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

PORTFOLIO_STATE_FILE = Path(__file__).parent.parent / "paper_portfolio_state.json"


@st.cache_data(ttl=60)
def load_portfolio_state():
    """Load the paper portfolio state from JSON."""
    if not PORTFOLIO_STATE_FILE.exists():
        return None
    try:
        with open(PORTFOLIO_STATE_FILE) as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading portfolio state: {e}")
        return None


@st.cache_data(ttl=3600)
def get_current_price(symbol: str):
    """Fetch current price for a symbol."""
    try:
        df = get_daily_ohlcv(symbol, outputsize="compact")
        if df is not None and len(df) > 0:
            return float(df["close"].iloc[0])
    except Exception as e:
        st.warning(f"Could not fetch price for {symbol}: {e}")
    return None


def format_currency(value):
    """Format a number as USD currency."""
    return f"${value:,.2f}" if value is not None else "N/A"


def format_percent(value):
    """Format a number as percentage."""
    color = "🟢" if value >= 0 else "🔴"
    return f"{color} {value:+.2f}%"


# ── Main dashboard ────────────────────────────────────────
st.title("📊 Trading Bot Dashboard")

# Sidebar controls
with st.sidebar:
    st.header("Controls")
    refresh_interval = st.slider(
        "Auto-refresh interval (seconds)",
        min_value=10, max_value=300, value=60, step=10
    )
    
    st.markdown("---")
    st.subheader("Portfolio Config")
    st.metric("Watchlist", ", ".join(settings.WATCHLIST))
    st.metric("Risk per trade", f"{settings.RISK_PER_TRADE_PCT}%")
    st.metric("Max open trades", settings.MAX_OPEN_TRADES)
    st.metric("Ollama model", settings.OLLAMA_MODEL)
    st.metric("Broker mode", settings.BROKER_MODE.upper())
    
    st.markdown("---")
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

# Load portfolio data
state = load_portfolio_state()

if state is None:
    st.warning("⚠️ No portfolio state found. Run `python main.py` to start trading.")
    st.stop()

broker_mode = state.get("broker", settings.BROKER_MODE)
if broker_mode == "webull":
    st.info("⚠️ Running in live Webull mode. Portfolio state is refreshed from your account.")

# Extract data from state
cash = state.get("cash", 0)
peak_value = state.get("peak_value", settings.PAPER_BALANCE)
positions_raw = state.get("positions", {})
positions = {}

if isinstance(positions_raw, dict):
    positions = positions_raw
elif isinstance(positions_raw, list):
    for pos in positions_raw:
        symbol = (pos.get("symbol") or pos.get("ticker") or pos.get("tickerSymbol") or pos.get("disSymbol"))
        if not symbol:
            continue
        positions[symbol] = pos

starting_balance = state.get("starting_balance", settings.PAPER_BALANCE)

# Calculate metrics
position_values = {}
for symbol, pos in positions.items():
    current_price = get_current_price(symbol)
    if current_price:
        position_values[symbol] = {
            "current_price": current_price,
            "value": pos["shares"] * current_price,
            "unrealised_pnl": pos["shares"] * (current_price - pos["entry_price"]),
        }

total_position_value = sum(p["value"] for p in position_values.values())
total_value = cash + total_position_value
daily_pnl = total_value - starting_balance
daily_pnl_pct = (daily_pnl / starting_balance) * 100
drawdown = ((peak_value - total_value) / peak_value) * 100

# ── Summary metrics ────────────────────────────────────────
st.subheader("Portfolio Summary")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Value", format_currency(total_value))

with col2:
    st.metric("Cash", format_currency(cash))

with col3:
    st.metric("P&L (unrealised)", format_percent(daily_pnl_pct))

with col4:
    st.metric("Max Drawdown", format_percent(drawdown))

with col5:
    st.metric("Open Trades", len(positions))

# ── Open positions ────────────────────────────────────────
st.subheader("📍 Open Positions")

if positions:
    positions_data = []
    for symbol, pos in positions.items():
        pv = position_values.get(symbol, {})
        current_price = pv.get("current_price", pos["entry_price"])
        unrealised_pnl = pv.get("unrealised_pnl", 0)
        unrealised_pct = (unrealised_pnl / (pos["shares"] * pos["entry_price"])) * 100 if pos["shares"] > 0 else 0
        
        positions_data.append({
            "Symbol": symbol,
            "Shares": pos["shares"],
            "Entry": format_currency(pos["entry_price"]),
            "Current": format_currency(current_price),
            "Stop": format_currency(pos["stop_price"]),
            "Target": format_currency(pos["target_price"]),
            "P&L $": format_currency(unrealised_pnl),
            "P&L %": format_percent(unrealised_pct),
            "Opened": pos["opened_at"][:10],
            "Reason": pos["entry_reason"][:50] + "..." if len(pos["entry_reason"]) > 50 else pos["entry_reason"],
        })
    
    df_positions = pd.DataFrame(positions_data)
    st.dataframe(df_positions, use_container_width=True, hide_index=True)
    
    # Position details expander
    with st.expander("Position Details"):
        for symbol, pos in positions.items():
            with st.container():
                pv = position_values.get(symbol, {})
                current_price = pv.get("current_price", pos["entry_price"])
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**{symbol}**")
                    st.metric("Entry Price", format_currency(pos["entry_price"]))
                    st.metric("Current Price", format_currency(current_price))
                
                with col2:
                    st.metric("Stop Loss", format_currency(pos["stop_price"]))
                    st.metric("Target", format_currency(pos["target_price"]))
                
                with col3:
                    entry_to_current = current_price - pos["entry_price"]
                    entry_to_stop = pos["entry_price"] - pos["stop_price"]
                    entry_to_target = pos["target_price"] - pos["entry_price"]
                    
                    st.metric("Entry → Current", format_currency(entry_to_current))
                    st.metric("Entry → Stop", format_currency(entry_to_stop))
                    st.metric("Entry → Target", format_currency(entry_to_target))
                
                st.divider()

else:
    st.info("No open positions. Waiting for signals...")

# ── Performance metrics ────────────────────────────────────
st.subheader("📈 Performance")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Starting Balance",
        format_currency(starting_balance)
    )

with col2:
    st.metric(
        "Current P&L",
        format_currency(daily_pnl),
        delta=format_percent(daily_pnl_pct)
    )

with col3:
    peak_to_current = ((total_value - peak_value) / peak_value) * 100
    st.metric(
        "Peak to Current",
        format_currency(total_value - peak_value),
        delta=format_percent(peak_to_current)
    )

# ── Status and info ────────────────────────────────────────
st.subheader("ℹ️ Bot Status")

col1, col2, col3 = st.columns(3)

with col1:
    status = "🟢 Running" if PORTFOLIO_STATE_FILE.exists() else "🔴 Idle"
    st.write(f"**Status:** {status}")

with col2:
    st.write(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

with col3:
    st.write(f"**Next Refresh:** ~{refresh_interval}s")

# Footer
st.divider()
st.caption(
    "📊 Trading Bot Dashboard | Paper Trading Mode | "
    f"Refresh rate: {refresh_interval}s | "
    f"Data source: Alpha Vantage + Ollama"
)

# Auto-refresh using streamlit's rerun mechanism
import time
time.sleep(refresh_interval)
st.rerun()
