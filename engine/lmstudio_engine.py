"""
engine/lmstudio_engine.py
────────────────────────
Sends the aggregated signal payload to a local LM Studio model
using the OpenAI-compatible `/v1/chat/completions` endpoint.
"""

import json
import requests
from typing import Optional
from dataclasses import dataclass

from config import settings


@dataclass
class TradeDecision:
    symbol:     str
    action:     str         # "buy", "sell", "hold", "skip"
    confidence: float       # 0.0 → 1.0
    stop_price: float
    target_price: float
    reasoning:  str         # LM Studio explanation
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


def _request_lmstudio(payload: dict) -> dict:
    url = settings.LM_STUDIO_HOST.rstrip("/") + "/v1/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def analyse(symbol: str, signals: list, portfolio_context: dict,
            current_price: float) -> Optional[TradeDecision]:
    """
    Send signals to LM Studio and return a trading decision.
    """

    payload = {
        "model": settings.LM_STUDIO_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyse the following signals for {symbol} "
                    f"and return your trading decision as JSON:\n\n"
                    f"{json.dumps({
                        'symbol': symbol,
                        'current_price': round(current_price, 2),
                        'signals': signals,
                        'active_signals_count': len(signals),
                        'bullish_count': sum(1 for s in signals if s.get('direction') == 'bullish'),
                        'bearish_count': sum(1 for s in signals if s.get('direction') == 'bearish'),
                        'portfolio': {
                            'cash_available': portfolio_context.get('cash', 0),
                            'open_positions': portfolio_context.get('open_positions', 0),
                            'daily_pnl_pct': portfolio_context.get('daily_pnl_pct', 0),
                            'max_drawdown': portfolio_context.get('max_drawdown', 0),
                        }
                    }, indent=2)}"
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }

    print(f"  [lmstudio] Analysing {symbol} with {len(signals)} signal(s)...")

    try:
        response = _request_lmstudio(payload)
        raw = json.dumps(response)

        # LM Studio OpenAI-compatible response shape
        choice = response.get("choices", [])[0]
        if not choice:
            raise ValueError("No choices returned from LM Studio")

        message = choice.get("message", {})
        raw_content = message.get("content", "")
        if not raw_content:
            raise ValueError("LM Studio returned empty message content")

        data = json.loads(raw_content)

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
            raw_response = raw_content,
        )

    except json.JSONDecodeError as e:
        print(f"  [lmstudio] JSON parse error for {symbol}: {e}")
        print(f"  [lmstudio] Raw response: {raw_content[:200] if 'raw_content' in locals() else '<<none>>'}")
        return None
    except Exception as e:
        print(f"  [lmstudio] Error calling model for {symbol}: {e}")
        print(f"  [lmstudio] Raw response: {raw_content[:200] if 'raw_content' in locals() else '<<none>>'}")
        return None
