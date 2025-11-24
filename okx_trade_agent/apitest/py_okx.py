import okx.MarketData as MarketData
import okx.PublicData as PublicData
import asyncio
from okx.websocket.WsPublicAsync import WsPublicAsync

flag = "1"  # live trading: 0, demo trading: 1

marketDataAPI = MarketData.MarketAPI(flag=flag)

def callbackFunc(message):
    print(message)

async def main():
    ws = WsPublicAsync(url="wss://wspap.okx.com:8443/ws/v5/public")
    await ws.start()
    args = [
        {
          "channel": "open-interest",
          "instId": "LTC-USD-SWAP"
        }
    ]

    await ws.subscribe(args, callback=callbackFunc)
    await asyncio.sleep(10)

    await ws.unsubscribe(args, callback=callbackFunc)
    await asyncio.sleep(10)

asyncio.run(main())
