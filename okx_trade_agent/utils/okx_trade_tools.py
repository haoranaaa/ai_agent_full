"""
OKX交易工具模块 - 直接使用OKX官方Python SDK进行交易操作

提供以下核心功能:
1. 市价买入/卖出订单
2. 账户余额查询
3. 当前价格获取
4. 订单查询与撤销
5. 止盈止损算法订单

技术栈: OKX Python SDK (python-okx)
"""

from __future__ import annotations

import datetime
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN

import okx.Account as Account
import okx.MarketData as MarketData
import okx.PublicData as PublicData
import okx.Trade as Trade
from dotenv import load_dotenv
from langchain_core.tools import tool

from okx_trade_agent.utils.logger import get_logger

# 加载环境变量
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

LOGGER = get_logger(__name__)

# API认证信息
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
SIMULATED_FLAG = os.getenv("OKX_SIMULATED", "1")  # "0": 实盘, "1": 模拟盘

# 交易限制配置
SUPPORTED_INST_IDS = {"BTC-USDT", "ETH-USDT", "BTC-USDT-SWAP"}  # 支持的交易对
BUY_CAP_USDT = 20  # 单笔买入上限(USDT)
MIN_BALANCE_USDT = 5  # 最小余额要求(USDT)

RETRY_CODES = {"50001"}  # service unavailable, retryable
MAX_RETRIES = 2
RETRY_DELAY = 0.3

# 全局API客户端缓存
_trade_client: Optional[Trade.TradeAPI] = None
_account_client: Optional[Account.AccountAPI] = None
_market_client: Optional[MarketData.MarketAPI] = None
_public_client: Optional[PublicData.PublicAPI] = None


class _RetryWrapper:
    """轻量包装OKX SDK方法，对特定返回code做重试，不侵入业务逻辑。"""

    def __init__(self, api_obj):
        self._api = api_obj

    def __getattr__(self, name):
        attr = getattr(self._api, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            last_res = None
            for i in range(MAX_RETRIES + 1):
                res = attr(*args, **kwargs)
                last_res = res
                code = res.get("code")
                if code not in RETRY_CODES:
                    return res
                if i < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * (2 ** i))
            return last_res

        return wrapped


# ==================== 客户端初始化 ====================

def _get_clients() -> tuple[Trade.TradeAPI, Account.AccountAPI]:
    """便于测试的交易/账户客户端获取器。"""
    return _get_trade_client(), _get_account_client()

def _get_trade_client() -> Trade.TradeAPI:
    """获取交易API客户端(单例模式)"""
    global _trade_client
    if _trade_client is None:
        if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            raise RuntimeError("OKX API认证信息缺失,请检查.env文件配置")
        _trade_client = _RetryWrapper(Trade.TradeAPI(API_KEY, API_SECRET, API_PASSPHRASE, False, SIMULATED_FLAG))
        LOGGER.info(f"已初始化OKX交易API客户端 (模拟盘: {SIMULATED_FLAG})")
    return _trade_client


def _get_account_client() -> Account.AccountAPI:
    """获取账户API客户端(单例模式)"""
    global _account_client
    if _account_client is None:
        if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            raise RuntimeError("OKX API认证信息缺失,请检查.env文件配置")
        _account_client = _RetryWrapper(Account.AccountAPI(API_KEY, API_SECRET, API_PASSPHRASE, False, SIMULATED_FLAG))
        LOGGER.info(f"已初始化OKX账户API客户端 (模拟盘: {SIMULATED_FLAG})")
    return _account_client


def _get_market_client() -> MarketData.MarketAPI:
    """获取市场数据API客户端(单例模式,无需认证)"""
    global _market_client
    if _market_client is None:
        _market_client = _RetryWrapper(MarketData.MarketAPI(flag=SIMULATED_FLAG))
        LOGGER.info(f"已初始化OKX市场数据API客户端 (模拟盘: {SIMULATED_FLAG})")
    return _market_client


