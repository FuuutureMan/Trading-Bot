import json
from pathlib import Path
from typing import Optional

from config import settings

STATE_FILE = Path(__file__).parent.parent / "paper_portfolio_state.json"


def load_paper_portfolio_state() -> Optional[dict]:
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def format_portfolio_state(portfolio: dict, positions: list[dict]) -> dict:
    return {
        "cash": round(float(portfolio.get("cashBalance", 0.0)), 2),
        "total_value": round(float(
            portfolio.get("netLiquidation", 0.0)
            or (float(portfolio.get("cashBalance", 0.0)) + float(portfolio.get("totalMarketValue", 0.0)))
            or float(portfolio.get("accountValue", 0.0))
        ), 2),
        "open_positions": len(positions),
        "daily_pnl_pct": round(float(portfolio.get("dailyGainLossPercent", 0.0)), 2),
        "weekly_pnl_pct": round(float(portfolio.get("weekGainLossPercent", 0.0)), 2),
        "max_drawdown": round(float(portfolio.get("maxDrawdownPercent", 0.0)) if portfolio.get("maxDrawdownPercent") is not None else 0.0, 2),
        "positions": positions,
    }
