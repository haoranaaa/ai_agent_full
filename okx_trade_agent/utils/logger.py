# -*- coding: utf-8 -*-
"""
Project-wide logging helpers.

Creates ./log/<project>_log.log automatically and exposes helpers to configure
the root logger once. Import get_logger() in any module to reuse the same file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT_DIR / "log"
PROJECT_NAME = ROOT_DIR.name  # e.g. "ai_agent_full"
LOG_FILE = LOG_DIR / f"okx_trade_agent_log.log"

_configured: bool = False


def setup_logging(level: int = logging.INFO) -> Path:
    """Ensure the root logger writes to ./log/<project>_log.log and stdout."""

    global _configured
    if _configured:
        return LOG_FILE

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
    _configured = True
    return LOG_FILE


def get_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Retrieve a module logger, configuring logging on first use."""

    setup_logging(level=level)
    return logging.getLogger(name)


__all__ = ["get_logger", "setup_logging", "LOG_FILE"]