def _get_public_client() -> PublicData.PublicAPI:
    """获取公共数据API客户端(单例模式,无需认证)"""
    global _public_client
    if _public_client is None:
        _public_client = _RetryWrapper(PublicData.PublicAPI(flag=SIMULATED_FLAG))
        LOGGER.info(f"已初始化OKX公共数据API客户端 (模拟盘: {SIMULATED_FLAG})")
    return _public_client


# ==================== 核心业务函数 ====================

def _get_current_price(inst_id: str = "BTC-USDT") -> Dict[str, Any]:
    """获取指定交易对的当前价格

    Args:
        inst_id: 交易对标识符,例如 "BTC-USDT", "ETH-USDT"

    Returns:
        包含价格信息的字典: {
            "inst_id": 交易对,
            "last_price": 最新成交价,
            "bid_price": 买一价,
            "ask_price": 卖一价,
            "timestamp": 时间戳
        }
    """
    try:
        market_api = _get_market_client()
        result = market_api.get_ticker(instId=inst_id)

        if result["code"] != "0":
            raise RuntimeError(f"获取价格失败: {result}")

        data = result["data"][0]
        return {
            "inst_id": inst_id,
            "last_price": float(data["last"]),
            "bid_price": float(data["bidPx"]),
            "ask_price": float(data["askPx"]),
            "timestamp": data["ts"]
        }
    except Exception as e:
        LOGGER.error(f"获取价格时发生错误 (inst_id={inst_id}): {str(e)}")
        raise


def _get_instrument(inst_id: str) -> Dict[str, Any]:
    """获取合约元数据,用于校验与精度处理。"""
    public_api = _get_public_client()
    inst_type = "SWAP" if "SWAP" in inst_id else "SPOT"
    result = public_api.get_instruments(instType=inst_type, instId=inst_id)
    if result.get("code") not in [None, "0"]:
        raise RuntimeError(f"查询合约元数据失败: {result}")

    data = result.get("data", [])
    if not data:
        raise RuntimeError(f"未找到合约: {inst_id}")
    return data[0]


def _quantize_size(inst_id: str, base_size: float) -> str:
    """根据合约lotSz约束数量，向下取整防止超额精度。"""
    instrument = _get_instrument(inst_id)
    lot_sz = instrument.get("lotSz")
    if not lot_sz:
        raise RuntimeError(f"合约缺少lotSz配置: {instrument}")

    try:
        step_dec = Decimal(lot_sz)
        size_dec = Decimal(str(base_size))
    except InvalidOperation:
        raise RuntimeError(f"无法解析下单精度: lotSz={lot_sz}, base_size={base_size}")
    if step_dec <= 0:
        raise RuntimeError(f"无效的lotSz: {lot_sz}")

    # 使用Decimal避免浮点误差导致的截断(如5.1//0.01=5.09)造成持仓残留
    multiples = (size_dec / step_dec).to_integral_value(rounding=ROUND_DOWN)
    quantized = multiples * step_dec
    if quantized <= 0:
        raise ValueError("订单数量过小，低于最小下单手数")

    precision = abs(step_dec.as_tuple().exponent)
    return f"{quantized:.{precision}f}"


@tool
def get_account_balance(currency: str = "") -> Dict[str, Any]:
    """获取账户余额信息

    Args:
        currency: 币种,例如 "BTC", "USDT", 为空则返回所有币种

    Returns:
        余额信息字典
    """
    try:
        account_api = _get_account_client()
        result = account_api.get_account_balance(ccy=currency if currency else None)

        if result["code"] != "0":
            raise RuntimeError(f"获取余额失败: {result}")

        account_data = result["data"][0]
        balances = []

        for detail in account_data.get("details", []):
            balances.append({
                "currency": detail["ccy"],
                "available": float(detail.get("availBal", 0)),
                "frozen": float(detail.get("frozenBal", 0)),
                "equity": float(detail.get("eq", 0))
            })

        return {
            "total_equity": float(account_data.get("totalEq", 0)),
            "balances": balances,
            "update_time": account_data.get("uTime")
        }
    except Exception as e:
        LOGGER.error(f"获取余额时发生错误: {str(e)}")
        raise


