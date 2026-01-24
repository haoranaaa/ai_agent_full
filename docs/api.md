# API 文档

## OKX 交易工具

### 现货交易

#### get_price
获取指定交易对的最新中间价。

**参数：**
- `symbol` (str): 交易对代码，如 'BTC/USDT'

**返回：**
- `float`: 买一卖一的平均价格

**示例：**
```python
from okx_trade_agent.utils.tools import get_price
price = get_price.invoke({"symbol": "BTC/USDT"})
```

#### get_balance
查询指定资产的账户余额。

**参数：**
- `asset` (str): 资产代码，如 'USDT' 或 'BTC'

**返回：**
```python
{
    "asset": "USDT",
    "free": 100.0,
    "total": 100.0
}
```

#### get_signal
获取基于 SMA 的金叉/死叉交易信号。

**参数：**
- `symbol` (str): 交易对代码
- `timeframe` (str): K线周期，默认 '1m'
- `short` (int): 短周期 SMA，默认 20
- `long` (int): 长周期 SMA，默认 50

**返回：**
```python
{
    "signal": "golden_cross_buy",  # 或 "death_cross_sell", "hold"
    "price": 50000.0
}
```

#### place_market_buy_usdt
使用 USDT 下市价买单。

**参数：**
- `symbol` (str): 交易对，必须为 'BTC/USDT'
- `usdt` (float): 购买金额 USDT，范围 (0, 20]

**返回：**
```python
{
    "order_id": "12345",
    "side": "buy",
    "filled": 0.001
}
```

#### place_market_sell_all
将可用资产全部市价卖出。

**参数：**
- `symbol` (str): 交易对，必须为 'BTC/USDT'

**返回：**
```python
{
    "order_id": "12346",
    "side": "sell",
    "filled": 0.001
}
```

### 永续合约交易

#### place_okx_order
永续合约限价单 + 止盈止损。

**参数：**
- `instId` (str): 合约ID，如 'BTC-USDT-SWAP'
- `side` (str): 买卖方向，'buy' 或 'sell'
- `posSide` (str): 持仓方向，'long' 或 'short'
- `usdt_amount` (float): 保证金金额（USDT）
- `limit_px` (float): 限价
- `take_profit` (float): 止盈价格
- `stop_loss` (float): 止损价格
- `td_mode` (str): 交易模式，默认 'isolated'
- `leverage` (int): 杠杆倍数，默认 1

**返回：**
```python
{
    "instId": "BTC-USDT-SWAP",
    "order_id": "12347",
    "price": 50000.0,
    "size": "0.001",
    "take_profit": 55000.0,
    "stop_loss": 45000.0
}
```

#### close_position
平掉指定方向的持仓。

**参数：**
- `instId` (str): 合约ID
- `posSide` (str): 持仓方向，'long' 或 'short'
- `close_px` (float): 平仓限价
- `td_mode` (str): 交易模式，默认 'isolated'

**返回：**
```python
{
    "instId": "BTC-USDT-SWAP",
    "order_id": "12348",
    "price": 50000.0,
    "size": "0.001"
}
```

#### place_algo_order
算法单下单。

**参数：**
- `inst_id` (str): 合约ID
- `side` (str): 买卖方向
- `ord_type` (str): 订单类型
  - `trigger`: 价格触发单
  - `conditional`: 条件单（止盈/止损）
  - `oco`: 同时止盈止损
  - `trailing`: 追踪止损
  - `iceberg`: 冰山单
  - `twap`: TWAP
- 其他参数详见函数文档

## 市场数据

### PerpSymbolSnapshot
永续合约市场快照数据结构。

**属性：**
- `symbol` (str): 合约代码
- `current_price` (float): 当前价格
- `ema20` (float): 20周期EMA
- `ema50` (float): 50周期EMA
- `macd_line` (float): MACD线
- `rsi7` (float): 7周期RSI
- `rsi14` (float): 14周期RSI
- `oi_latest` (float): 最新持仓量
- `oi_avg` (float): 平均持仓量
- `funding_rate` (float): 资金费率
- 其他指标...

## 配置说明

### 环境变量

所有配置通过环境变量或 `.env` 文件管理。详见 `.env.example`。

### 日志配置

项目使用统一的日志系统：

```python
from okx_trade_agent.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("日志信息")
logger.error("错误信息")
```

## 错误处理

所有函数都有完整的错误处理：

```python
try:
    result = get_price.invoke({"symbol": "BTC/USDT"})
except ValueError as e:
    logger.error(f"参数错误: {e}")
except Exception as e:
    logger.error(f"系统错误: {e}")
```