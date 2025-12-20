# -*- coding: utf-8 -*-
"""
Project-wide logging helpers.

Creates ./log/<project>_log.log automatically and exposes helpers to configure
the root logger once. Import get_logger() in any module to reuse the same file.
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT_DIR / "log"
PROJECT_NAME = ROOT_DIR.name  # e.g. "ai_agent_full"
LOG_FILE_BASE = LOG_DIR / "okx_trade_agent_log"

_configured: bool = False
_current_log_file: Optional[Path] = None


def setup_logging(level: int = logging.INFO) -> Path:
    """Ensure the root logger writes to ./log/<project>_log.log and stdout."""

    global _configured, _current_log_file
    if _configured:
        return _current_log_file or LOG_FILE_BASE.with_name(f"{LOG_FILE_BASE.name}_{datetime.now().strftime('%Y%m%d')}.log")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today_suffix = datetime.now().strftime("%Y%m%d")
    current_file = LOG_FILE_BASE.with_name(f"{LOG_FILE_BASE.name}_{today_suffix}.log")
    # backupCount=0 表示不删除旧文件，按日期无限保留（请注意磁盘占用）
    rotating_file_handler = TimedRotatingFileHandler(
        current_file, when="midnight", interval=1, backupCount=0, encoding="utf-8"
    )
    rotating_file_handler.suffix = "%Y%m%d"

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            rotating_file_handler,
        ],
    )
    _configured = True
    _current_log_file = current_file
    return current_file


def get_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Retrieve a module logger, configuring logging on first use."""

    setup_logging(level=level)
    return logging.getLogger(name)


__all__ = ["get_logger", "setup_logging"]