@tool
def place_market_buy(
    inst_id: str,
    usdt_amount: float,
    td_mode: str = "cash"
) -> Dict[str, Any]:
    """市价买入订单

    Args:
        inst_id: 交易对,例如 "BTC-USDT"
        usdt_amount: 买入金额(USDT),受BUY_CAP_USDT限制
        td_mode: 交易模式 - "cash":现货, "cross":全仓, "isolated":逐仓

    Returns:
        订单结果字典
    """
    try:
        # 参数验证
        if inst_id not in SUPPORTED_INST_IDS:
            raise ValueError(f"不支持的交易对: {inst_id}, 支持的交易对: {SUPPORTED_INST_IDS}")

        if usdt_amount <= 0:
            raise ValueError(f"买入金额必须大于0: {usdt_amount}")

        if usdt_amount > BUY_CAP_USDT:
            raise ValueError(f"买入金额超过限制 {BUY_CAP_USDT} USDT: {usdt_amount}")

        # 检查USDT余额
        balance = get_account_balance("USDT")
        usdt_available = next(
            (b["available"] for b in balance["balances"] if b["currency"] == "USDT"),
            0
        )

        if usdt_available < usdt_amount:
            raise ValueError(f"USDT余额不足: 可用={usdt_available}, 需要={usdt_amount}")

        if usdt_available < MIN_BALANCE_USDT:
            raise ValueError(f"USDT余额低于最小要求 {MIN_BALANCE_USDT} USDT")

        # 生成客户端订单ID
        cl_ord_id = f"buy{uuid.uuid4().hex[:12]}"

        # 调用OKX API下单
        trade_api = _get_trade_client()
        result = trade_api.place_order(
            instId=inst_id,
            tdMode=td_mode,
            side="buy",
            ordType="market",
            sz=str(usdt_amount),
            tgtCcy="quote_ccy",  # 以计价货币(USDT)为单位
            clOrdId=cl_ord_id
        )

        LOGGER.info(f"市价买入订单响应: {result}")

        # 检查结果
        if result["code"] != "0":
            raise RuntimeError(f"下单失败: code={result['code']}, msg={result.get('msg')}")

        order_data = result["data"][0]
        if order_data.get("sCode") not in ["0", None]:
            raise RuntimeError(f"订单被拒绝: sCode={order_data['sCode']}, sMsg={order_data.get('sMsg')}")

        return {
            "inst_id": inst_id,
            "side": "buy",
            "order_id": order_data.get("ordId"),
            "client_order_id": cl_ord_id,
            "size": usdt_amount,
            "status": "submitted",
            "raw_response": result
        }

    except Exception as e:
        LOGGER.error(f"市价买入失败 (inst_id={inst_id}, amount={usdt_amount}): {str(e)}")
        raise


