"""Price subscription helpers using OKX WebSocket tickers with polling fallback."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from langgraph.types import interrupt

try:
    from okx.websocket.WsPublicAsync import WsPublicAsync
except Exception:  # pragma: no cover - fallback when WS SDK missing
    WsPublicAsync = None  # type: ignore

from okx_trade_agent.utils.okx_trade_tools import SIMULATED_FLAG, _get_current_price


WS_PUBLIC_LIVE = "wss://ws.okx.com:8443/ws/v5/public"
WS_PUBLIC_PAPER = "wss://wspap.okx.com:8443/ws/v5/public"


def _normalize_inst_id(symbol_or_inst: str) -> str:
    """Convert ccxt-style symbol to OKX instId (perp)."""
    if symbol_or_inst.endswith("-SWAP") and "-" in symbol_or_inst:
        return symbol_or_inst
    if "/" in symbol_or_inst:
        base_quote = symbol_or_inst.split(":")[0]  # strip settlement
        base, quote = base_quote.split("/")
        return f"{base}-{quote}-SWAP"
    return symbol_or_inst


class PriceSubscriptionManager:
    """Manage price-trigger subscriptions and provide a wake event for the runner."""

    def __init__(self) -> None:
        # Shared event that can wake paused flows when trigger is hit.
        self._event = asyncio.Event()
        self._ws: Optional[WsPublicAsync] = None
        self._ws_connected = False
        self._ws_lock = asyncio.Lock()
        self._watchers: Dict[str, List[Dict[str, Any]]] = {}
        self._subscribed: set[str] = set()

    def clear_event(self) -> None:
        self._event.clear()

    async def wait_event(self) -> None:
        await self._event.wait()

    def _trigger(self) -> None:
        self._event.set()

    async def _ensure_ws(self) -> None:
        """Lazy-init WebSocket connection."""
        if self._ws_connected or WsPublicAsync is None:
            return
        async with self._ws_lock:
            if self._ws_connected:
                return
            url = WS_PUBLIC_PAPER if str(SIMULATED_FLAG) == "1" else WS_PUBLIC_LIVE
            self._ws = WsPublicAsync(url=url)
            await self._ws.start()
            self._ws_connected = True

    async def _subscribe_inst(self, inst_id: str) -> None:
        """Subscribe to ticker channel for an instId if not already."""
        await self._ensure_ws()
        if not self._ws or not self._ws_connected:
            return
        if inst_id in self._subscribed:
            return

        def _callback(message: Dict[str, Any]) -> None:
            # Push callback into the loop to handle async safely
            asyncio.get_event_loop().create_task(self._handle_message(message))

        args = [{"channel": "tickers", "instId": inst_id}]
        await self._ws.subscribe(args, callback=_callback)
        self._subscribed.add(inst_id)

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        data = message.get("data", [])
        if not data:
            return
        tick = data[0]
        inst_id = tick.get("instId")
        if not inst_id:
            return
        try:
            last_price = float(tick.get("last") or tick.get("px"))
        except (TypeError, ValueError):
            return

        watchers = self._watchers.get(inst_id, [])
        remaining: List[Dict[str, Any]] = []
        for w in watchers:
            direction = w["direction"]
            target = w["target_price"]
            tol = w["tolerance"]
            hit = False
            if direction == "above":
                hit = last_price >= target - tol
            elif direction == "below":
                hit = last_price <= target + tol
            else:
                continue

            if hit:
                self._trigger()
                w["status"] = "triggered"
                w["last_price"] = last_price
            else:
                remaining.append(w)

        self._watchers[inst_id] = remaining

    async def _poll_price(
        self,
        inst_id: str,
        target_price: float,
        direction: str,
        poll_interval: float,
        tolerance: float,
        max_checks: Optional[int],
    ) -> Dict[str, Any]:
        """Polling fallback when WS SDK不可用或连接失败。"""
        checks = 0
        while True:
            price_info = _get_current_price(inst_id)
            last_price = float(price_info.get("last_price"))

            hit = False
            if direction == "above":
                hit = last_price >= target_price - tolerance
            elif direction == "below":
                hit = last_price <= target_price + tolerance
            else:
                raise ValueError("direction 需为 'above' 或 'below'")

            if hit:
                self._trigger()
                return {
                    "inst_id": inst_id,
                    "last_price": last_price,
                    "target_price": target_price,
                    "direction": direction,
                    "status": "triggered",
                }

            checks += 1
            if max_checks is not None and checks >= max_checks:
                return {
                    "inst_id": inst_id,
                    "last_price": last_price,
                    "target_price": target_price,
                    "direction": direction,
                    "status": "expired",
                }

            await asyncio.sleep(poll_interval)

    def subscribe(
        self,
        inst_id: str,
        target_price: float,
        direction: str = "above",
        poll_interval: float = 5.0,
        tolerance: float = 0.0,
        max_checks: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a WS ticker subscription (preferred) with polling fallback."""
        inst_id_norm = _normalize_inst_id(inst_id)
        loop = asyncio.get_event_loop()

        # Try WS path first
        if WsPublicAsync is not None:
            loop.create_task(self._subscribe_inst(inst_id_norm))
            watcher = {
                "inst_id": inst_id_norm,
                "target_price": float(target_price),
                "direction": direction,
                "tolerance": float(tolerance),
                "status": "scheduled",
            }
            self._watchers.setdefault(inst_id_norm, []).append(watcher)
            return {
                "inst_id": inst_id_norm,
                "target_price": target_price,
                "direction": direction,
                "mode": "websocket",
                "status": "scheduled",
            }

        # Fallback: polling task
        task = loop.create_task(
            self._poll_price(inst_id_norm, float(target_price), direction, poll_interval, tolerance, max_checks)
        )
        task.add_done_callback(lambda t: None)
        return {
            "inst_id": inst_id_norm,
            "target_price": target_price,
            "direction": direction,
            "mode": "polling",
            "status": "scheduled",
        }


