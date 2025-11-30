# bot.py
import os
import time
from datetime import datetime, timezone
from typing import Any

import logging
import pandas as pd
from dotenv import load_dotenv
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import before_model, after_model, wrap_tool_call, after_agent, before_agent
from langchain_core.tools import tool
from langgraph.runtime import Runtime

load_dotenv()

# ---- 0) OKX (Demo) 客户端：现货、模拟盘 ----
from okx_trade_agent.utils.get_exchange import get_exchange

okx = get_exchange()

SYMBOL = "BTC/USDT"
TIMEFRAME = "1m"
SHORT, LONG = 20, 50

# ---- 1) 工具封装（严格描述+参数，便于LLM正确调用） ----
@tool
def get_price(symbol: str) -> float:
    """Return latest mid price for a spot symbol. Only supports BTC/USDT in this demo."""
    if symbol != SYMBOL:
        raise ValueError("Only BTC/USDT allowed in this demo.")
    ticker = okx.fetch_ticker(symbol)
    # 取买一/卖一均价近似
    bid, ask = ticker.get("bid"), ticker.get("ask")
    if bid and ask:
        return (bid + ask) / 2
    return ticker["last"]

@tool
def get_balance(asset: str) -> dict:
    """Return free and total balance for given asset (e.g., 'USDT' or 'BTC')."""
    bal = okx.fetch_balance()
    info = bal.get(asset, {})
    return {"asset": asset, "free": float(info.get("free", 0)), "total": float(info.get("total", 0))}

@tool
def place_market_buy_usdt(symbol: str, usdt: float) -> dict:
    """Place a market BUY using a USDT cash amount. Max 20 USDT per trade in this demo."""
    if symbol != SYMBOL:
        raise ValueError("Only BTC/USDT allowed.")
    if usdt <= 0 or usdt > 20:
        raise ValueError("usdt must be (0, 20].")
    price = get_price.invoke({"symbol": symbol})
    amount = usdt / price
    amount = okx.amount_to_precision(symbol, amount)
    order = okx.create_order(symbol, "market", "buy", float(amount))
    return {"order_id": order["id"], "side": "buy", "filled": order.get("filled", None)}

@tool
def place_market_sell_all(symbol: str) -> dict:
    """Sell all available base asset at market (e.g., sell all BTC)."""
    if symbol != SYMBOL:
        raise ValueError("Only BTC/USDT allowed.")
    bal = okx.fetch_balance()
    base = "BTC"
    amt = float(bal.get(base, {}).get("free", 0))
    if amt <= 0:
        return {"status": "no_position"}
    amt = okx.amount_to_precision(symbol, amt)
    order = okx.create_order(symbol, "market", "sell", float(amt))
    return {"order_id": order["id"], "side": "sell", "filled": order.get("filled", None)}

@tool
def get_signal(symbol: str, timeframe: str = TIMEFRAME, short: int = SHORT, long: int = LONG) -> dict:
    """Return a simple SMA crossover signal for the symbol and timeframe."""
    ohlcv = okx.fetch_ohlcv(symbol, timeframe=timeframe, limit=max(short, long) + 2)
    df = pd.DataFrame(ohlcv, columns=["ts","o","h","l","c","v"])
    df["sma_s"] = df["c"].rolling(short).mean()
    df["sma_l"] = df["c"].rolling(long).mean()
    sig = "hold"
    if len(df) >= long + 1:
        if df["sma_s"].iloc[-2] <= df["sma_l"].iloc[-2] and df["sma_s"].iloc[-1] > df["sma_l"].iloc[-1]:
            sig = "golden_cross_buy"
        elif df["sma_s"].iloc[-2] >= df["sma_l"].iloc[-2] and df["sma_s"].iloc[-1] < df["sma_l"].iloc[-1]:
            sig = "death_cross_sell"
    return {"signal": sig, "price": float(df["c"].iloc[-1])}


@before_agent
def log_before_agent(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    print(f"Agent begin !")
    return None

@after_agent
def log_after_agent(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    logging.info("Agent end !")
    return None

@before_model
def log_before_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    print(f"About to call model with {state['messages'][-1].content} messages")
    return None

@after_model
def log_after_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    logging.info(state["messages"][-1].content)
    return None

@wrap_tool_call
def wrap_tool_call(request, handler):
    logging.info(f"Calling tool request: {request}")

    return handler(request)

TOOLS = [get_price, get_balance, get_signal, place_market_buy_usdt, place_market_sell_all]
MIDDLEWARE = [wrap_tool_call, log_before_model, log_before_agent, log_after_model, log_after_agent]
# ---- 2) 代理（决策层） + 护栏 ----
SYSTEM = """你是一个加密现货交易小助手，只能交易 BTC/USDT（现货、无杠杆、模拟盘）。
硬性规则：
- 仅当 signal == 'golden_cross_buy' 才能考虑买入；仅当 signal == 'death_cross_sell' 才能考虑卖出；否则 HOLD。
- 单笔买入金额上限 20 USDT；当 USDT 可用余额 < 5 USDT 时，不得买入。
- 卖出使用 place_market_sell_all，一次清仓。
- 每次必须先查询 get_balance('USDT') 和 get_balance('BTC') 再决定下单。
- 绝不使用除提供的工具外的任何操作；绝不交易除 BTC/USDT 外的标的。
输出时务必调用对应工具完成动作；若不交易则说明原因并结束。
"""

agent = create_agent(model="openai:deepseek-chat", tools= TOOLS, system_prompt=SYSTEM
                     , middleware=MIDDLEWARE)

def loop_once():
    now = datetime.now(timezone.utc).isoformat()
    messages = {"messages":[
        {"role":"user", "content": f"当前时间：{now}\n请先调用 get_signal('{SYMBOL}')，再根据规则决定。"}
    ]}

    response = agent.invoke(messages)
    print(response)



if __name__ == "__main__":
    loop_once()
