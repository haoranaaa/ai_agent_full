# -*- coding: utf-8 -*-
"""Perpetual swap market snapshot with 3m cadence and common indicators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Sequence

import pandas as pd

from .logger import get_logger

LOGGER = get_logger(__name__)

AllowedTimeframe = Literal["3m", "4h"]


def _parse_ohlcv(row: List[float]) -> Dict[str, Any]:
    ts, o, h, l, c, v = row
    return {
        "ts": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
        "o": float(o),
        "h": float(h),
        "l": float(l),
        "c": float(c),
        "v": float(v),
    }


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _macd(series: pd.Series) -> pd.Series:
    ema12 = _ema(series, 12)
    ema26 = _ema(series, 26)
    return ema12 - ema26  # macd line


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - 100 / (1 + rs)
    return rsi


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["c"].shift(1)
    tr = pd.concat(
        [
            df["h"] - df["l"],
            (df["h"] - prev_close).abs(),
            (df["l"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


@dataclass
class PerpSymbolSnapshot:
    symbol: str  # e.g., BTC/USDT:USDT
    current_price: float
    ema20: float
    ema50: float | None
    macd_line: float | None
    rsi7: float | None
    rsi14: float | None
    oi_latest: float | None
    oi_avg: float | None
    funding_rate: float | None
    prices_3m: List[float]
    ema20_3m: List[float]
    macd_3m: List[float]
    rsi7_3m: List[float]
    rsi14_3m: List[float]
    ema20_4h: float | None
    ema50_4h: float | None
    atr3_4h: float | None
    atr14_4h: float | None
    volume_current_4h: float | None
    volume_avg_4h: float | None
    macd_4h: List[float]
    rsi14_4h: List[float]
    raw_candles_3m: List[Dict[str, Any]]
    raw_candles_4h: List[Dict[str, Any]]


def _compute_intraday_indicators(df: pd.DataFrame, keep: int) -> Dict[str, Any]:
    prices = df["c"]
    ema20_series = _ema(prices, 20)
    macd_series = _macd(prices)
    rsi7_series = _rsi(prices, 7)
    rsi14_series = _rsi(prices, 14)

    def _last_valid(series: pd.Series) -> float | None:
        s = series.dropna()
        return float(s.iloc[-1]) if len(s) else None

    return {
        "prices": prices.tail(keep).tolist(),
        "ema20": ema20_series.tail(keep).tolist(),
        "macd": macd_series.tail(keep).tolist(),
        "rsi7": rsi7_series.tail(keep).tolist(),
        "rsi14": rsi14_series.tail(keep).tolist(),
        "ema20_latest": _last_valid(ema20_series),
        "ema50_latest": _last_valid(_ema(prices, 50)) if len(prices) >= 50 else None,
        "macd_latest": _last_valid(macd_series),
        "rsi7_latest": _last_valid(rsi7_series),
        "rsi14_latest": _last_valid(rsi14_series),
    }


def _compute_4h_indicators(df: pd.DataFrame, keep: int) -> Dict[str, Any]:
    prices = df["c"]
    ema20 = _ema(prices, 20)
    ema50 = _ema(prices, 50)
    macd_series = _macd(prices)
    rsi14_series = _rsi(prices, 14)
    atr3 = _atr(df, 3)
    atr14 = _atr(df, 14)

    def _last_valid(series: pd.Series) -> float | None:
        s = series.dropna()
        return float(s.iloc[-1]) if len(s) else None

    return {
        "ema20_latest": _last_valid(ema20),
        "ema50_latest": _last_valid(ema50),
        "atr3_latest": _last_valid(atr3),
        "atr14_latest": _last_valid(atr14),
        "volume_current": float(df["v"].iloc[-1]) if len(df) else None,
        "volume_avg": float(df["v"].mean()),
        "macd_series": macd_series.tail(keep).tolist(),
        "rsi14_series": rsi14_series.tail(keep).tolist(),
    }


def fetch_perp_snapshot(
    exchange,
    symbol: str,
    intraday_timeframe: AllowedTimeframe = "3m",
    intraday_keep: int = 10,
    context_timeframe: AllowedTimeframe = "4h",
    context_keep: int = 10,
) -> PerpSymbolSnapshot:
    """Fetch 3m + 4h data and derive indicators for a single perpetual symbol."""

    ticker = exchange.fetch_ticker(symbol)
    current_price = float(ticker.get("last") or ticker.get("close"))

    ohlcv_3m = exchange.fetch_ohlcv(symbol, timeframe=intraday_timeframe, limit=max(intraday_keep * 3, 60))
    df_3m = pd.DataFrame(ohlcv_3m, columns=["ts", "o", "h", "l", "c", "v"])
    intraday = _compute_intraday_indicators(df_3m, intraday_keep)

    ohlcv_4h = exchange.fetch_ohlcv(symbol, timeframe=context_timeframe, limit=max(context_keep * 2, 30))
    df_4h = pd.DataFrame(ohlcv_4h, columns=["ts", "o", "h", "l", "c", "v"])
    ctx = _compute_4h_indicators(df_4h, context_keep)

    oi_latest = oi_avg = None
    funding_rate = None
    try:
        oi = exchange.fetch_open_interest(symbol)
        if oi:
            oi_latest = float(oi.get("openInterestAmount") or oi.get("openInterestValue") or oi.get("amount") or oi.get("value"))
            oi_avg = oi_latest  # lacking full series; treat latest as avg placeholder
    except Exception as exc:  # pragma: no cover - network/unsupported
        LOGGER.warning("fetch_open_interest failed for %s: %s", symbol, exc)

    try:
        fr = exchange.fetch_funding_rate(symbol)
        if fr:
            funding_rate = float(fr.get("fundingRate"))
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("fetch_funding_rate failed for %s: %s", symbol, exc)

    return PerpSymbolSnapshot(
        symbol=symbol,
        current_price=current_price,
        ema20=intraday["ema20_latest"],
        ema50=intraday["ema50_latest"],
        macd_line=intraday["macd_latest"],
        rsi7=intraday["rsi7_latest"],
        rsi14=intraday["rsi14_latest"],
        oi_latest=oi_latest,
        oi_avg=oi_avg,
        funding_rate=funding_rate,
        prices_3m=intraday["prices"],
        ema20_3m=intraday["ema20"],
        macd_3m=intraday["macd"],
        rsi7_3m=intraday["rsi7"],
        rsi14_3m=intraday["rsi14"],
        ema20_4h=ctx["ema20_latest"],
        ema50_4h=ctx["ema50_latest"],
        atr3_4h=ctx["atr3_latest"],
        atr14_4h=ctx["atr14_latest"],
        volume_current_4h=ctx["volume_current"],
        volume_avg_4h=ctx["volume_avg"],
        macd_4h=ctx["macd_series"],
        rsi14_4h=ctx["rsi14_series"],
        raw_candles_3m=[_parse_ohlcv(row) for row in ohlcv_3m[-intraday_keep:]],
        raw_candles_4h=[_parse_ohlcv(row) for row in ohlcv_4h[-context_keep:]],
    )


def fetch_perp_snapshots(
    exchange,
    symbols: Sequence[str],
    intraday_keep: int = 10,
    context_keep: int = 10,
) -> Dict[str, PerpSymbolSnapshot]:
    """Fetch perp snapshots for multiple symbols."""

    snapshots: Dict[str, PerpSymbolSnapshot] = {}
    for sym in symbols:
        snapshots[sym] = fetch_perp_snapshot(
            exchange,
            sym,
            intraday_keep=intraday_keep,
            context_keep=context_keep,
        )
    return snapshots


__all__ = ["PerpSymbolSnapshot", "fetch_perp_snapshot", "fetch_perp_snapshots"]
