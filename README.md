# Trading Bot

A simple Python-based trading bot that uses Webull for market data and optional live execution, plus LM Studio as the decision engine.

## What this project does

- Fetches stock price data from Webull
- Runs technical signal checks using the `MomentumSkill`
- Sends signals to a local LM Studio model for a decision
- Applies risk management rules
- Executes trades either in simulated paper mode or live on Webull
- Provides a dashboard under `dashboard/app.py`

## Important files

- `main.py` - bot entry point, runs one scan cycle
- `config/settings.py` - loads `.env` and contains bot settings
- `data/fetcher.py` - gets OHLCV price data from Webull
- `skills/momentum.py` - current trading signal logic
- `engine/lmstudio_engine.py` - calls LM Studio for buy/sell decisions
- `broker/` - broker interface and Webull live trading adapter
- `dashboard/app.py` - Streamlit dashboard UI
- `paper_portfolio_state.json` - simulated portfolio state for paper trading

## .env file

This project uses a `.env` file for credentials and configuration. Do not share `.env` publicly.

### Required values

- `WEBULL_EMAIL` - your Webull login email
- `WEBULL_PASSWORD` - your Webull login password
- `BROKER_MODE` - `paper` or `webull`
- `WATCHLIST` - comma-separated list of tickers to scan
- `LM_STUDIO_MODEL` - model name for LM Studio (default: `mistral`)
- `LM_STUDIO_HOST` - local LM Studio host URL (default: `http://127.0.0.1:1234`)

### Optional but recommended

- `WEBULL_TRADING_PIN` - required only if `BROKER_MODE=webull`
- `PAPER_BALANCE` - starting cash for paper trading
- `RISK_PER_TRADE_PCT` - portfolio risk per trade
- `MAX_OPEN_TRADES` - maximum open positions

## Setup

1. Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

3. Edit `.env` with your credentials and settings.

4. Run the bot:

```bash
python main.py
```

## Running the dashboard

If you want to view the dashboard, run:

```bash
streamlit run dashboard/app.py
```

## Paper trading vs live trading

- `BROKER_MODE=paper`:
  - simulates trades in `paper_portfolio_state.json`
  - good for learning and testing
- `BROKER_MODE=webull`:
  - places trades on your live Webull account
  - `WEBULL_TRADING_PIN` is required

## Notes for beginners

- Use `paper` mode first until you understand how the bot behaves.
- Keep `WEBULL_EMAIL` and `WEBULL_PASSWORD` private.
- The bot currently scans the symbols in `WATCHLIST`.
- You can change the watchlist to other tickers in `.env`.

## Troubleshooting

- If the bot fails on startup, check `.env` for missing values
- If the bot cannot connect to LM Studio, verify `LM_STUDIO_HOST`
- If the bot cannot fetch data, verify your Webull credentials

## Dashboard docs

There is also a dashboard guide in `dashboard/README.md` with more UI details.
