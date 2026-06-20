# Trading Bot Dashboard

Live monitoring dashboard for your paper trading portfolio.

## Features

- **Portfolio Summary**: Total value, cash, P&L, max drawdown
- **Open Positions**: Entry/stop/target prices, unrealised P&L, entry reasoning
- **Position Details**: Deep dive into each position with price relationships
- **Performance Metrics**: Starting balance, cumulative P&L, peak-to-current analysis
- **Auto-Refresh**: Configurable refresh interval (10-300 seconds)
- **Current Prices**: Fetches live data from Webull

## Installation

Streamlit is already in `requirements.txt`. If not installed:

```bash
pip install streamlit
```

## Running the Dashboard

From the project root:

```bash
streamlit run dashboard/app.py
```

The dashboard will open in your browser at `http://localhost:8501`

## What It Shows

### Portfolio Summary
- **Total Value**: Cash + all open positions at current market prices
- **Cash**: Available buying power
- **P&L %**: Unrealised profit/loss as percentage of starting balance
- **Max Drawdown**: Peak-to-current decline
- **Open Trades**: Number of active positions

### Open Positions Table
- Symbol, shares, entry/current/stop/target prices
- Unrealised P&L in dollars and percentage
- When the position was opened
- The LM Studio reasoning that triggered the entry

### Position Details Expander
For each position:
- Price relationships (Entry → Current, Entry → Stop, Entry → Target)
- Helps you visualize the risk/reward setup

### Performance Metrics
- Starting balance (from settings)
- Current P&L
- Peak balance vs current

## How It Works

1. Reads `paper_portfolio_state.json` (created by `main.py`)
2. Fetches current prices from Webull for all open positions
3. Calculates unrealised P&L
4. Displays everything with auto-refresh

## Customization

Edit `dashboard/app.py` to:
- Change refresh interval (sidebar slider)
- Add more metrics or charts
- Change colors or layout
- Add trade history visualization

## Monitoring While Away

You can:
- Run the dashboard on a machine at home
- Share the URL via ngrok tunneling if needed
- Keep it open on a tablet or phone
- Set up alerts if you add more features

## Notes

- Dashboard reads-only (no trading decisions made here)
- Prices update in real-time from Webull
- Portfolio state syncs whenever `main.py` executes a trade
- Requires `.env` file with `WEBULL_EMAIL` and `WEBULL_PASSWORD` for live prices
