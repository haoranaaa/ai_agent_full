# -*- coding: utf-8 -*-
"""Structured model decision schema aligned with system_prompt output."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel

Signal = Literal["buy_to_enter", "sell_to_enter", "hold", "close"]


class ModelDecision(BaseModel):
    """Represents the single JSON object the model must return."""

    signal: Signal
    coin: str
    quantity: float
    leverage: int
    profit_target: float
    stop_loss: float
    invalidation_condition: str
    confidence: float
    risk_usd: float
    justification: str


class ModelResult(BaseModel):
    """Container for multiple decisions plus concise summaries."""

    action_summary: str
    reasoning_summary: str


__all__ = ["ModelDecision", "ModelResult", "Signal"]
