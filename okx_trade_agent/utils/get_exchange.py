# -*- coding: utf-8 -*-
"""
Centralized OKX exchange factory.

The module keeps a single ccxt client alive in memory so that we do not reload
markets and auth state on every tool call. Import this helper wherever the
agent needs to talk to OKX.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import ccxt
from dotenv import load_dotenv

from .logger import get_logger

LOGGER = get_logger(__name__)

# Locate project root (where .env lives) and load credentials once.
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

_exchange: Optional[ccxt.Exchange] = None
_lock = threading.Lock()


def _build_client_config() -> dict:
    """Compose the ccxt okx constructor payload from env variables."""

    proxies = {}
    http_proxy = os.getenv("HTTP_PROXY")
    https_proxy = os.getenv("HTTPS_PROXY")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy

    config = {
        "apiKey": os.getenv("OKX_API_KEY"),
        "secret": os.getenv("OKX_API_SECRET"),
        "password": os.getenv("OKX_API_PASSPHRASE"),
        # 模拟盘默认打开；若要切换实盘可通过环境变量控制
        "headers": {"x-simulated-trading": os.getenv("OKX_SIMULATED", "0")},
        "options": {"defaultType": "spot"},
    }

    if proxies:
        config["proxies"] = proxies

    missing = [key for key in ("apiKey", "secret", "password") if not config.get(key)]
    if missing:
        LOGGER.warning("OKX credentials are incomplete: %s", ", ".join(missing))

    return config


def _create_exchange() -> ccxt.Exchange:
    """Instantiate a fresh ccxt OKX client with the current configuration."""

    cfg = _build_client_config()
    exchange = ccxt.okx(cfg)
    LOGGER.info("Initialized OKX exchange (simulated=%s)", cfg["headers"]["x-simulated-trading"])
    return exchange


def get_exchange() -> ccxt.Exchange:
    """
    Return a cached OKX exchange instance.

    The first call creates the client; subsequent calls reuse it so login state
    and loaded markets stay in memory.
    """

    global _exchange
    if _exchange is None:
        with _lock:
            if _exchange is None:
                _exchange = _create_exchange()
                try:
                    _exchange.load_markets()
                except Exception as exc:  # pragma: no cover - network failure
                    LOGGER.warning("Failed to pre-load markets: %s", exc)
    return _exchange


def refresh_exchange() -> ccxt.Exchange:
    """
    Force creation of a new exchange client.

    Useful when credentials change at runtime.
    """

    global _exchange
    with _lock:
        _exchange = _create_exchange()
    return _exchange


__all__ = ["get_exchange", "refresh_exchange"]
