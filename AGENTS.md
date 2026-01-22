# AGENTS.md

This file contains guidelines and commands for agentic coding agents working in this repository.

## Project Overview

This is a Python-based AI trading agent system that uses LangChain, LangGraph, and OKX API for cryptocurrency trading. The project consists of:

- `okx_trade_agent/` - Main trading agent with OKX integration
- `auto_testing_generate/` - Testing and validation framework
- LangGraph-based agent orchestration

## Build/Lint/Test Commands

### Python Environment Setup
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies (no requirements.txt found, install manually)
pip install ccxt langchain langgraph python-dotenv pandas openai
```

### Running the Application
```bash
# Run main trading agent
python okx_trade_agent/agent.py

# Run price agent
python okx_trade_agent/price_agent.py

# Run automated trading loop
python okx_trade_agent/auto_trade.py

# Run testing framework
python auto_testing_generate/agent.py
```

### LangGraph Commands
```bash
# List available graphs
langgraph list

# Run specific graph
langgraph run okx_trade_agent
langgraph run okx_price_agent

# Serve graphs
langgraph serve
```

### Testing
```bash
# No formal test suite found - run modules directly for testing
python -m okx_trade_agent.utils.okx_client
python -m okx_trade_agent.utils.tools
```

## Code Style Guidelines

### Import Organization
```python
# Standard library imports first
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Third-party imports
import logging
import pandas as pd
from dotenv import load_dotenv
from langchain.agents import create_agent, AgentState
from langchain_core.tools import tool
from langgraph.runtime import Runtime

# Local imports
from okx_trade_agent.utils.get_exchange import get_exchange
from okx_trade_agent.utils.logger import get_logger
```

### Type Hints
- Use type hints for all function parameters and return values
- Import from `typing` module: `Any`, `Dict`, `List`, `Optional`
- Use `from __future__ import annotations` for forward references in complex modules

### Naming Conventions
- **Variables**: `snake_case` (e.g., `symbol`, `timeframe`, `usdt_amount`)
- **Functions**: `snake_case` (e.g., `get_price`, `place_market_buy`)
- **Classes**: `PascalCase` (e.g., `ModelResult`, `AgentState`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `SYMBOL`, `TIMEFRAME`, `SHORT`, `LONG`)
- **Private functions**: `_underscore_prefix` (e.g., `_retry_api_call`, `_symbol_to_inst_id`)

### Error Handling
```python
# Use specific exceptions with descriptive messages
if symbol != SYMBOL:
    raise ValueError("Only BTC/USDT allowed in this demo.")
if usdt <= 0 or usdt > 20:
    raise ValueError("usdt must be (0, 20].")

# Use try-except for API calls with logging
try:
    order = okx.create_order(symbol, "market", "buy", float(amount))
    return {"order_id": order["id"], "side": "buy", "filled": order.get("filled", None)}
except Exception as e:
    logger.error(f"Failed to place order: {e}")
    raise
```

### Logging
- Use the centralized logger from `okx_trade_agent.utils.logger`
- Import as: `from okx_trade_agent.utils.logger import get_logger`
- Initialize: `logger = get_logger(__name__)`
- Log levels: `logger.info()`, `logger.error()`, `logger.debug()`

### Tool Definition Pattern
```python
@tool
def function_name(param1: type1, param2: type2 = default) -> return_type:
    """Brief description of what the tool does.
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2 (optional)
    
    Returns:
        Description of return value
    """
    # Implementation
    return result
```

### Environment Configuration
- Use `.env` file for configuration (see `.env_example`)
- Load with `load_dotenv()` at module level
- Access with `os.getenv()`
- Required keys: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE`

### File Structure
```
okx_trade_agent/
├── agent.py              # Main agent implementation
├── price_agent.py        # Price analysis agent
├── auto_trade.py         # Automated trading loop
├── utils/
│   ├── __init__.py
│   ├── okx_client.py     # OKX API wrapper
│   ├── tools.py          # Trading tools
│   ├── logger.py         # Logging utilities
│   ├── market_data.py    # Market data processing
│   └── ...
└── prompts/
    ├── system_prompt.txt
    └── perp_user_prompt.txt
```

### LangChain Agent Pattern
```python
# Define tools
TOOLS = [get_price, get_balance, get_signal, place_market_buy_usdt, place_market_sell_all]

# Define middleware
MIDDLEWARE = [wrap_tool_call, log_before_model, log_before_agent, log_after_model, log_after_agent]

# Create agent
agent = create_agent(
    model="openai:deepseek-chat", 
    tools=TOOLS, 
    system_prompt=SYSTEM,
    middleware=MIDDLEWARE
)
```

### Documentation
- Use docstrings for all functions and classes
- Include Chinese comments where appropriate (project uses mixed languages)
- Keep prompts in `prompts/` directory, separate from code

### Security Best Practices
- Never commit API keys or secrets
- Use environment variables for all sensitive data
- Validate all user inputs and API parameters
- Use simulated trading mode by default (`OKX_SIMULATED=1`)

## Development Workflow

1. Set up environment and install dependencies
2. Copy `.env_example` to `.env` and configure API keys
3. Test with simulated trading first (`OKX_SIMULATED=1`)
4. Use LangGraph for agent orchestration
5. Log all decisions and actions for debugging
6. Validate tools and agents before live trading

## Key Dependencies

- `ccxt` - Cryptocurrency exchange trading library
- `langchain` - LLM framework for agent creation
- `langgraph` - Agent orchestration and runtime
- `python-dotenv` - Environment variable management
- `pandas` - Data manipulation and analysis
- `openai` - OpenAI API client (used with DeepSeek)