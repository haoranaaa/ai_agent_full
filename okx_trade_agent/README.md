# OKX AI Trade Agent

An LLM-driven helper that reads perpetual market/context data, prompts a model for a structured decision, and (optionally) executes perp orders on OKX (simulated by default).

## Quickstart
- Clone repo, create venv, install deps: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (or `pip install ccxt langchain langgraph python-dotenv pandas` per root instructions).
- Copy `.env_example` → `.env`, fill `OKX_*` + `OPENAI_*` keys. Set `OKX_SIMULATED=1` for demo, `0` for live.
- Run one-off agent call: `python okx_trade_agent/price_agent.py` (loads symbols from `OKX_SYMBOLS`, defaults to BTC/DOGE/ETH/SOL perps).
- Run periodic loop (30m): `python okx_trade_agent/auto_trade.py` (feeds snapshots + account to the agent).

## How It Works
- Prompts: `okx_trade_agent/prompts/system_prompt.txt` (agent rules/tools), `okx_trade_agent/prompts/perp_user_prompt.txt` (market/account template).
- Data prep (per loop in `okx_trade_agent/auto_trade.py`):
  - Fetch perpetual snapshots via `utils/perp_market.py` (prices, EMA/MACD/RSI/ATR, OI, funding).
  - Fetch balances/positions via `utils/get_exchange.py` → `utils/okx_client.py`.
  - Build the user prompt block (market + account + structured positions JSON).
- Decision layer: `okx_trade_agent/price_agent.py` creates a LangChain agent (`openai:deepseek-chat`) with tools:  
  - `get_recent_candles`  
  - `place_okx_order` (perp limit + TP/SL; `usdt_amount` is margin)  
  - `close_position` (reduce-only limit, closes existing perp side)  
  - `await_price_trigger` (poll-wait trigger)  
  System prompt requires structured output (`ModelResult` in `utils/model_decision.py`).
- Execution: `auto_trade.py` currently only logs the structured decision; hook actual order mapping as needed.

## Configuration
- `.env` keys: `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, optional `OKX_SIMULATED` (default `1`).
- Symbols: set `OKX_SYMBOLS` (comma-separated, e.g., `BTC/USDT:USDT,ETH/USDT:USDT`); fallback is `utils/symbols.py::DEFAULT_PERP_SYMBOLS`.
- Default settlement: `OKX_DEFAULT_TYPE=swap` set in `auto_trade.py` when run as main.
- Prompts and tooling can be adjusted in `prompts/system_prompt.txt` and `prompts/perp_user_prompt.txt` without touching code.

## Key Modules
- Market/account: `utils/perp_market.py`, `utils/okx_client.py`, `utils/get_exchange.py`.
- Trading tools: `utils/okx_trade_tools.py` (place/cancel, TP/SL, close position).
- Agent wiring: `price_agent.py` (tools, system prompt, symbols), `auto_trade.py` (scheduler + prompt builder).
- Models/schema: `utils/model_decision.py`.

## Typical Run (auto_trade)
- Start loop (`python okx_trade_agent/auto_trade.py`).
- Every 30 minutes: refresh snapshots → build prompt → call `price_agent` → log structured decision.
- You can intercept the decision to fan-out real orders (e.g., map `signal` to `place_okx_order`/`close_position`).

## Notes
- Simulated by default; flip `OKX_SIMULATED=0` only when you intend to trade live.
- Tools are reduce-only for closes; `place_okx_order` expects a positive margin (`usdt_amount`) and computes contracts internally.
- Keep prompts tight—model behavior (hold vs. trade, wait vs. immediate) is largely governed by `system_prompt.txt`.
