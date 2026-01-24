# OKX AI 交易机器人

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![LangChain](https://img.shields.io/badge/LangChain-Latest-orange.svg)

> 基于 LangChain/LangGraph 的 AI 驱动 OKX 加密货币自动交易框架

## ✨ 特性

- 🤖 **AI 驱动决策**：使用 LLM（DeepSeek/ChatGPT）分析市场并做出交易决策
- 📊 **多技术指标集成**：EMA、MACD、RSI、ATR、持仓量、资金费率等
- 💱 **多交易模式支持**：现货交易 & 永续合约（支持杠杆）
- 🔒 **安全机制**：默认模拟盘模式，风险可控的交易限额
- 🔄 **自动化循环**：可配置周期自动运行交易逻辑
- 🛠️ **灵活配置**：通过 `.env` 文件和环境变量轻松配置
- 📝 **完整日志**：详细的交易决策和执行日志，便于复盘

## 🏗️ 架构

```
okx_trade_agent/
├── agent.py              # 简单现货交易示例（BTC/USDT）
├── price_agent.py        # 永续合约价格分析 Agent
├── auto_trade.py         # 自动化交易循环
├── utils/
│   ├── okx_client.py     # OKX API 客户端封装（ccxt）
│   ├── tools.py          # 现货交易工具
│   ├── okx_trade_tools.py # 永续合约交易工具（官方 SDK）
│   ├── perp_market.py    # 市场数据与指标计算
│   ├── symbols.py        # 交易对管理
│   ├── market_data.py    # 市场数据处理
│   ├── asset_data.py     # 资产数据处理
│   ├── model_decision.py # 模型决策数据结构
│   ├── nodes.py          # LangGraph 节点
│   ├── state.py          # LangGraph 状态管理
│   ├── price_tool.py     # 价格查询工具
│   ├── subscription.py   # WebSocket 订阅
│   └── logger.py         # 日志管理
└── prompts/
    ├── system_prompt.txt # Agent 系统提示词
    └── perp_user_prompt.txt # 永续合约用户提示模板

auto_testing_generate/
└── agent.py              # 测试框架
```

## 🚀 快速开始

### 前置要求

- Python 3.9+
- OKX 账户（[注册链接](https://www.okx.com/join)）
- OpenAI API 密钥或 DeepSeek API 密钥

### 安装

```bash
# 克隆仓库
git clone https://github.com/miaoyuhan/ai_agent_full.git
cd ai_agent_full

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install ccxt langchain langgraph python-dotenv pandas openai okx
```

### 配置

1. 复制环境变量模板：
```bash
cp .env_example .env
```

2. 编辑 `.env` 文件，填入你的 API 密钥：

```env
# OKX API 配置
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_API_PASSPHRASE=your_okx_passphrase
OKX_SIMULATED=1  # 1=模拟盘（推荐）, 0=实盘

# LLM 配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.deepseek.com/v1  # 或使用 OpenAI 原生地址
```

3. （可选）配置交易对：
```env
OKX_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
OKX_DEFAULT_TYPE=swap  # swap=永续合约, spot=现货
```

### 运行

#### 1. 简单单次交易（现货）

```bash
python okx_trade_agent/agent.py
```

这会执行一次交易决策，支持：
- 查询 BTC/USDT 价格
- 查询账户余额
- 基于 SMA 金叉/死叉信号买卖
- 单笔交易限额 20 USDT

#### 2. 永续合约价格分析

```bash
python okx_trade_agent/price_agent.py
```

运行永续合约价格分析 Agent，获取：
- 多周期技术指标（3分钟、4小时）
- 市场深度和持仓量
- 资金费率
- 结构化交易决策

#### 3. 自动化交易循环

```bash
python okx_trade_agent/auto_trade.py
```

以 **30 分钟**为周期自动运行：
1. 获取市场快照
2. 查询账户状态
3. 调用 AI 做出决策
4. 执行交易（当前仅记录，需自行实现真实下单）

### 测试工具

```bash
# 测试 OKX 连接和配置
python -m okx_trade_agent.utils.okx_client

# 测试交易工具
python -m okx_trade_agent.utils.tools

# 测试永续合约工具
python okx_trade_agent/utils/okx_trade_tools.py
```

## 📖 核心功能

### 1. 现货交易工具

| 工具 | 功能 |
|------|------|
| `get_price` | 获取指定交易对的最新中间价 |
| `get_balance` | 查询指定资产的账户余额 |
| `get_signal` | 获取基于 SMA 的金叉/死叉信号 |
| `place_market_buy_usdt` | 使用 USDT 下市价买单 |
| `place_market_sell_all` | 将可用资产全部市价卖出 |

### 2. 永续合约交易工具

| 工具 | 功能 |
|------|------|
| `get_account_balance` | 获取账户余额信息 |
| `place_market_buy/sell` | 市价买卖 |
| `place_limit_order` | 限价订单 |
| `place_okx_order` | 永续合约限价单 + 止盈止损 |
| `close_position` | 平仓（reduce-only） |
| `place_algo_order` | 算法单（触发单/OCO/追踪止损/冰山单/TWAP） |
| `cancel_order` | 撤单 |

### 3. 市场数据指标

- **趋势指标**：EMA（20/50周期）
- **动量指标**：MACD、RSI（7/14周期）
- **波动指标**：ATR（3/14周期）
- **市场深度**：持仓量（OI）、资金费率
- **成交量分析**：当前成交量 vs 平均成交量

### 4. 智能决策流程

```
市场数据获取 → 指标计算 → LLM 分析 → 交易决策 → 风险检查 → 订单执行
```

## ⚙️ 高级配置

### 修改系统提示词

编辑 `okx_trade_agent/prompts/system_prompt.txt` 来自定义 Agent 的行为逻辑：

```
你是一个加密货币交易助手...
硬性规则：
- 仅当信号满足条件时交易
- 风险控制要求...
```

### 调整交易参数

在 `.env` 或代码中调整：
- 交易限额（默认 20 USDT）
- 最小余额要求（默认 5 USDT）
- 杠杆倍数（永续合约）
- 循环周期（默认 30 分钟）

### 切换实盘交易

⚠️ **警告**：实盘交易存在资金损失风险，请先在模拟盘充分测试！

修改 `.env`：
```env
OKX_SIMULATED=0
```

## 📝 交易示例

### 示例 1：现货买入

```python
from okx_trade_agent.utils.tools import get_price, place_market_buy_usdt

# 获取当前价格
price = get_price.invoke({"symbol": "BTC/USDT"})
print(f"BTC 价格: {price}")

# 买入 10 USDT 的 BTC
order = place_market_buy_usdt.invoke({"symbol": "BTC/USDT", "usdt": 10})
print(f"订单ID: {order['order_id']}")
```

### 示例 2：永续合约开仓

```python
from okx_trade_agent.utils.okx_trade_tools import place_okx_order

# 开多仓 BTC-USDT-SWAP
order = place_okx_order.invoke({
    "instId": "BTC-USDT-SWAP",
    "side": "buy",
    "posSide": "long",
    "usdt_amount": 100,
    "limit_px": 90000,
    "take_profit": 100000,
    "stop_loss": 85000,
    "td_mode": "isolated",
    "leverage": 5
})
```

## 🔒 安全建议

1. **始终从模拟盘开始**：设置 `OKX_SIMULATED=1` 充分测试策略
2. **设置交易限额**：控制单笔和总交易金额
3. **使用止盈止损**：永续合约交易务必设置 TP/SL
4. **定期检查日志**：监控 Agent 决策逻辑
5. **API 权限最小化**：仅授权必要的交易权限
6. **不要提交密钥**：`.env` 文件已在 `.gitignore` 中

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## ⚠️ 免责声明

**重要提示**：

- 本项目仅供学习和研究目的
- 加密货币交易存在极高的风险，可能导致全部资金损失
- AI 交易决策不代表必然盈利，过往表现不代表未来收益
- 作者不对使用本系统造成的任何损失负责
- 请在充分了解风险的前提下使用，并遵守当地法律法规

## 📧 联系方式

- 提交 Issue：[GitHub Issues](https://github.com/haoranaaa/ai_agent_full/issues)
- Email：997438111@qq.com

## 🔗 相关资源

- [OKX API 文档](https://www.okx.com/docs-v5/)
- [LangChain 文档](https://docs.langchain.com/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [ccxt 文档](https://docs.ccxt.com/)

---

⭐ 如果这个项目对你有帮助，请给它一个 Star！
