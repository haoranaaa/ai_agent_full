# -*- coding: utf-8 -*-
"""
OKX 交易工具模块
用于提供各类与交易相关的工具函数
"""
import os
from dotenv import load_dotenv
import logging
from typing import Any, Dict

import pandas as pd
from langchain_core.tools import tool

from okx_trade_agent.utils.get_exchange import get_exchange
from okx_trade_agent.utils.logger import get_logger


# 获取项目根目录路径（即 .env 所在位置）
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))

# 加载根目录的 .env
load_dotenv(os.path.join(ROOT_DIR, ".env"))
# 配置日志输出格式
logger = get_logger(__name__)

# 常量定义
SYMBOL = "BTC/USDT"
TIMEFRAME = "1m"
SHORT, LONG = 20, 50

# ---- 工具函数 ----
@tool
def get_price(symbol: str) -> float:
    """获取指定交易对的最新中间价。

    参数:
        symbol: 交易对代码，例如 'BTC/USDT'

    返回:
        float: 买一卖一的平均价

    异常:
        ValueError: 当交易对不是 BTC/USDT 时抛出
    """
    logger.info(f"Getting price - Symbol: {symbol}")
    
    if symbol != SYMBOL:
        error_msg = f"Only BTC/USDT trading pair supported, got: {symbol}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        okx = get_exchange()
        ticker = okx.fetch_ticker(symbol)
        logger.info(f"Ticker data: {ticker}")
        
        # 使用买一卖一平均价
        bid, ask = ticker.get("bid"), ticker.get("ask")
        if bid and ask:
            price = (bid + ask) / 2
            logger.info(f"Mid price: ({bid} + {ask}) / 2 = {price}")
            return price
        else:
            price = ticker["last"]
            logger.info(f"Using last price: {price}")
            return price
    except Exception as e:
        logger.error(f"Failed to get price: {str(e)}")
        raise

@tool
def get_balance(asset: str) -> Dict[str, Any]:
    """查询指定资产的账户余额。

    参数:
        asset: 资产代码，例如 'USDT' 或 'BTC'

    返回:
        Dict: 余额信息
            {
                "asset": str,
                "free": float,
                "total": float
            }

    异常:
        Exception: 拉取余额失败时抛出
    """
    logger.info(f"Getting balance - Asset: {asset}")
    
    try:
        okx = get_exchange()
        bal = okx.fetch_balance()
        logger.info(f"Full balance info: {bal}")
        
        info = bal.get(asset, {})
        result = {
            "asset": asset,
            "free": float(info.get("free", 0)),
            "total": float(info.get("total", 0))
        }
        
        logger.info(f"Asset {asset} balance: free={result['free']}, total={result['total']}")
        return result
    except Exception as e:
        logger.error(f"Failed to get balance: {str(e)}")
        raise

@tool
def place_market_buy_usdt(symbol: str, usdt: float) -> Dict[str, Any]:
    """使用 USDT 下市价买单。

    参数:
        symbol: 交易对代码，必须为 'BTC/USDT'
        usdt: 购买所用 USDT 数量，范围为 (0, 20]

    返回:
        Dict: 订单信息
            {
                "order_id": str,
                "side": str,
                "filled": float 或 None
            }

    异常:
        ValueError: 入参不合法时抛出
        Exception: 下单失败时抛出
    """
    logger.info(f"Market buy - Symbol: {symbol}, USDT: {usdt}")
    
    if symbol != SYMBOL:
        error_msg = f"Only BTC/USDT trading pair supported, got: {symbol}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    if usdt <= 0 or usdt > 20:
        error_msg = f"USDT amount must be in (0, 20], got: {usdt}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        okx = get_exchange()
        
        # 获取当前价格
        price = get_price.invoke({"symbol": symbol})
        logger.info(f"Current price: {price}")
        
        # 计算下单数量
        amount = usdt / price
        amount = okx.amount_to_precision(symbol, amount)
        logger.info(f"Calculated amount: {usdt} / {price} = {amount}")
        
        # 提交订单
        order = okx.create_order(symbol, "market", "buy", float(amount))
        logger.info(f"Order successful: {order}")
        
        return {
            "order_id": order["id"],
            "side": "buy",
            "filled": order.get("filled", None)
        }
    except Exception as e:
        logger.error(f"Buy order failed: {str(e)}")
        raise

@tool
def place_market_sell_all(symbol: str) -> Dict[str, Any]:
    """将可用的基础资产全部以市价卖出。

    参数:
        symbol: 交易对代码，必须为 'BTC/USDT'

    返回:
        Dict: 订单信息
            {
                "status": str,  # "no_position" 或下单结果
                "order_id": str 或 None,
                "side": str 或 None,
                "filled": float 或 None
            }

    异常:
        ValueError: 交易对不是 BTC/USDT 时抛出
        Exception: 卖单失败时抛出
    """
    logger.info(f"Market sell - Symbol: {symbol}")
    
    if symbol != SYMBOL:
        error_msg = f"Only BTC/USDT trading pair supported, got: {symbol}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        okx = get_exchange()
        
        # 获取 BTC 余额
        bal = okx.fetch_balance()
        base = "BTC"
        amt = float(bal.get(base, {}).get("free", 0))
        
        logger.info(f"BTC balance: {amt}")
        
        if amt <= 0:
            logger.info("No BTC to sell")
            return {"status": "no_position"}
        
        # 处理交易所精度要求
        amt = okx.amount_to_precision(symbol, amt)
        logger.info(f"Amount after precision: {amt}")
        
        # 提交卖出订单
        order = okx.create_order(symbol, "market", "sell", float(amt))
        logger.info(f"Sell order successful: {order}")
        
        return {
            "order_id": order["id"],
            "side": "sell",
            "filled": order.get("filled", None)
        }
    except Exception as e:
        logger.error(f"Sell order failed: {str(e)}")
        raise

