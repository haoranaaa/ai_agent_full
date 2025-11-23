import ccxt

from okx_trade_agent.utils.get_exchange import get_exchange

def get_asset(exchange: ccxt.Exchange):
    return exchange.fetch_balance()