@tool
def place_market_sell(
    inst_id: str,
    base_amount: float,
    td_mode: str = "cash"
) -> Dict[str, Any]:
    """市价卖出订单

    Args:
        inst_id: 交易对,例如 "BTC-USDT"
        base_amount: 卖出数量(基础货币,如BTC)
        td_mode: 交易模式 - "cash":现货, "cross":全仓, "isolated":逐仓

    Returns:
        订单结果字典
    """
    try:
        # 参数验证
        if inst_id not in SUPPORTED_INST_IDS:
            raise ValueError(f"不支持的交易对: {inst_id}")

        if base_amount <= 0:
            raise ValueError(f"卖出数量必须大于0: {base_amount}")

        # 检查基础货币余额
        base_currency = inst_id.split("-")[0]  # 例如 "BTC-USDT" -> "BTC"
        balance = get_account_balance(base_currency)
        base_available = next(
            (b["available"] for b in balance["balances"] if b["currency"] == base_currency),
            0
        )

        if base_available < base_amount:
            raise ValueError(f"{base_currency}余额不足: 可用={base_available}, 需要={base_amount}")

        # 生成客户端订单ID
        cl_ord_id = f"sell-{uuid.uuid4().hex[:12]}"

        # 调用OKX API下单
        trade_api = _get_trade_client()
        result = trade_api.place_order(
            instId=inst_id,
            tdMode=td_mode,
            side="sell",
            ordType="market",
            sz=str(base_amount),
            clOrdId=cl_ord_id
        )

        LOGGER.info(f"市价卖出订单响应: {result}")

        # 检查结果
        if result["code"] != "0":
            raise RuntimeError(f"下单失败: code={result['code']}, msg={result.get('msg')}")

        order_data = result["data"][0]
        if order_data.get("sCode") not in ["0", None]:
            raise RuntimeError(f"订单被拒绝: sCode={order_data['sCode']}, sMsg={order_data.get('sMsg')}")

        return {
            "inst_id": inst_id,
            "side": "sell",
            "order_id": order_data.get("ordId"),
            "client_order_id": cl_ord_id,
            "size": base_amount,
            "status": "submitted",
            "raw_response": result
        }

    except Exception as e:
        LOGGER.error(f"市价卖出失败 (inst_id={inst_id}, amount={base_amount}): {str(e)}")
        raise


@tool
def place_limit_order(
    inst_id: str,
    side: str,
    price: float,
    size: float,
    td_mode: str = "cash"
) -> Dict[str, Any]:
    """限价订单

    Args:
        inst_id: 交易对,例如 "BTC-USDT"
        side: 买卖方向 - "buy" 或 "sell"
        price: 限价价格
        size: 订单数量(基础货币)
        td_mode: 交易模式 - "cash":现货, "cross":全仓, "isolated":逐仓

    Returns:
        订单结果字典
    """
    try:
        # 参数验证
        if inst_id not in SUPPORTED_INST_IDS:
            raise ValueError(f"不支持的交易对: {inst_id}")

        if side not in ["buy", "sell"]:
            raise ValueError(f"无效的买卖方向: {side}, 必须是 'buy' 或 'sell'")

        if price <= 0 or size <= 0:
            raise ValueError(f"价格和数量必须大于0: price={price}, size={size}")

        # 生成客户端订单ID
        cl_ord_id = f"{side}-limit-{uuid.uuid4().hex[:12]}"

        # 调用OKX API下单
        trade_api = _get_trade_client()
        result = trade_api.place_order(
            instId=inst_id,
            tdMode=td_mode,
            side=side,
            ordType="limit",
            px=str(price),
            sz=str(size),
            clOrdId=cl_ord_id
        )

        LOGGER.info(f"限价订单响应: {result}")

        # 检查结果
        if result["code"] != "0":
            raise RuntimeError(f"下单失败: code={result['code']}, msg={result.get('msg')}")

        order_data = result["data"][0]
        if order_data.get("sCode") not in ["0", None]:
            raise RuntimeError(f"订单被拒绝: sCode={order_data['sCode']}, sMsg={order_data.get('sMsg')}")

        return {
            "inst_id": inst_id,
            "side": side,
            "order_type": "limit",
            "price": price,
            "size": size,
            "order_id": order_data.get("ordId"),
            "client_order_id": cl_ord_id,
            "status": "submitted",
            "raw_response": result
        }

    except Exception as e:
        LOGGER.error(f"限价订单失败 (inst_id={inst_id}, side={side}, price={price}, size={size}): {str(e)}")
        raise