# Global manager for the runner and tools to share
SUBSCRIPTION_MANAGER = PriceSubscriptionManager()


@tool
def await_price_trigger(
    instId: str,
    target_price: float,
    direction: str = "above",
    poll_interval: float = 5.0,
    tolerance: float = 0.0,
    max_checks: Optional[int] = None,
    timeout: float = 1500.0,
) -> Dict[str, Any]:
    """单工具完成订阅并挂起: 注册价格触发器，然后 interrupt 等待外部 resume。

    调用流程:
        1) 模型调用本工具，会先注册订阅(WS优先，失败回退轮询)。
        2) 立即触发 interrupt，返回 payload= {waiting...} 给上层，执行暂停。
        3) 外部事件监听（基于 SUBSCRIPTION_MANAGER 的 event，或其他渠道）命中后，
           使用 Command(resume={\"status\":\"triggered\"|\"timeout\",\"last_price\":...}) 恢复。

    Args:
        instId: 合约或符号, 如 \"BTC-USDT-SWAP\" 或 \"BTC/USDT:USDT\" (自动转 SWAP instId)
        target_price: 触发价格
        direction: 'above' 达到或高于触发, 'below' 达到或低于触发
        poll_interval: 轮询间隔(秒, 仅在 WS 不可用时生效)
        tolerance: 触发容差, 用于浮点误差
        max_checks: 最大轮询次数, None 表示无限直到触发 (仅轮询模式)
        timeout: 建议的最大等待秒数(外部可用来决定超时 resume)

    Notes:
        - 需要在 invoke 时提供 thread_id 并使用支持 interrupt 的运行时（LangGraph）。
        - resume 时传入的 payload 会作为 interrupt 的返回值继续后续逻辑。
    """
    inst_id_norm = _normalize_inst_id(instId)
    SUBSCRIPTION_MANAGER.subscribe(inst_id_norm, float(target_price), direction, poll_interval, tolerance, max_checks)
    payload = {
        "status": "waiting_for_price",
        "instId": inst_id_norm,
        "target_price": target_price,
        "direction": direction,
        "timeout": timeout,
        "hint": "resume with {'status': 'triggered'|'timeout', 'last_price': <optional>}",
    }
    resume_val = interrupt(payload)
    return {"status": resume_val.get("status", "unknown"), "payload": resume_val}