@tool
def get_signal(symbol: str, timeframe: str = TIMEFRAME, short: int = SHORT, long: int = LONG) -> Dict[str, Any]:
    """获取基于 SMA 的金叉/死叉信号。

    参数:
        symbol: 交易对代码
        timeframe: K 线周期，默认 '1m'
        short: 短周期 SMA，默认 20
        long: 长周期 SMA，默认 50

    返回:
        Dict: 信号信息
            {
                "signal": str,  # 可为 'golden_cross_buy'、'death_cross_sell' 或 'hold'
                "price": float
            }

    异常:
        Exception: 拉取行情或计算失败时抛出
    """
    logger.info(f"Getting signal - Symbol: {symbol}, Timeframe: {timeframe}, Short: {short}, Long: {long}")
    
    try:
        okx = get_exchange()
        
        # 获取 OHLCV 数据
        limit = max(short, long) + 2
        ohlcv = okx.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        logger.info(f"Fetched {len(ohlcv)} K-line data points")
        
        # 转换为 DataFrame
        df = pd.DataFrame(ohlcv, columns=["ts", "o", "h", "l", "c", "v"])
        logger.info(f"Latest price: {df['c'].iloc[-1]}")
        
        # 计算 SMA
        df["sma_s"] = df["c"].rolling(short).mean()
        df["sma_l"] = df["c"].rolling(long).mean()
        logger.info(f"Short SMA: {df['sma_s'].iloc[-1]:.2f}, Long SMA: {df['sma_l'].iloc[-1]:.2f}")
        
        # 判断信号
        sig = "hold"
        if len(df) >= long + 1:
            # 金叉: 短期均线从下向上穿越长期均线
            if (df["sma_s"].iloc[-2] <= df["sma_l"].iloc[-2] and
                df["sma_s"].iloc[-1] > df["sma_l"].iloc[-1]):
                sig = "golden_cross_buy"
                logger.info("Signal: Golden cross - Buy")
            # 死叉: 短期均线从上向下跌破长期均线
            elif (df["sma_s"].iloc[-2] >= df["sma_l"].iloc[-2] and
                  df["sma_s"].iloc[-1] < df["sma_l"].iloc[-1]):
                sig = "death_cross_sell"
                logger.info("Signal: Death cross - Sell")
            else:
                logger.info("Signal: Hold")
        
        return {
            "signal": sig,
            "price": float(df["c"].iloc[-1])
        }
    except Exception as e:
        logger.error(f"Failed to get signal: {str(e)}")
        raise

# 工具列表
TOOLS = [get_price, get_balance, get_signal, place_market_buy_usdt, place_market_sell_all]

# ---- 调试与测试函数 ----
def debug_all_tools():
    """调试所有工具函数"""
    logger.info("=" * 60)
    logger.info("Starting tool debugging")
    logger.info("=" * 60)
    
    try:
        # 1. 测试 get_price
        logger.info("\n[1] Testing get_price")
        price = get_price.invoke({"symbol": "BTC/USDT"})
        logger.info(f"✓ Price retrieved: {price}")
        
        # 2. 测试 get_balance
        logger.info("\n[2] Testing get_balance")
        usdt_balance = get_balance.invoke({"asset": "USDT"})
        logger.info(f"✓ USDT balance: {usdt_balance}")
        btc_balance = get_balance.invoke({"asset": "BTC"})
        logger.info(f"✓ BTC balance: {btc_balance}")
        
        # 3. 测试 get_signal
        logger.info("\n[3] Testing get_signal")
        signal = get_signal.invoke({"symbol": "BTC/USDT"})
        logger.info(f"✓ Trading signal: {signal}")
        
        # 4. 测试交易所连接
        logger.info("\n[4] Testing exchange connection")
        okx = get_exchange()
        markets = okx.load_markets()
        logger.info(f"✓ Successfully loaded {len(markets)} markets")
        
        logger.info("\n" + "=" * 60)
        logger.info("All tools debug complete!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during debugging: {str(e)}", exc_info=True)
        raise

def test_environment():
    """验证环境变量配置"""
    logger.info("=" * 60)
    logger.info("Checking environment variables")
    logger.info("=" * 60)
    
    required_vars = ["OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"]
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # 仅打印前四位和后四位
            masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            logger.info(f"✓ {var}: {masked}")
        else:
            logger.error(f"✗ {var}: Not set")

    logger.info("=" * 60)

if __name__ == '__main__':
    markets = get_exchange().load_markets()
    print(markets)
    print(markets.get("BTC/USDT"))
