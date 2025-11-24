import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

import ccxt

from okx_trade_agent.price_agent import price_agent
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

    exchange: ccxt.Exchange
    symbols: List[str]
    cnt: int = 0
    baseline_usdt: float | None = None
    start_time: datetime

    def __init__(self, exchange: ccxt.Exchange, symbols: List[str]):
        self.exchange = exchange
        self.symbols = symbols
        self.start_time = datetime.now(timezone.utc)

    def _set_baseline(self, balances: Dict[str, Any]):
        if self.baseline_usdt is None:
            self.baseline_usdt = float(balances.get("USDT", {}).get("total", 0.0))
            log.info("Baseline USDT set to %.4f", self.baseline_usdt)

    def _format_intraday_section(self, snap: PerpSymbolSnapshot) -> str:
        return (
            f"Mid prices: {_fmt_seq(snap.prices_3m)}\n"
            f"EMA indicators (20-period): {_fmt_seq(snap.ema20_3m)}\n"
            f"MACD indicators: {_fmt_seq(snap.macd_3m)}\n"
            f"RSI indicators (7-Period): {_fmt_seq(snap.rsi7_3m)}\n"
            f"RSI indicators (14-Period): {_fmt_seq(snap.rsi14_3m)}\n"
        )

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
            f"**Intraday Series (3-minute intervals, oldest → latest):**\n\n"
            f"{self._format_intraday_section(snap)}\n"
            f"**Longer-term Context (4-hour timeframe):**\n\n"
            f"{self._format_context_section(snap)}\n"
            f"Raw 3m candles (oldest→latest): {snap.raw_candles_3m}\n"
            f"Raw 4h candles (oldest→latest): {snap.raw_candles_4h}\n"
            f"\n---\n\n"
        )

    def _account_blocks(
        self,
        balances: Dict[str, Any],
        price_map: Dict[str, float],
        symbols: Sequence[str],
        min_notional_usdt: float = 0.1,
    ) -> str:
        usdt_total = float(balances.get("USDT", {}).get("total", 0.0))

        positions = []
        skip_keys = {"info", "free", "used", "total", "timestamp", "datetime"}
        for base, bal_info in balances.items():
            if base in skip_keys or not isinstance(bal_info, dict):
                continue
            qty = float(bal_info.get("total", 0.0))
            if qty <= 0:
                continue
            price = price_map.get(base, 0.0)
            notional = qty * price
            if notional < min_notional_usdt:
                continue
            positions.append(
                {
                    "symbol": base,
                    "quantity": qty,
                    "entry_price": None,
                    "current_price": price,
                    "liquidation_price": None,
                    "unrealized_pnl": None,
                    "leverage": 1,
                    "exit_plan": {
                        "profit_target": None,
                        "stop_loss": None,
                        "invalidation_condition": "",
                    },
                    "confidence": None,
                    "risk_usd": None,
                    "notional_usd": notional,
                }
            )

        positions_str = "[]"
        if positions:
            positions_str = str(positions)

        account_value = usdt_total + sum(p["notional_usd"] for p in positions)

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
            f"{positions_str}\n\n"
        )

    def build_user_prompt(self, snapshots: Dict[str, PerpSymbolSnapshot], balances: Dict[str, Any]) -> str:
        elapsed = int((datetime.now(timezone.utc) - self.start_time).total_seconds() // 60)

        body_blocks = ""
        price_map: Dict[str, float] = {}
        for sym, snap in snapshots.items():
            base = base_from_symbol(sym)
            price_map[base] = snap.current_price  # align with balance keys (e.g., "BTC")
            price_map[sym] = snap.current_price
            body_blocks += self._build_symbol_block(base, snap)

        account_block = self._account_blocks(balances, price_map, self.symbols)
        return PERP_USER_PROMPT.format(
            elapsed_minutes=elapsed,
            market_blocks=body_blocks,
            account_block=account_block,
        )

    async def run_30min_cycle(self):
        """30分钟循环执行，使用精简 agent 完成决策。"""
        while True:
            self.cnt += 1
            nowtime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.info("当前日期：%s 开始执行第%s次循环", nowtime_str, self.cnt)

            snapshots = fetch_perp_snapshots(
                exchange=self.exchange, symbols=self.symbols, intraday_keep=INTRADAY_KEEP, context_keep=10
            )
            balances = self.exchange.fetch_balance()

            user_prompt = self.build_user_prompt(snapshots, balances)
            messages = {"messages": [{"role": "user", "content": user_prompt}]}

            result = price_agent.invoke(messages)
            log.info("Agent message list: %s", result)
            decision = result["structured_response"]
            log.info("Agent decision: %s", repr(decision))

            # TODO: translate decision JSON array into concrete trades using utils.tools.* as needed.

            await asyncio.sleep(30 * 60)


if __name__ == "__main__":
    os.environ.setdefault("OKX_DEFAULT_TYPE", "swap")
    exchange = get_exchange()
    symbols = load_symbols(default=DEFAULT_SYMBOLS)
    agent = AutoTradeAgent(exchange=exchange, symbols=symbols)
    asyncio.run(agent.run_30min_cycle())
