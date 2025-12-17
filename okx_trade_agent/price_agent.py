# -*- coding: utf-8 -*-
"""Perpetual-aware price agent using configurable symbols."""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Sequence

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from okx_trade_agent.utils.model_decision import ModelResult
from okx_trade_agent.utils.price_tool import get_recent_candles
from okx_trade_agent.utils.okx_trade_tools import close_position, place_okx_order
from okx_trade_agent.utils.subscription import await_price_trigger
from okx_trade_agent.utils.symbols import DEFAULT_PERP_SYMBOLS, base_from_symbol, format_symbol_list, load_symbols

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

SYSTEM_PROMPT_TEMPLATE = Template(_read_text(PROJECT_ROOT / "prompts/system_prompt.txt"))

# Symbols are centrally loaded from env (OKX_SYMBOLS) to avoid prompt/tool mismatches.
SYMBOLS: Sequence[str] = load_symbols(default=DEFAULT_PERP_SYMBOLS)
PRIMARY_SYMBOL = SYMBOLS[0] if SYMBOLS else DEFAULT_PERP_SYMBOLS[0]
BASE_ASSET = base_from_symbol(PRIMARY_SYMBOL)
SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.safe_substitute(
    PRIMARY_SYMBOL=PRIMARY_SYMBOL,
    BASE_ASSET=BASE_ASSET,
    ALLOWED_SYMBOLS=format_symbol_list(SYMBOLS),

)

TOOLS = [get_recent_candles, place_okx_order, close_position, await_price_trigger]
# Propagate tool errors back to the model instead of raising to caller.
for _t in TOOLS:
    try:
        _t.handle_tool_error = True  # type: ignore[attr-defined]
    except Exception:
        pass

price_agent = create_agent(
    model="openai:deepseek-chat",
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
    response_format=ToolStrategy(ModelResult)  # structured JSON + summaries
)
