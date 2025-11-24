# -*- coding: utf-8 -*-
"""Shared symbol helpers to keep symbol naming consistent across modules."""

from __future__ import annotations

import os
from typing import Iterable, List, Sequence

# Canonical default perpetual symbols (OKX style with settlement suffix)
DEFAULT_PERP_SYMBOLS: Sequence[str] = (
    "BTC/USDT:USDT",
    "DOGE/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
)


def _parse_symbols(raw: str | None, fallback: Sequence[str]) -> List[str]:
    if not raw:
        return list(fallback)
    return [s.strip() for s in raw.split(",") if s.strip()]


def load_symbols(env_var: str = "OKX_SYMBOLS", default: Sequence[str] | None = None) -> List[str]:
    """Load symbols from env (comma-separated), falling back to defaults."""

    fallback = default or DEFAULT_PERP_SYMBOLS
    raw = os.getenv(env_var)
    symbols = _parse_symbols(raw, fallback)
    return symbols


def base_from_symbol(symbol: str) -> str:
    """Extract base asset (e.g., BTC from BTC/USDT:USDT)."""

    if "/" in symbol:
        return symbol.split("/")[0]
    return symbol


def format_symbol_list(symbols: Iterable[str]) -> str:
    """Join symbols for prompt display."""

    return ", ".join(symbols)


__all__ = ["DEFAULT_PERP_SYMBOLS", "load_symbols", "base_from_symbol", "format_symbol_list"]