@tool
def cancel_order(inst_id: str, order_id: str = "", client_order_id: str = "") -> Dict[str, Any]:
    """撤销订单

    Args:
        inst_id: 交易对,例如 "BTC-USDT"
        order_id: OKX订单ID(ordId)
        client_order_id: 客户端订单ID(clOrdId)

    注: order_id 和 client_order_id 至少提供一个

    Returns:
        撤单结果字典
    """
    try:
        if not order_id and not client_order_id:
            raise ValueError("必须提供 order_id 或 client_order_id 之一")

        trade_api = _get_trade_client()
        result = trade_api.cancel_order(
            instId=inst_id,
            ordId=order_id if order_id else None,
            clOrdId=client_order_id if client_order_id else None
        )

        LOGGER.info(f"撤单响应: {result}")

        if result["code"] != "0":
            raise RuntimeError(f"撤单失败: code={result['code']}, msg={result.get('msg')}")

        cancel_data = result["data"][0]
        if cancel_data.get("sCode") not in ["0", None]:
            raise RuntimeError(f"撤单被拒绝: sCode={cancel_data['sCode']}, sMsg={cancel_data.get('sMsg')}")

        return {
            "inst_id": inst_id,
            "order_id": order_id or cancel_data.get("ordId"),
            "client_order_id": client_order_id or cancel_data.get("clOrdId"),
            "status": "canceled",
            "raw_response": result
        }

    except Exception as e:
        LOGGER.error(f"撤单失败 (inst_id={inst_id}, order_id={order_id}, client_order_id={client_order_id}): {str(e)}")
        raise


@tool
def get_order_history(inst_id: str = "", limit: int = 10) -> List[Dict[str, Any]]:
    """查询历史订单(最近7天)

    Args:
        inst_id: 交易对,例如 "BTC-USDT", 为空则查询所有
        limit: 返回结果数量限制

    Returns:
        订单列表
    """
    try:
        trade_api = _get_trade_client()

        # 根据inst_id判断交易类型
        if inst_id:
            inst_type = "SWAP" if "SWAP" in inst_id else "SPOT"
            result = trade_api.get_orders_history(instType=inst_type, instId=inst_id)
        else:
            result = trade_api.get_orders_history(instType="SPOT")

        if result["code"] != "0":
            raise RuntimeError(f"查询订单历史失败: {result}")

        orders = []
        for order in result.get("data", [])[:limit]:
            orders.append({
                "inst_id": order["instId"],
                "order_id": order["ordId"],
                "client_order_id": order.get("clOrdId", ""),
                "side": order["side"],
                "order_type": order["ordType"],
                "price": float(order.get("px", 0)),
                "size": float(order["sz"]),
                "filled_size": float(order.get("accFillSz", 0)),
                "state": order["state"],
                "created_time": order["cTime"],
                "updated_time": order["uTime"]
            })

        return orders

    except Exception as e:
        LOGGER.error(f"查询订单历史失败: {str(e)}")
        raise


@tool
def place_tp_sl_order(
    inst_id: str,
    side: str,
    size: float,
    take_profit_price: float = None,
    stop_loss_price: float = None,
    td_mode: str = "cash"
) -> Dict[str, Any]:
    """下单并附加止盈止损算法订单

    Args:
        inst_id: 交易对,例如 "BTC-USDT"
        side: 买卖方向 - "buy" 或 "sell"
        size: 订单数量
        take_profit_price: 止盈价格
        stop_loss_price: 止损价格
        td_mode: 交易模式

    Returns:
        订单结果字典
    """
    try:
        if not take_profit_price and not stop_loss_price:
            raise ValueError("至少需要设置止盈价格或止损价格")

        # 生成客户端订单ID
        cl_ord_id = f"{side}-tpsl-{uuid.uuid4().hex[:12]}"

        # 构建附加算法订单
        attach_algo_ords = []
        if take_profit_price:
            attach_algo_ords.append({
                "tpTriggerPx": str(take_profit_price),
                "tpOrdPx": "-1"  # -1表示市价单
            })
        if stop_loss_price:
            if attach_algo_ords:
                # 如果已有止盈,添加到同一对象
                attach_algo_ords[0]["slTriggerPx"] = str(stop_loss_price)
                attach_algo_ords[0]["slOrdPx"] = "-1"
            else:
                attach_algo_ords.append({
                    "slTriggerPx": str(stop_loss_price),
                    "slOrdPx": "-1"
                })

        # 调用OKX API下单
        trade_api = _get_trade_client()
        result = trade_api.place_order(
            instId=inst_id,
            tdMode=td_mode,
            side=side,
            ordType="market",
            sz=str(size),
            clOrdId=cl_ord_id,
            attachAlgoOrds=attach_algo_ords
        )

        LOGGER.info(f"止盈止损订单响应: {result}")

        # 检查结果
        if result["code"] != "0":
            raise RuntimeError(f"下单失败: code={result['code']}, msg={result.get('msg')}")

        order_data = result["data"][0]
        if order_data.get("sCode") not in ["0", None]:
            raise RuntimeError(f"订单被拒绝: sCode={order_data['sCode']}, sMsg={order_data.get('sMsg')}")

        return {
            "inst_id": inst_id,
            "side": side,
            "order_id": order_data.get("ordId"),
            "client_order_id": cl_ord_id,
            "size": size,
            "take_profit_price": take_profit_price,
            "stop_loss_price": stop_loss_price,
            "status": "submitted",
            "raw_response": result
        }

    except Exception as e:
        LOGGER.error(f"止盈止损订单失败: {str(e)}")
        raise


