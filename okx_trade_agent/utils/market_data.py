# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Market data helpers and models for the trading agent.

The models keep the agent input small but structured, so an LLM can reason
over multiple symbols and timeframes without repeatedly hitting the exchange.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import fmean
from typing import Any, Dict, Iterable, List, Literal, Sequence


# NOTE: 模型当前只关心 BTC/USDT 等少量标的的 1m/30m/1h/1d 线，
# 若未来扩展更多粒度，在这里追加即可。
Timeframe = Literal["1m", "30m", "1h", "1d"]


@dataclass(slots=True)
class Candle:
    """Single OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class TimeframeSeries:
    """Candles for a single timeframe."""

    timeframe: Timeframe
    candles: List[Candle]


@dataclass(slots=True)
class SymbolMarketSnapshot:
    """Aggregated market view for one trading pair."""

    symbol: str
    last_price: float
    last_updated: datetime
    series: Dict[Timeframe, TimeframeSeries]
    stats: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class MarketSnapshot:
    """Multi-symbol market data package that goes into each agent cycle."""

    generated_at: datetime
    symbols: Dict[str, SymbolMarketSnapshot]


PREFERRED_TIMEFRAMES: Sequence[Timeframe] = ("1m", "30m", "1h", "1d")
# close_history 控制每个时间粒度输出多少个 close 值，便于模型“复原”走势。
MODEL_CLOSE_HISTORY_OVERRIDES: Dict[Timeframe, int] = {"1m": 30, "30m": 12, "1h": 24, "1d": 7}
# window 控制统计指标的回看窗口，默认和 close_history 保持一致，便于解释。
MODEL_WINDOW_OVERRIDES: Dict[Timeframe, int] = {
    "1m": 30,
    "30m": 12,
    "1h": 24,
    "1d": 7,
}


def _to_candle(row: List[float]) -> Candle:
    ts, o, h, l, c, v = row
    return Candle(
        timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
        open=float(o),
        high=float(h),
        low=float(l),
        close=float(c),
        volume=float(v),
    )


def fetch_symbol_snapshot(
    exchange,
    symbol: str,
    timeframes: Iterable[Timeframe] = PREFERRED_TIMEFRAMES,
    limit: int = 120,
) -> SymbolMarketSnapshot:
    """
    Pull the latest ticker and OHLCV series for a single symbol.

    Args:
        exchange: OKX client instance.
        symbol: trading pair like 'BTC/USDT'.
        timeframes: iterable of requested timeframes.
        limit: number of candles per timeframe.
    """
    ticker = exchange.fetch_ticker(symbol)
    last_price = float(ticker.get("last") or ticker.get("close"))
    last_updated = datetime.fromtimestamp(ticker.get("timestamp", 0) / 1000, tz=timezone.utc)

    series: Dict[Timeframe, TimeframeSeries] = {}
    for timeframe in timeframes:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        series[timeframe] = TimeframeSeries(
            timeframe=timeframe,
            candles=[_to_candle(row) for row in ohlcv],
        )

    stats = {
        "24h_high": float(ticker.get("high", 0)),
        "24h_low": float(ticker.get("low", 0)),
        "24h_volume": float(ticker.get("baseVolume", 0)),
        "24h_change_pct": float(ticker.get("percentage", 0)),
    }

    return SymbolMarketSnapshot(
        symbol=symbol,
        last_price=last_price,
        last_updated=last_updated,
        series=series,
        stats=stats,
    )


def fetch_market_snapshot(
    exchange,
    symbols: Sequence[str],
    timeframes: Iterable[Timeframe] = PREFERRED_TIMEFRAMES,
    limit: int = 120,
) -> MarketSnapshot:
    """
    Fetch the structured market snapshot for multiple symbols.

    Any exception from the client bubbles up so the caller can decide whether to retry
    or fall back to cached data.
    """
    snapshots = {
        symbol: fetch_symbol_snapshot(exchange, symbol, timeframes=timeframes, limit=limit)
        for symbol in symbols
    }

    return MarketSnapshot(generated_at=datetime.now(tz=timezone.utc), symbols=snapshots)


# ---- Summaries for model consumption ---------------------------------------------------------
@dataclass(slots=True)
class TimeframeSummary:
    """Compact representation that LLMs can digest easily."""

    timeframe: Timeframe
    last_close: float
    change_pct: float | None
    range_pct: float
    avg_body: float
    volume_sum: float
    close_history: List[float]
    recent_candles: List[Candle]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "last_close": self.last_close,
            "change_pct": self.change_pct,
            "range_pct": self.range_pct,
            "avg_body": self.avg_body,
            "volume_sum": self.volume_sum,
            "close_history": self.close_history,
            "recent_candles": [
                {
                    "ts": candle.timestamp.isoformat(),
                    "o": candle.open,
                    "h": candle.high,
                    "l": candle.low,
                    "c": candle.close,
                    "v": candle.volume,
                }
                for candle in self.recent_candles
            ],
        }


def summarize_series(
    series: TimeframeSeries,
    window: int,
    keep_candles: int,
    close_history_len: int,
) -> TimeframeSummary:
    """Compress raw candles into a handful of statistics plus a short tail of raw bars."""

    candles = series.candles[-window:] if window > 0 else series.candles
    if not candles:
        raise ValueError(f"No candles available for timeframe {series.timeframe}")

    recent = candles[-keep_candles:]
    last_close = candles[-1].close
    prev_close = candles[-2].close if len(candles) >= 2 else None
    change_pct = None
    if prev_close and prev_close != 0:
        change_pct = (last_close - prev_close) / prev_close * 100

    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    range_pct = ((high - low) / low * 100) if low else 0.0

    avg_body = fmean(abs(c.close - c.open) for c in candles)
    volume_sum = sum(c.volume for c in candles)
    # close_history 让模型能快速看到“最近 N 根收盘价”的走势
    close_history = [c.close for c in candles[-close_history_len:]] if close_history_len > 0 else []

    return TimeframeSummary(
        timeframe=series.timeframe,
        last_close=last_close,
        change_pct=change_pct,
        range_pct=range_pct,
        avg_body=avg_body,
        volume_sum=volume_sum,
        close_history=close_history,
        recent_candles=recent,
    )


def snapshot_to_model_payload(
    snapshot: MarketSnapshot,
    window_overrides: Dict[Timeframe, int] | None = None,
    close_history_overrides: Dict[Timeframe, int] | None = None,
    keep_candles: int = 3,
) -> Dict[str, Any]:
    """
    Convert a MarketSnapshot to a lightweight dict that can be serialized for the LLM.
    """
    window_overrides = window_overrides or {}
    close_history_overrides = close_history_overrides or {}

    default_window = 20
    default_close_history = 5
    symbols_payload: Dict[str, Any] = {}
    for symbol, snap in snapshot.symbols.items():
        tf_payload = {
            tf: summarize_series(
                series,
                window=window_overrides.get(tf, default_window),
                keep_candles=keep_candles,
                close_history_len=close_history_overrides.get(tf, default_close_history),
            ).as_dict()
            for tf, series in snap.series.items()
        }
        symbols_payload[symbol] = {
            "last_price": snap.last_price,
            "last_updated": snap.last_updated.isoformat(),
            "stats": snap.stats,
            "timeframes": tf_payload,
        }

    return {
        "generated_at": snapshot.generated_at.isoformat(),
        "symbols": symbols_payload,
    }


def build_default_model_payload(snapshot: MarketSnapshot, keep_candles: int = 3) -> Dict[str, Any]:
    """Helper that applies the preferred history sizes discussed with the user."""

    return snapshot_to_model_payload(
        snapshot,
        window_overrides=MODEL_WINDOW_OVERRIDES,
        close_history_overrides=MODEL_CLOSE_HISTORY_OVERRIDES,
        keep_candles=keep_candles,
    )


def example_model_payload() -> Dict[str, Any]:
    """Static example that shows what the model receives after compression."""

    return {
        "generated_at": "2024-05-22T10:00:00+00:00",
        "symbols": {
            "BTC/USDT": {
                "last_price": 67123.4,
                "last_updated": "2024-05-22T09:59:00+00:00",
                "stats": {
                    "24h_high": 69000.0,
                    "24h_low": 65500.0,
                    "24h_volume": 18234.5,
                    "24h_change_pct": 1.8,
                },
                "timeframes": {
                    "1m": {
                        "last_close": 67120.1,
                        "change_pct": -0.08,
                        "range_pct": 0.2,
                        "avg_body": 7.5,
                        "volume_sum": 150.2,
                        "close_history": [
                            67180.0,
                            67170.5,
                            67160.0,
                            67145.2,
                            "...",  # 其余数值省略，这里一共有 30 个
                            67120.1,
                        ],
                        "recent_candles": [
                            {
                                "ts": "2024-05-22T09:57:00+00:00",
                                "o": 67140.0,
                                "h": 67150.0,
                                "l": 67120.0,
                                "c": 67135.0,
                                "v": 52.0,
                            },
                            {
                                "ts": "2024-05-22T09:58:00+00:00",
                                "o": 67135.0,
                                "h": 67140.0,
                                "l": 67105.0,
                                "c": 67115.0,
                                "v": 48.0,
                            },
                            {
                                "ts": "2024-05-22T09:59:00+00:00",
                                "o": 67115.0,
                                "h": 67125.0,
                                "l": 67100.0,
                                "c": 67120.1,
                                "v": 50.2,
                            },
                        ],
                    },
                    "30m": {
                        "last_close": 67120.1,
                        "change_pct": -0.25,
                        "range_pct": 0.8,
                        "avg_body": 25.0,
                        "volume_sum": 820.3,
                        "close_history": [67250.0, 67210.5, 67190.0, "...", 67120.1],  # 共 12 个
                        "recent_candles": "...",  # 实际数据同结构
                    },
                    "1h": {"...": "..."},
                    "1d": {"...": "..."},
                },
            },
            "DOGE/USDT": {"...": "..."},
            "ETH/USDT": {"...": "..."},
            "SOL/USDT": {"...": "..."},
        },
    }


def debug_market_data(symbols: Sequence[str] | None = None, keep_candles: int = 3) -> Dict[str, Any]:
    """
    Quick helper for manual testing: hits OKX client, builds the payload, and prints it.

    Returns:
        Dict[str, Any]: the same payload that would be sent to the LLM.
    """

    if not symbols:
        symbols = ["BTC/USDT", "DOGE/USDT", "ETH/USDT", "SOL/USDT"]

    # 延迟导入，避免工具模块在未装依赖时立刻初始化客户端。
    try:
        from .tools import get_exchange
    except ImportError:
        # 当用户以 `python okx_trade_agent/utils/market_data.py` 直接运行时，
        # 该模块没有父包信息，因此退回到绝对导入并动态补齐 sys.path。
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.append(str(repo_root))
        from okx_trade_agent.utils.tools import get_exchange

    exchange = get_exchange()
    snapshot = fetch_market_snapshot(exchange, symbols)
    payload = build_default_model_payload(snapshot, keep_candles=keep_candles)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    debug_market_data()
