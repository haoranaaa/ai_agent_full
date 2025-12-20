# -*- coding: utf-8 -*-
"""Slim price tool for the lightweight OKX agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Sequence

from langchain_core.tools import tool

from .get_exchange import get_exchange
from .logger import get_logger
from .symbols import DEFAULT_PERP_SYMBOLS

LOGGER = get_logger(__name__)

AllowedTimeframe = Literal["3m","15m", "30m", "1h", "4h", "1d"]
SUPPORTED_TIMEFRAMES: tuple[AllowedTimeframe, ...] = ("3m","15m", "30m", "1h", "4h", "1d")
MAX_CANDLES = 10
DEFAULT_SYMBOLS: Sequence[str] = DEFAULT_PERP_SYMBOLS


def _format_candle(row: List[float]) -> Dict[str, Any]:
    ts, o, h, l, c, v = row
    return {
        "ts": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
        "o": float(o),
        "h": float(h),
        "l": float(l),
        "c": float(c),
        "v": float(v),
    }


@tool
def get_recent_candles(symbol: str, timeframe: AllowedTimeframe) -> Dict[str, Any]:
    """Return the latest 10 OHLCV candles for a supported symbol in 15m/30m/1h/4h/1d granularity."""

    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Allowed: {SUPPORTED_TIMEFRAMES}")

    exchange = get_exchange()
    LOGGER.info("Fetching %s candles for %s", timeframe, symbol)
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=MAX_CANDLES)
    candles = [_format_candle(row) for row in ohlcv[-MAX_CANDLES:]]
    if not candles:
        raise ValueError("No candles returned from exchange")

    last_candle = candles[-1]
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "last_price": last_candle["c"],
        "last_updated": last_candle["ts"],
        "candles": candles,
        "close_history": [c["c"] for c in candles],
    }


__all__ = ["get_recent_candles"]