@tool
def place_okx_order(
    instId: str,
    side: str,
    posSide: str,
    usdt_amount: float,
    limit_px: float,
    take_profit: float,
    stop_loss: float,
    td_mode: str = "isolated",
    leverage: int = 1,
) -> Dict[str, Any]:
    """在永续合约上下限价单并同时附加止盈止损。

    将下单金额视为保证金(USDT)，乘杠杆得到名义价值，再按限价换算数量并按lotSz向下取整。
    仅支持永续合约(如 BTC-USDT-SWAP)。
    """
    get_logger().info(f"place_okx_order 调用, instId={instId}, side={side}, posSide={posSide}, usdt_amount={usdt_amount}, limit_px={limit_px}, take_profit={take_profit}, stop_loss={stop_loss}, td_mode={td_mode}, leverage={leverage}")
    if not instId.endswith("-SWAP"):
        raise ValueError(f"仅支持永续合约, 当前: {instId}")
    if side not in {"buy", "sell"}:
        raise ValueError("side 需为 'buy' 或 'sell'")
    if posSide not in {"long", "short", "net"}:
        raise ValueError("posSide 需为 long/short/net")

    try:
        usdt_amount = float(usdt_amount)
        limit_px = float(limit_px)
        take_profit = float(take_profit)
        stop_loss = float(stop_loss)
        leverage = int(leverage)
    except (TypeError, ValueError):
        raise ValueError("usdt_amount/limit_px/take_profit/stop_loss/lever 需为数字")

    if usdt_amount <= 0 or limit_px <= 0:
        raise ValueError("下单金额与价格必须大于0")
    if take_profit is None or stop_loss is None:
        raise ValueError("止盈(take_profit)与止损(stop_loss)均为必填")
    if leverage <= 0:
        raise ValueError("杠杆必须大于0")

    trade_api, account_api = _get_clients()

    # 检查USDT余额
    balance = account_api.get_account_balance()
    details = balance.get("data", [{}])[0].get("details", [])
    usdt_available = 0.0
    for item in details:
        if item.get("ccy") == "USDT":
            try:
                usdt_available = float(item.get("availBal", 0) or 0)
            except (TypeError, ValueError):
                usdt_available = 0.0
            break
    if usdt_available < usdt_amount:
        raise ValueError(f"USDT余额不足, 可用 {usdt_available}, 需要 {usdt_amount}")

    # 持仓模式需与 posSide 匹配: long/short 需双向仓, net 需单向仓
    desired_pos_mode = "long_short_mode" if posSide in {"long", "short"} else "net_mode"
    try:
        config = account_api.get_account_config()
        pos_mode = config.get("data", [{}])[0].get("posMode")
    except Exception:
        pos_mode = None
    if pos_mode != desired_pos_mode:
        switch_result = account_api.set_position_mode(posMode=desired_pos_mode)
        if switch_result.get("code") not in [None, "0"]:
            raise RuntimeError(f"切换持仓模式失败: {switch_result}")

    # 设置杠杆，交易所会缓存该配置
    leverage_params = {"instId": instId, "mgnMode": td_mode, "lever": str(leverage)}
    if td_mode == "isolated" and posSide != "net":
        leverage_params["posSide"] = posSide
    set_leverage_result = account_api.set_leverage(**leverage_params)
    if set_leverage_result.get("code") not in [None, "0"]:
        raise RuntimeError(f"设置杠杆失败: {set_leverage_result}")
    LOGGER.info(f"设置杠杆成功: {set_leverage_result}")
    cl_ord_id = f"{datetime.datetime.now().strftime('%Y%m%d')}{side}{'long' if posSide == 'long' else 'short'}{instId.split('-')[0]}{int(usdt_amount)}{leverage}{uuid.uuid4().hex[:4]}"

    # USDT保证金 * 杠杆 -> 名义价值 -> 基础币数量
    base_size = usdt_amount * leverage / limit_px

    # SWAP 下单数量单位是合约张数，需用 ctVal 换算
    instrument = _get_instrument(instId)
    ct_val = instrument.get("ctVal")
    ct_val_ccy = instrument.get("ctValCcy")
    if ct_val is None:
        raise RuntimeError(f"合约缺少ctVal: {instrument}")
    try:
        ct_val_f = float(ct_val)
    except (TypeError, ValueError):
        raise RuntimeError(f"无效的ctVal: {ct_val}")
    if ct_val_f <= 0:
        raise RuntimeError(f"无效的ctVal: {ct_val}")

    # 合约张数(未量化)
    contracts = base_size / ct_val_f

    # 按 lotSz 量化张数
    sz = _quantize_size(instId, contracts)
    payload = {
        "instId": instId,
        "tdMode": td_mode,
        "side": side,
        "posSide": str(posSide),
        "ordType": "limit",
        "px": str(limit_px),
        "sz": sz,
        "clOrdId": str(cl_ord_id),
        "attachAlgoOrds": [
            {
                "tpTriggerPx": str(take_profit),
                "tpOrdPx": "-1",
                "slTriggerPx": str(stop_loss),
                "slOrdPx": "-1",
            }
        ],
    }

    LOGGER.info("提交永续限价单: %s", payload)
    result = trade_api.place_order(**payload)
    LOGGER.info("下单响应: %s", result)

    if result.get("code") not in [None, "0"]:
        raise RuntimeError(f"下单失败: {result}")
    order_data = result.get("data", [{}])[0]
    if order_data.get("sCode") not in ["0", None]:
        raise RuntimeError(f"订单被拒绝: sCode={order_data.get('sCode')}, sMsg={order_data.get('sMsg')}")

    return {
        "instId": instId,
        "side": side,
        "posSide": posSide,
        "tdMode": td_mode,
        "leverage": leverage,
        "order_id": order_data.get("ordId"),
        "client_order_id": cl_ord_id,
        "price": limit_px,
        "size": sz,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "raw_response": result,
    }


