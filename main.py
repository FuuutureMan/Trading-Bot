"""
main.py
────────
Entry point for the swing trading bot.

Run with:
    python main.py

What it does each scan cycle:
  1. Fetch fresh price data for the watchlist
  2. Run all skill sensors on each symbol
    3. If signals exist, ask LM Studio to make a decision
    4. Pass LM Studio's decision through the Risk Manager
  5. If approved, execute on the paper portfolio
  6. Log everything to the journal
"""

import time
from datetime import datetime

from config import settings
from data.fetcher import rate_limited_fetch
from skills.momentum import MomentumSkill
from risk.manager import RiskManager
from broker import create_portfolio
from engine import lmstudio_engine as decision_engine

# ── Initialise components ──────────────────────────────────
portfolio = create_portfolio()
risk_mgr  = RiskManager(portfolio)

# Register all active skills
SKILLS = [
    MomentumSkill(),
    # TrendSkill(),       ← add as we build them
    # PriceStructureSkill(),
    # VolumeSkill(),
]


def run_scan():
    """One full scan cycle across the entire watchlist."""
    print(f"\n{'='*55}")
    print(f"  Scan started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Watchlist: {', '.join(settings.WATCHLIST)}")
    print(f"  Portfolio: ${portfolio.total_value():,.2f} | "
          f"{portfolio.open_trade_count()} open trades")
    print(f"{'='*55}")

    # ── Step 1: Fetch price data ─────────────────────────────
    print("\n[1/4] Fetching price data...")
    data = rate_limited_fetch(settings.WATCHLIST)

    # ── Step 2: Run skill sensors ────────────────────────────
    print("\n[2/4] Running skill sensors...")
    all_signals = {}   # { symbol: [Signal, ...] }

    for symbol, df in data.items():
        if df is None:
            continue

        symbol_signals = []
        current_price  = float(df["close"].iloc[0])

        for skill in SKILLS:
            signal = skill.safe_analyse(symbol, df)
            if signal is not None:
                symbol_signals.append(signal)
                print(f"  ✓ {symbol} [{skill.name}] {signal.direction} "
                      f"{signal.signal} (strength={signal.strength:.2f})")

        if symbol_signals:
            all_signals[symbol] = symbol_signals

    if not all_signals:
        print("  No signals found this cycle.")
        return

    # ── Step 3: LM Studio decision engine ─────────────────────
    print(f"\n[3/4] Asking LM Studio about {len(all_signals)} symbol(s)...")
    portfolio_ctx = portfolio.summary()

    for symbol, signals in all_signals.items():
        df            = data[symbol]
        current_price = float(df["close"].iloc[0])

        # Don't analyse symbols we're already holding
        if portfolio.has_position(symbol):
            print(f"  Skipping {symbol} — already in portfolio")
            continue

        decision = decision_engine.analyse(
            symbol          = symbol,
            signals         = [s.to_dict() for s in signals],
            portfolio_context = portfolio_ctx,
            current_price   = current_price,
        )

        if decision is None:
            print(f"  [{symbol}] No decision returned from LM Studio")
            continue

        print(f"  [{symbol}] LM Studio says: {decision.action.upper()} "
              f"(confidence={decision.confidence:.2f})")
        print(f"    Reasoning: {decision.reasoning}")

        # ── Step 4: Risk Manager gate ────────────────────────
        if decision.action != "buy":
            print(f"  [{symbol}] Action is '{decision.action}' — no order needed")
            continue

        print(f"\n[4/4] Risk Manager validating {symbol}...")
        result = risk_mgr.validate(
            symbol      = symbol,
            entry_price = current_price,
            stop_price  = decision.stop_price,
            direction   = "long",
        )

        print(f"  {'✓ APPROVED' if result.approved else '✗ REJECTED'}: {result.reason}")

        # ── Step 5: Execute on paper portfolio ───────────────
        if result.approved:
            portfolio.open_long(
                symbol       = symbol,
                shares       = result.shares,
                fill_price   = current_price,
                stop_price   = result.stop_price,
                target_price = result.target_price,
                reason       = decision.reasoning,
            )

    # ── Final summary ────────────────────────────────────────
    print(f"\n{'─'*55}")
    s = portfolio.summary()
    print(f"  Portfolio after scan:")
    print(f"    Total value : ${s['total_value']:>10,.2f}")
    print(f"    Cash        : ${s['cash']:>10,.2f}")
    print(f"    Open trades : {s['open_positions']}")
    print(f"    Daily P&L   : {s['daily_pnl_pct']:>+.2f}%")
    print(f"    Max drawdown: {s['max_drawdown']:>.2f}%")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    print("\n  Swing Trading Bot starting up...")

    # Validate config before anything else
    if not settings.validate():
        print("\n  Fix the above config errors in your .env file first.")
        exit(1)

    print(f"  Model     : {settings.LM_STUDIO_MODEL}")
    print(f"  Watchlist : {', '.join(settings.WATCHLIST)}")
    print(f"  Risk/trade: {settings.RISK_PER_TRADE_PCT}%")
    print(f"  Broker    : {settings.BROKER_MODE}")

    # Run one scan immediately on startup
    run_scan()
