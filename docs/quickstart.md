# 快速开始指南

## 安装和配置

### 1. 环境准备

确保你有 Python 3.9+：

```bash
python --version
```

### 2. 克隆项目

```bash
git clone https://github.com/miaoyuhan/ai_agent_full.git
cd ai_agent_full
```

### 3. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate  # Windows
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的配置：

```env
# 必须配置
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_API_PASSPHRASE=your_okx_passphrase
OPENAI_API_KEY=your_openai_or_deepseek_key

# 安全设置
OKX_SIMULATED=1  # 先用模拟盘测试

# LLM 配置（二选一）
# 使用 DeepSeek（推荐）
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

# 或使用 OpenAI
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini
```

## 第一次运行

### 测试现货交易

```bash
python okx_trade_agent/agent.py
```

这将：
1. 查询 BTC/USDT 当前价格
2. 查询你的账户余额
3. 根据技术指标做出交易决策
4. （模拟盘）执行交易

### 测试永续合约

```bash
python okx_trade_agent/price_agent.py
```

这将：
1. 获取多个币种的市场数据
2. 计算技术指标
3. AI 分析市场趋势
4. 输出交易建议

### 运行自动交易

```bash
python okx_trade_agent/auto_trade.py
```

这将每30分钟自动：
1. 扫描市场机会
2. AI 做出决策
3. 执行交易策略

## 常见问题

### Q: 如何获取 OKX API 密钥？

A: 
1. 登录 [OKX](https://www.okx.com)
2. 进入 API 管理
3. 创建新的 API Key
4. 记录 API Key、Secret、Passphrase

### Q: 如何选择 LLM？

A: 
- **DeepSeek**: 性价比高，中文友好，推荐
- **OpenAI**: 质量稳定，但成本较高

### Q: 模拟盘和实盘有什么区别？

A: 
- **模拟盘**: 使用虚拟资金，零风险，适合测试
- **实盘**: 使用真实资金，有盈亏，请谨慎

### Q: 如何切换交易对？

A: 
修改 `.env` 文件中的 `OKX_SYMBOLS`：
```env
OKX_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
```

### Q: 如何设置风险控制？

A: 
在 `.env` 文件中配置：
```env
SPOT_BUY_CAP_USDT=20        # 单笔最大买入
SPOT_MIN_BALANCE_USDT=5     # 最小余额要求
MAX_LOSS_RATIO=0.05         # 最大亏损比例
DAILY_MAX_LOSS_USDT=100     # 日最大亏损
```

## 进阶使用

### 自定义交易策略

编辑 `okx_trade_agent/prompts/system_prompt.txt`：

```text
你是一个加密货币交易助手...
自定义你的交易逻辑...
```

### 添加新指标

在 `okx_trade_agent/utils/perp_market.py` 中添加新指标：

```python
def _custom_indicator(series: pd.Series, period: int) -> pd.Series:
    # 你的指标计算逻辑
    return result
```

### 监控和通知

配置 Telegram 或邮件通知：

```env
# Telegram 通知
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 邮件通知
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_TO=notification@example.com
```

## 安全提醒

⚠️ **重要安全提示**

1. **永远不要提交 `.env` 文件**到代码仓库
2. **先在模拟盘充分测试**，确认策略有效
3. **使用小额资金**开始实盘交易
4. **设置合理的止损**，控制单笔风险
5. **定期更换 API 密钥**，确保账户安全
6. **监控交易日志**，及时发现异常

## 获取帮助

- 📖 查看 [API 文档](api.md)
- 🐛 报告 [Issues](https://github.com/miaoyuhan/ai_agent_full/issues)
- 💬 参与 [讨论](https://github.com/miaoyuhan/ai_agent_full/discussions)
- 📧 联系: your.email@example.com

---

祝你交易顺利！🚀