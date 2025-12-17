"""Lightweight OKX client wrapper exposing ccxt-like methods using OKX SDK."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import datetime

from okx_trade_agent.utils.okx_trade_tools import (
    SIMULATED_FLAG,
    _get_account_client,
    _get_instrument,
    _get_market_client,
    _get_public_client,
    _get_trade_client,
    _quantize_size,
)


_BAR_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "1d": "1D",
}


def _symbol_to_inst_id(symbol: str) -> str:
    """Convert ccxt-style symbol to OKX instId (spot or swap)."""
    if symbol.endswith("-SWAP") and "-" in symbol:
        return symbol
    if "/" in symbol:
        base_quote = symbol.split(":")[0]  # drop settlement if present
        base, quote = base_quote.split("/")
        # If symbol already looks like perpetual (ccxt style with :USDT), treat as SWAP
        if ":USDT" in symbol or ":USD" in symbol:
            return f"{base}-{quote}-SWAP"
        return f"{base}-{quote}"
    return symbol


class OkxClient:
    """ccxt-like surface using official OKX SDK."""

    def __init__(self) -> None:
        self.market_api = _get_market_client()
        self.public_api = _get_public_client()
        self.account_api = _get_account_client()
        self.trade_api = _get_trade_client()

    # ---- market data ----
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        inst_id = _symbol_to_inst_id(symbol)
        res = self.market_api.get_ticker(instId=inst_id)
        data = res.get("data", [])
        if not data:
            raise RuntimeError(f"No ticker data for {inst_id}")
        tick = data[0]
        last = float(tick.get("last"))
        high = float(tick.get("high24h"))
        low = float(tick.get("low24h"))
        open_24h = float(tick.get("open24h"))
        ts = int(tick.get("ts"))
        base_vol = float(tick.get("vol", 0))
        pct = ((last - open_24h) / open_24h * 100) if open_24h else 0.0
        return {
            "symbol": symbol,
            "last": last,
            "close": last,
            "high": high,
            "low": low,
            "open": open_24h,
            "percentage": pct,
            "baseVolume": base_vol,
            "timestamp": ts,
            "datetime": datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).isoformat(),
            "bid": float(tick.get("bidPx")) if tick.get("bidPx") else None,
            "ask": float(tick.get("askPx")) if tick.get("askPx") else None,
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 120) -> List[List[float]]:
        inst_id = _symbol_to_inst_id(symbol)
        bar = _BAR_MAP.get(timeframe, timeframe)
        res = self.market_api.get_candlesticks(instId=inst_id, bar=bar, limit=limit)
        data = res.get("data", [])
        # OKX 返回按时间倒序，需要反转为升序
        rows = list(reversed(data))
        ohlcv: List[List[float]] = []
        for row in rows:
            ts = int(row[0])
            o, h, l, c, v = map(float, row[1:6])
            ohlcv.append([ts, o, h, l, c, v])
        return ohlcv

    def fetch_open_interest(self, symbol: str, instType: str = "SWAP") -> Dict[str, Any]:
        inst_id = _symbol_to_inst_id(symbol)
        res = self.public_api.get_open_interest(instId=inst_id, instType=instType)
        data = res.get("data", [])
        if not data:
            raise RuntimeError(f"No open interest for {inst_id}")
        item = data[0]
        oi = float(item.get("oi", 0))
        oi_ccy = float(item.get("oiCcy", 0))
        return {"symbol": symbol, "openInterestAmount": oi, "openInterestValue": oi_ccy}

    def fetch_funding_rate(self, symbol: str) -> Dict[str, Any]:
        inst_id = _symbol_to_inst_id(symbol)
        res = self.public_api.get_funding_rate(instId=inst_id)
        data = res.get("data", [])
        if not data:
            raise RuntimeError(f"No funding rate for {inst_id}")
        item = data[0]
        return {"symbol": symbol, "fundingRate": float(item.get("fundingRate", 0))}

    # ---- account ----
    def fetch_balance(self) -> Dict[str, Any]:
        res = self.account_api.get_account_balance()
        data = res.get("data", [])
        if not data:
            return {}
        details = data[0].get("details", [])
        balances: Dict[str, Any] = {}
        for d in details:
            ccy = d.get("ccy")
            if not ccy:
                continue
            avail = float(d.get("availBal", 0) or 0)
            total = float(d.get("bal", 0) or avail)
            used = total - avail
            balances[ccy] = {"free": avail, "used": used, "total": total}
        return balances

    def fetch_positions(self, inst_type: str = "SWAP", inst_id: str | None = None) -> List[Dict[str, Any]]:
        """Fetch all positions for the account (default SWAP)."""
        params: Dict[str, Any] = {"instType": inst_type}
        if inst_id:
            params["instId"] = inst_id
        res = self.account_api.get_positions(**params)
        return res.get("data", []) or []

    def fetch_account_and_positions(self, inst_type: str = "SWAP") -> Dict[str, Any]:
        """Convenience helper: balances + positions."""
        return {
            "balances": self.fetch_balance(),
            "positions": self.fetch_positions(inst_type=inst_type),
        }

    # ---- orders ----
    def fetch_open_orders(self, inst_type: str = None, inst_id: str | None = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if inst_id:
            params["instId"] = inst_id
        if inst_type:
            params["instType"] = inst_type
        res = self.trade_api.get_order_list(**params)
        return res.get("data", []) or []

    def cancel_open_orders(self, inst_type: str = None, inst_id: str | None = None) -> Dict[str, Any]:
        orders = self.fetch_open_orders(inst_type=inst_type, inst_id=inst_id)
        payload = []
        for o in orders:
            inst = o.get("instId")
            ord_id = o.get("ordId")
            if inst and ord_id:
                payload.append({"instId": inst, "ordId": ord_id})
        if not payload:
            return {"requested": 0, "orders": [], "raw": None}
        res = self.trade_api.cancel_multiple_orders(payload)
        # 如果单条失败，OKX 会在 data 中给出 sCode/sMsg，可在上层判断。
        return {"requested": len(payload), "orders": payload, "raw": res}

    # ---- trading (spot demo) ----
    def amount_to_precision(self, symbol: str, amount: float) -> float:
        inst_id = _symbol_to_inst_id(symbol)
        return float(_quantize_size(inst_id, float(amount)))

    def create_order(self, symbol: str, order_type: str, side: str, amount: float) -> Dict[str, Any]:
        inst_id = _symbol_to_inst_id(symbol)
        amount = self.amount_to_precision(symbol, amount)
        payload: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": side,
            "ordType": order_type,
            "sz": str(amount),
        }
        res = self.trade_api.place_order(**payload)
        if res.get("code") not in [None, "0"]:
            raise RuntimeError(f"Order failed: {res}")
        data = res.get("data", [{}])[0]
        return {"id": data.get("ordId"), "info": res, "filled": None, "side": side}


def get_okx_client() -> OkxClient:
    return OkxClient()


__all__ = ["OkxClient", "get_okx_client", "_symbol_to_inst_id"]


if __name__ == "__main__":
    # Quick manual test: cancel all open orders (any instType)
    client = get_okx_client()
    res = client.fetch_balance()
    print("Cancel open orders result:", res)