@tool
def close_position(
    instId: str,
    posSide: str,
    close_px: float,
    td_mode: str = "isolated",
) -> Dict[str, Any]:
    """平掉指定永续合约方向的持仓（reduce-only 限价单，默认全平）。

    Args:
        instId: 合约ID, 例如 "ETH-USDT-SWAP"
        posSide: long 或 short（仅双向持仓）
        close_px: 平仓限价
        td_mode: 逐仓/全仓，默认沿用逐仓
    """
    LOGGER.info(
        "close_position 调用, instId=%s, posSide=%s, close_px=%s, td_mode=%s",
        instId, posSide, close_px, td_mode
    )
    if not instId.endswith("-SWAP"):
        raise ValueError(f"仅支持永续合约, 当前: {instId}")
    if posSide not in {"long", "short"}:
        raise ValueError("posSide 需为 long 或 short")
    try:
        close_px_f = float(close_px)
    except (TypeError, ValueError):
        raise ValueError("close_px 需为数字")
    if close_px_f <= 0:
        raise ValueError("close_px 必须大于0")

    trade_api, account_api = _get_clients()
    positions_res = account_api.get_positions(instId=instId)
    pos_list = positions_res.get("data", []) or []
    position = next((p for p in pos_list if p.get("posSide") == posSide), None)
    if not position:
        raise ValueError(f"未找到 {instId} {posSide} 持仓")

    raw_pos = position.get("pos") or position.get("sz")
    try:
        pos_size = float(raw_pos)
    except (TypeError, ValueError):
        pos_size = 0.0
    if pos_size <= 0:
        raise ValueError(f"{instId} {posSide} 持仓数量无效: {raw_pos}")

    sz = _quantize_size(instId, pos_size)
    order_side = "sell" if posSide == "long" else "buy"
    tdMode = position.get("mgnMode") or td_mode or "isolated"
    cl_ord_id = f"close{datetime.datetime.now().strftime('%Y%m%d')}{posSide}{uuid.uuid4().hex[:4]}"

    payload = {
        "instId": instId,
        "tdMode": tdMode,
        "side": order_side,
        "posSide": posSide,
        "ordType": "limit",
        "px": str(close_px_f),
        "sz": sz,
        "reduceOnly": True,
        "clOrdId": cl_ord_id,
    }

    LOGGER.info("提交平仓单: %s", payload)
    result = trade_api.place_order(**payload)
    LOGGER.info("平仓下单响应: %s", result)

    if result.get("code") not in [None, "0"]:
        raise RuntimeError(f"平仓下单失败: {result}")
    order_data = result.get("data", [{}])[0]
    if order_data.get("sCode") not in ["0", None]:
        raise RuntimeError(f"平仓被拒绝: sCode={order_data.get('sCode')}, sMsg={order_data.get('sMsg')}")

    return {
        "instId": instId,
        "side": order_side,
        "posSide": posSide,
        "tdMode": tdMode,
        "order_id": order_data.get("ordId"),
        "client_order_id": cl_ord_id,
        "price": close_px_f,
        "size": sz,
        "raw_response": result,
    }


