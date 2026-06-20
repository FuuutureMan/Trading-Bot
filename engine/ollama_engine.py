"""
engine/ollama_engine.py
────────────────────────
Sends the aggregated signal payload to the local Ollama model
and parses a structured trading decision back out.

The model receives a tight JSON summary of all active signals
for a symbol and returns a JSON decision — never raw price data.
This keeps the context window small and the reasoning focused.
"""

import json
import ollama
from typing import Optional
from dataclasses import dataclass

from config import settings

OLLAMA_CLIENT = ollama.Client(host=settings.OLLAMA_HOST)


@dataclass
class TradeDecision:
    symbol:     str
    action:     str         # "buy", "sell", "hold", "skip"
    confidence: float       # 0.0 → 1.0
    stop_price: float
    target_price:float
    reasoning:  str         # Ollama's explanation
    raw_response: str = ""  # Full model output for the journal


SYSTEM_PROMPT = """You are a disciplined swing trading analyst.
You receive a JSON payload containing technical signals for a stock.
Your job is to evaluate the signals and decide whether to trade.

Rules you must follow:
- Only recommend BUY when multiple signals align bullishly
- Only recommend SELL (exit) when a position should be closed
- Use HOLD when a position should stay open and be monitored
- Use SKIP when signals are mixed, weak, or insufficient
- Always provide a specific stop price and target price
- Be conservative — a missed trade is better than a bad trade

Respond ONLY with valid JSON in this exact format:
{
  "action": "buy" | "sell" | "hold" | "skip",
  "confidence": 0.0 to 1.0,
  "stop_price": float,
  "target_price": float,
  "reasoning": "concise explanation under 100 words"
}
No other text. No markdown. Just the JSON object."""


def _safe_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def analyse(symbol: str, signals: list, portfolio_context: dict,
            current_price: float) -> Optional[TradeDecision]:
    """
    Send signals to Ollama and get a trading decision back.

    Parameters
    ----------
    symbol           : ticker being analysed
    signals          : list of Signal.to_dict() from all skills
    portfolio_context: summary dict from PaperPortfolio.summary()
    current_price    : latest price for the symbol

    Returns a TradeDecision, or None if the model call fails.
    """

    # Build the user message payload
    payload = {
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "signals": signals,
        "active_signals_count": len(signals),
        "bullish_count": sum(1 for s in signals if s.get("direction") == "bullish"),
        "bearish_count": sum(1 for s in signals if s.get("direction") == "bearish"),
        "portfolio": {
            "cash_available": portfolio_context.get("cash", 0),
            "open_positions": portfolio_context.get("open_positions", 0),
            "daily_pnl_pct":  portfolio_context.get("daily_pnl_pct", 0),
            "max_drawdown":   portfolio_context.get("max_drawdown", 0),
        }
    }

    user_message = (
        f"Analyse the following signals for {symbol} "
        f"and return your trading decision as JSON:\n\n"
        f"{json.dumps(payload, indent=2)}"
    )

    print(f"  [ollama] Analysing {symbol} with {len(signals)} signal(s)...")

    try:
        response = OLLAMA_CLIENT.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            format="json",          # Ask the model to enforce JSON output
            options={"temperature": 0.1}  # Low temp = more consistent decisions
        )

        raw = response["message"]["content"]

        # Parse the JSON response
        data = json.loads(raw)

        action = data.get("action", "skip").lower()
        confidence = _safe_float(data.get("confidence"), 0.0)
        stop_price = _safe_float(data.get("stop_price"), None)
        target_price = _safe_float(data.get("target_price"), None)
        reasoning = data.get("reasoning", "")

        if action in {"buy", "sell"} and (stop_price is None or target_price is None):
            raise ValueError(
                f"Missing required stop_price/target_price for action '{action}'"
            )

        if stop_price is None:
            stop_price = 0.0
        if target_price is None:
            target_price = 0.0

        return TradeDecision(
            symbol       = symbol,
            action       = action,
            confidence   = confidence,
            stop_price   = stop_price,
            target_price = target_price,
            reasoning    = reasoning,
            raw_response = raw,
        )

    except json.JSONDecodeError as e:
        print(f"  [ollama] JSON parse error for {symbol}: {e}")
        print(f"  [ollama] Raw response: {raw[:200]}")
        return None
    except Exception as e:
        print(f"  [ollama] Error calling model for {symbol}: {e}")
        print(f"  [ollama] Raw response: {raw[:200]}")
        return None
