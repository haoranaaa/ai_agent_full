import asyncio
import json
from typing import List
from datetime import datetime
import ccxt

from okx_trade_agent.utils import market_data
from okx_trade_agent.utils.asset_data import get_asset
from okx_trade_agent.utils.get_exchange import get_exchange
from okx_trade_agent.utils.logger import get_logger

log = get_logger(__name__)
class AutoTradeAgent:

    exchange: ccxt.Exchange

    symbols: List[str]

    cnt: int = 0

    def __init__(self, exchange: ccxt.Exchange, symbols: List[str]):
        self.exchange = exchange
        self.symbols = symbols
        # self.memory = MemorySystem()
        # self.tools = ToolKit(self.exchange, self.memory)

    async def run_30min_cycle(self):
        """30分钟循环执行"""
        while True:
            self.cnt += 1
            nowtimeStr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log.info("当前日期：" + nowtimeStr + " 开始执行第"+ str(self.cnt)+"次循环")
            # 1. 获取市场数据
            data = market_data.fetch_market_snapshot(exchange=self.exchange, symbols=self.symbols)

            log.info("markDataSnapshot:" + {json.dump(data)})
            # 2. 获取账户信息
            account_info = get_asset(exchange=self.exchange)
            log.info(account_info)

            # 3. 构建模型输入
            context = self.build_agent_context(market_data, account_info)

            # 4. 调用模型决策
            decision = await self.agent_decision(context)

            # 5. 执行交易
            if decision.should_execute:
                await self.execute_trade(decision)

            # 6. 等待下一个周期
            await asyncio.sleep(30 * 60)

if __name__ == '__main__':
    exchange = get_exchange()
    agent = AutoTradeAgent(exchange=exchange, symbols=["BTC/USDT", "DOGE/USDT", "ETC/USDT", "SOL/USDT"])
    asyncio.run(agent.run_30min_cycle())
