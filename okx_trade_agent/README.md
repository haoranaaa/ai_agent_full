# OKX AI Trade Agent

构建一个 AI 驱动的自动化交易系统，目标是跑出超越普通定存利息水平的稳健收益。在 OKX 模拟/永续环境里，结合实时行情、账户信息和大语言模型的决策能力，自动执行低频、风险可控的交易策略。

## 项目构成
- `okx_trade_agent/price_agent.py`：最小化的 LLM Agent，读取配置的交易对（默认 BTC、DOGE、ETC、SOL 永续），拉取 3m/4h 行情与账户数据，组装 prompt 调用模型。
- `okx_trade_agent/auto_trade.py`：周期调度入口（默认 30 分钟循环），生成用户 prompt，调用 Agent 并预留执行交易的入口。
- `okx_trade_agent/utils/`：
  - `perp_market.py`：永续行情抓取与指标计算（EMA20/50、MACD、RSI7/14、ATR3/14、成交量、资金费率、持仓量）。
  - `price_tool.py`：通用 K 线工具，支持 1m/3m/30m，多标的，输出最近 10 根 OHLCV。
  - `model_decision.py`：模型输出的结构化定义（action: buy/sell_all/hold/wait 等）。
  - 其余：`get_exchange.py`（OKX 连接与缓存）、`logger.py`、`market_data.py` 等。
- `okx_trade_agent/prompts/`：系统提示与用户提示模板（spot/perp 版本集中管理）。
- `langgraph.json`：注册 agent 图入口。

## 当前做法（简版）
1. 默认符号：`BTC/USDT:USDT, DOGE/USDT:USDT, ETC/USDT:USDT, SOL/USDT:USDT`（可通过环境变量 `OKX_SYMBOLS` 配置）。
2. 数据侧：抓取永续 3m/4h K 线，计算 EMA/MACD/RSI/ATR/资金费率/持仓量，并格式化（最多 10 位有效数字）。
3. Prompt：采用 `perp_user_prompt.txt` 模板，包含最新 10 根 3m K 线序列和 4h 上下文 + 账户余额/收益率（基于启动时 USDT 基线）。
4. 模型：`openai:deepseek-chat`，系统约束在 `system_prompt.txt`，输出结构化 JSON（见 `ModelDecision`）。
5. 运行：设置 `.env`（OKX key，`OKX_DEFAULT_TYPE=swap`），可选 `OKX_SYMBOLS`，执行 `python okx_trade_agent/auto_trade.py` 周期运行；或 `python okx_trade_agent/price_agent.py` 单次调用。

> 下一步：将模型的决策 JSON 映射到具体下单工具，完善风控与持仓管理，并根据需要调整系统提示以适配永续多标的策略。
