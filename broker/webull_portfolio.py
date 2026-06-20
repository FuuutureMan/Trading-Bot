import json
import time
from pathlib import Path
from typing import Optional

from webull import webull

from config import settings
from broker.base_portfolio import BasePortfolio


class WebullPortfolio(BasePortfolio):
    """Live Webull broker adapter using the webull package."""

    def __init__(self):
        self.webull = webull()
        self.trading_pin = settings.WEBULL_TRADING_PIN
        self._account_data = {}
        self._positions = []
        self._portfolio = {}
        self._logged_in = False
        self.STATE_FILE = Path(__file__).parent.parent / "paper_portfolio_state.json"

        self._login()
        self.refresh()

    @property
    def is_live(self) -> bool:
        return True

    def _login(self):
        if self.webull.is_logged_in():
            self._logged_in = True
            return

        print("  [webull] Logging in to Webull...")
        self.webull.login(
            username=settings.WEBULL_EMAIL,
            password=settings.WEBULL_PASSWORD,
            device_name=settings.WEBULL_DEVICE_NAME,
            save_token=False,
        )
        self._logged_in = self.webull.is_logged_in()

        if not self._logged_in:
            raise RuntimeError("Webull login failed. Check your credentials and MFA requirements.")

        if self.trading_pin:
            print("  [webull] Requesting trade token...")
            if not self.webull.get_trade_token(self.trading_pin):
                raise RuntimeError("Failed to obtain Webull trade token. Verify WEBULL_TRADING_PIN.")

    def refresh(self):
        """Refresh account and position data from Webull."""
        self._account_data = self.webull.get_account() or {}
        self._positions = self._account_data.get("positions", []) or []
        self._portfolio = self.webull.get_portfolio() or {}
        self._save_state()
        return self._account_data

    def _save_state(self):
        state = {
            "broker": "webull",
            "cash": round(float(self._portfolio.get("cashBalance", 0.0)), 2),
            "total_value": round(self.total_value(), 2),
            "peak_value": round(self.total_value(), 2),
            "daily_pnl_pct": round(float(self._portfolio.get("dailyGainLossPercent", 0.0)), 2),
            "weekly_pnl_pct": round(float(self._portfolio.get("weekGainLossPercent", 0.0)), 2),
            "max_drawdown": round(float(self._portfolio.get("maxDrawdownPercent", 0.0)) if self._portfolio.get("maxDrawdownPercent") is not None else 0.0, 2),
            "positions": [self._format_position(pos) for pos in self._positions],
        }
        try:
            with self.STATE_FILE.open("w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"  [webull] Could not save portfolio state: {e}")

    def _format_position(self, pos: dict) -> dict:
        symbol = (pos.get("symbol") or pos.get("tickerSymbol") or pos.get("disSymbol") or "").upper()
        shares = int(pos.get("quantity", pos.get("shares", 0)))
        avg_cost = pos.get("avgCost") or pos.get("cost") or pos.get("lastPrice") or 0.0
        entry_price = float(avg_cost) if avg_cost else 0.0
        return {
            "symbol": symbol,
            "shares": shares,
            "entry_price": round(entry_price, 2),
            "stop_price": pos.get("stop_price", 0.0),
            "target_price": pos.get("target_price", 0.0),
            "entry_reason": "Live Webull position",
        }

    def _find_position(self, symbol: str) -> Optional[dict]:
        for pos in self._positions:
            if str(pos.get("symbol", "")).upper() == symbol.upper():
                return pos
            if str(pos.get("tickerSymbol", "")).upper() == symbol.upper():
                return pos
            if str(pos.get("disSymbol", "")).upper() == symbol.upper():
                return pos
        return None

    def total_value(self, prices: dict = None) -> float:
        if "netLiquidation" in self._portfolio:
            return float(self._portfolio.get("netLiquidation", 0.0))
        if "totalMarketValue" in self._portfolio:
            cash = float(self._portfolio.get("cashBalance", 0.0))
            return cash + float(self._portfolio.get("totalMarketValue", 0.0))
        return float(self._portfolio.get("accountValue", 0.0))

    def open_trade_count(self) -> int:
        return len(self._positions)

    def has_position(self, symbol: str) -> bool:
        return self._find_position(symbol) is not None

    def summary(self) -> dict:
        cash = float(self._portfolio.get("cashBalance", 0.0))
        total_value = self.total_value()
        open_positions = self.open_trade_count()
        return {
            "cash": round(cash, 2),
            "total_value": round(total_value, 2),
            "open_positions": open_positions,
            "daily_pnl_pct": round(float(self._portfolio.get("dailyGainLossPercent", 0.0)), 2),
            "weekly_pnl_pct": round(float(self._portfolio.get("weekGainLossPercent", 0.0)), 2),
            "max_drawdown": 0.0,
            "total_trades": 0,
        }

    def open_long(self, symbol: str, shares: int, fill_price: float,
                  stop_price: float, target_price: float,
                  reason: str = "") -> bool:
        if shares < 1:
            print(f"  [webull] Cannot open {symbol}: invalid share count {shares}")
            return False

        if not self._logged_in:
            raise RuntimeError("Webull is not logged in.")

        self.webull.get_trade_token(self.trading_pin)
        print(f"  [webull] Placing buy order for {symbol} ({shares} shares @ ${fill_price:.2f})...")
        response = self.webull.place_order(
            stock=symbol,
            price=fill_price,
            action="BUY",
            orderType="LMT",
            enforce="GTC",
            quant=shares,
            outsideRegularTradingHour=False,
        )

        success = bool(response and (response.get("resultCode") in {0, "0"} or response.get("success") is True))
        if not success:
            print(f"  [webull] Order failed: {response}")
            return False

        time.sleep(1)
        self.refresh()
        return True

    def close_position(self, symbol: str, fill_price: float,
                       reason: str = "") -> Optional[dict]:
        position = self._find_position(symbol)
        if not position:
            print(f"  [webull] No position to close for {symbol}")
            return None

        shares = int(position.get("quantity", position.get("shares", 0)))
        if shares < 1:
            print(f"  [webull] No shares found for {symbol}")
            return None

        self.webull.get_trade_token(self.trading_pin)
        print(f"  [webull] Placing sell order for {symbol} ({shares} shares)...")
        response = self.webull.place_order(
            stock=symbol,
            price=0,
            action="SELL",
            orderType="MKT",
            enforce="GTC",
            quant=shares,
            outsideRegularTradingHour=False,
        )
        self.refresh()
        return response