# ==================== 导出的工具列表 ====================

TOOLS = [
    _get_current_price,
    get_account_balance,
    place_market_buy,
    place_market_sell,
    place_limit_order,
    cancel_order,
    get_order_history,
    place_tp_sl_order,
    place_okx_order,
    close_position,
]

__all__ = [
    "_get_current_price",
    "get_account_balance",
    "place_market_buy",
    "place_market_sell",
    "place_limit_order",
    "cancel_order",
    "get_order_history",
    "place_tp_sl_order",
    "place_okx_order",
    "close_position",
]


# ==================== 测试示例 ====================

def main():
    """
    测试示例: 在模拟盘下单一笔永续限价单并附带止盈止损。

    参数示例:
    - 做多 BTC-USDT-SWAP
    - 逐仓 5x
    - 价格: 100000
    - 名义金额: 200 USDT (按限价换算手数并按 lotSz 对齐)
    - 止盈: 110000
    - 止损: 90000
    """

    inst_id = "BTC-USDT-SWAP"

    try:
        LOGGER.info("=" * 50)
        LOGGER.info("测试 place_okx_order (模拟盘)")
        LOGGER.info("=" * 50)

        # 1) 先拉行情便于对照
        price_info = _get_current_price(inst_id)
        LOGGER.info("当前价格: %s", price_info)

        # 2) 下单: 做多逐仓 10x，限价+止盈止损
        order = place_okx_order.invoke(
            {
                "instId": inst_id,
                "side": "buy",
                "posSide": "long",
                "usdt_amount": 500,
                "limit_px": 90000,
                "take_profit": 100000,
                "stop_loss": 80000,
                "td_mode": "isolated",
                "leverage": 10,
            }
        )
        LOGGER.info("下单完成: %s", order)

        LOGGER.info("=" * 50)
        LOGGER.info("测试完成 (如需取消订单，可调用 cancel_order)")

    except Exception as e:
        LOGGER.error(f"测试过程中发生错误: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
