import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from okx_trade_agent.price_agent import price_agent, SYSTEM_PROMPT
from okx_trade_agent.utils.get_exchange import get_exchange
from okx_trade_agent.utils.logger import get_logger
from okx_trade_agent.utils.perp_market import PerpSymbolSnapshot, fetch_perp_snapshots
from okx_trade_agent.utils.symbols import DEFAULT_PERP_SYMBOLS, base_from_symbol, load_symbols

log = get_logger(__name__)

DEFAULT_SYMBOLS: Sequence[str] = DEFAULT_PERP_SYMBOLS
INTRADAY_KEEP = 10
PROMPTS_DIR = Path(__file__).resolve().parent.joinpath("prompts")
PERP_USER_PROMPT = PROMPTS_DIR.joinpath("perp_user_prompt.txt").read_text(encoding="utf-8")


def _fmt_num(val: float | None) -> str:
    """Shorten numeric strings to keep prompts compact for the model."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.6g}"  # cap to ~6 significant digits (~<=10 chars)
    except (TypeError, ValueError):
        return str(val)


def _fmt_seq(seq: Sequence[float]) -> str:
    return "[" + ", ".join(_fmt_num(v) for v in seq) + "]"


class AutoTradeAgent:
    """Periodic runner that feeds market/account context into the minimal price agent."""

    exchange: Any
    symbols: List[str]
    cnt: int = 0
    baseline_usdt: float | None = None
    start_time: datetime

    def __init__(self, exchange: Any, symbols: List[str]):
        self.exchange = exchange
        self.symbols = symbols
        self.start_time = datetime.now(timezone.utc)

    def _set_baseline(self, balances: Dict[str, Any]):
        if self.baseline_usdt is None:
            self.baseline_usdt = float(balances.get("USDT", {}).get("total", 0.0))
            log.info("Baseline USDT set to %.4f", self.baseline_usdt)

    def _format_context_section(self, snap: PerpSymbolSnapshot) -> str:
        return (
            f"20-Period EMA: {_fmt_num(snap.ema20_4h)} vs. 50-Period EMA: {_fmt_num(snap.ema50_4h)}\n"
            f"3-Period ATR: {_fmt_num(snap.atr3_4h)} vs. 14-Period ATR: {_fmt_num(snap.atr14_4h)}\n"
            f"Current Volume: {_fmt_num(snap.volume_current_4h)} vs. Average Volume: {_fmt_num(snap.volume_avg_4h)}\n"
            f"MACD indicators (4h): {_fmt_seq(snap.macd_4h)}\n"
            f"RSI indicators (14-Period, 4h): {_fmt_seq(snap.rsi14_4h)}\n"
        )

    def _build_symbol_block(self, name: str, snap: PerpSymbolSnapshot) -> str:
        return (
            f"### ALL {name} DATA\n\n"
            f"**Current Snapshot:**\n"
            f"- current_price = {_fmt_num(snap.current_price)}\n"
            f"- current_ema20 = {_fmt_num(snap.ema20)}\n"
            f"- current_macd = {_fmt_num(snap.macd_line)}\n"
            f"- current_rsi (7 period) = {_fmt_num(snap.rsi7)}\n\n"
            f"**Perpetual Futures Metrics:**\n"
            f"- Open Interest: Latest: {_fmt_num(snap.oi_latest)} | Average: {_fmt_num(snap.oi_avg)}\n"
            f"- Funding Rate: {_fmt_num(snap.funding_rate)}\n\n"
            # f"**Intraday Series (3-minute intervals, oldest → latest):**\n\n"
            # f"{self._format_intraday_section(snap)}\n"
            f"**Longer-term Context (4-hour timeframe):**\n\n"
            f"{self._format_context_section(snap)}\n"
            # f"Raw 3m candles (oldest→latest): {snap.raw_candles_3m}\n"
            # f"Raw 4h candles (oldest→latest): {snap.raw_candles_4h}\n"
            f"\n---\n\n"
        )

    def _prepare_positions(self, positions: List[Dict[str, Any]], price_map: Dict[str, float]) -> List[Dict[str, Any]]:
        """Normalize OKX positions into the richer schema for prompts."""
        prepared: List[Dict[str, Any]] = []

        def _to_float(val):
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _to_epoch_seconds(val):
            try:
                ts = float(val)
            except (TypeError, ValueError):
                return None
            # OKX 时间戳通常是毫秒
            if ts > 1e12:
                ts = ts / 1000.0
            return ts

        for p in positions:
            inst_id = p.get("instId") or p.get("symbol") or ""
            base = inst_id.split("-")[0] if inst_id else p.get("symbol", "")
            current_price = price_map.get(base) or price_map.get(inst_id)
            qty = _to_float(p.get("pos") or p.get("position") or p.get("sz"))
            pos_side_raw = p.get("posSide") or p.get("side") or p.get("direction")
            pos_side = pos_side_raw.lower() if isinstance(pos_side_raw, str) else None
            close_algos = p.get("closeOrderAlgo") or []
            profit_target = _to_float(
                p.get("profit_target")
                or p.get("take_profit")
                or p.get("tp")
                or p.get("tpTriggerPx")
            )
            stop_loss = _to_float(
                p.get("stop_loss")
                or p.get("sl")
                or p.get("stopLoss")
                or p.get("slTriggerPx")
            )
            invalidation_condition = p.get("invalidation_condition") or ""
            entry = _to_float(p.get("avgPx"))
            liq_px = _to_float(p.get("liqPx"))
            upl = _to_float(p.get("upl")) if p.get("upl") is not None else _to_float(p.get("uplRatio"))
            lev = _to_float(p.get("lever") or p.get("leverage"))
            notional = _to_float(p.get("notionalUsd"))
            if notional is None and current_price is not None:
                base_qty = _to_float(p.get("posCcy")) or qty
                if base_qty is not None:
                    try:
                        notional = base_qty * float(current_price)
                    except Exception:
                        notional = None

            c_time = _to_epoch_seconds(p.get("cTime") or p.get("ctime"))
            now_ts = datetime.now(timezone.utc).timestamp()
            hold_minutes = None
            if c_time is not None:
                try:
                    delta_sec = max(0.0, now_ts - c_time)
                    hold_minutes = int(delta_sec // 60)
                except Exception:
                    hold_minutes = None

            # 从 closeOrderAlgo 中提取当前挂着的 TP/SL（OKX 会把关联的算法平仓单挂在这里）
            if close_algos and isinstance(close_algos, list):
                algo = close_algos[0] or {}
                tp_candidate = algo.get("tpTriggerPx") or algo.get("tp")
                sl_candidate = algo.get("slTriggerPx") or algo.get("sl")
                profit_target = _to_float(profit_target or tp_candidate)
                stop_loss = _to_float(stop_loss or sl_candidate)

            prepared.append(
                {
                    "symbol": base or inst_id,
                    "quantity": qty,
                    "entry_price": entry,
                    "current_price": _to_float(current_price),
                    "liquidation_price": liq_px,
                    "unrealized_pnl": upl,
                    "leverage": lev,
                    "exit_plan": {
                        "profit_target": profit_target,
                        "stop_loss": stop_loss,
                        "invalidation_condition": invalidation_condition,
                    },
                    "position_side": pos_side,
                    "holding_minutes": hold_minutes,
                    "confidence": None,
                    "risk_usd": None,
                    "notional_usd": notional,
                }
            )
        return prepared

    def _account_blocks(
        self,
        balances: Dict[str, Any],
        price_map: Dict[str, float],
        positions: List[Dict[str, Any]],
    ) -> str:
        usdt_total = float(balances.get("USDT", {}).get("total", 0.0))

        prepared_positions = self._prepare_positions(positions, price_map)
        account_value = usdt_total + sum(p["notional_usd"] or 0 for p in prepared_positions)

        self._set_baseline(balances)
        return_pct = None
        if self.baseline_usdt and self.baseline_usdt > 0:
            return_pct = (account_value - self.baseline_usdt) / self.baseline_usdt * 100

        return (
            "## HERE IS YOUR ACCOUNT INFORMATION & PERFORMANCE\n\n"
            f"**Performance Metrics:**\n"
            f"- Current Total Return (percent): {return_pct if return_pct is not None else 'N/A'}%\n"
            f"- Sharpe Ratio: {'N/A'}\n\n"
            f"**Account Status:**\n"
            f"- Available Cash: ${usdt_total}\n"
            f"- **Current Account Value:** ${account_value}\n\n"
            "**Current Live Positions & Performance:**\n\n"
            f"{json.dumps(prepared_positions, ensure_ascii=False, indent=2)}\n\n"
        )

    def _format_positions(self, positions: List[Dict[str, Any]], price_map: Dict[str, float]) -> str:
        prepared = self._prepare_positions(positions, price_map)
        return json.dumps(prepared, ensure_ascii=False, indent=2) + "\n\n"

    def build_user_prompt(self, snapshots: Dict[str, PerpSymbolSnapshot], account: Dict[str, Any]) -> str:
        elapsed = int((datetime.now(timezone.utc) - self.start_time).total_seconds() // 60)

        body_blocks = ""
        price_map: Dict[str, float] = {}
        for sym, snap in snapshots.items():
            base = base_from_symbol(sym)
            price_map[base] = snap.current_price  # align with balance keys (e.g., "BTC")
            price_map[sym] = snap.current_price
            body_blocks += self._build_symbol_block(base, snap)

        balances = account.get("balances", {})
        positions = account.get("positions", [])
        account_block = self._account_blocks(balances, price_map, positions)
        return PERP_USER_PROMPT.format(
            elapsed_minutes=elapsed,
            market_blocks=body_blocks,
            account_block=account_block,
        )

    async def run_3min_cycle(self):
        """30分钟循环执行，价格触发可提前唤醒 agent。"""
        while True:
            self.cnt += 1
            nowtime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.info("当前日期：%s 开始执行第%s次循环", nowtime_str, self.cnt)

            # 清理未成交订单，确保余额可用
            try:
                cancel_result = getattr(self.exchange, "cancel_open_orders", lambda: {"requested": 0})()
                log.info("已尝试取消未成交订单: %s", cancel_result)
            except Exception as exc:
                log.warning("取消未成交订单失败: %s", exc)

            try:
                snapshots = fetch_perp_snapshots(
                    exchange=self.exchange, symbols=self.symbols, intraday_keep=INTRADAY_KEEP, context_keep=10
                )
            except Exception as exc:
                log.error("获取行情快照失败，跳过本轮: %s", exc)
                await asyncio.sleep(60)
                continue

            try:
                balances = self.exchange.fetch_balance()
                positions = getattr(self.exchange, "fetch_positions", lambda: [])()
            except Exception as exc:
                log.error("获取账户信息失败，跳过本轮: %s", exc)
                await asyncio.sleep(60)
                continue

            account_data = {
                "balances": balances,
                "positions": positions
            }
            user_prompt = self.build_user_prompt(snapshots, account_data)
            messages = {"messages": [
                    {"role": "user", "content": user_prompt}
                ]
            }
            log.info(user_prompt)
            try:
                result = price_agent.invoke(messages)
            except Exception as exc:
                log.error("Agent 调用失败，跳过本轮: %s", exc)
                await asyncio.sleep(60)
                continue
            log.info("Agent message list: %s", result)
            decision = result["structured_response"]
            log.info("Agent decision: %s", repr(decision))
            await asyncio.sleep(15 * 60)


if __name__ == "__main__":
    os.environ.setdefault("OKX_DEFAULT_TYPE", "swap")
    exchange = get_exchange()
    symbols = load_symbols(default=DEFAULT_SYMBOLS)
    agent = AutoTradeAgent(exchange=exchange, symbols=symbols)
    asyncio.run(agent.run_3min_cycle())
