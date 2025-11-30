# -*- coding: utf-8 -*-
"""Centralized OKX exchange factory using official SDK (ccxt-like surface)."""

from __future__ import annotations

from typing import Optional

from okx_trade_agent.utils.okx_client import OkxClient, get_okx_client

_exchange: Optional[OkxClient] = None


def _create_exchange() -> OkxClient:
    """Instantiate a fresh OKX client with the current configuration."""
    return get_okx_client()


def get_exchange() -> OkxClient:
    """Return a cached OKX client instance."""
    global _exchange
    if _exchange is None:
        _exchange = _create_exchange()
    return _exchange


def refresh_exchange() -> OkxClient:
    """Force creation of a new OKX client (e.g., after credential refresh)."""
    global _exchange
    _exchange = _create_exchange()
    return _exchange


__all__ = ["get_exchange", "refresh_exchange"]
