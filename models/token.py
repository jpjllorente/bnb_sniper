"""
Domain model representing a cryptocurrency token.

This class encapsulates basic attributes such as contract address, name and
risk score. Additional attributes can be added as needed (e.g. decimals,
symbol, liquidity, etc.).
"""

from __future__ import annotations

from pydantic import BaseModel
import time


class Token(BaseModel):
    
    pair_address: str
    name: str
    symbol: str
    address: str
    price_native: float
    price_usd: float
    pair_created_at: int
    liquidity: float
    volume: float
    buys: int
    image_url: str
    open_graph: str
    buy_tax: float = 0.0
    sell_tax: float = 0.0
    status: str = ""  # Default status
    timestamp: int = int(time.time())

    @classmethod
    def from_dexscreener(cls, raw: dict) -> "Token":
        base = raw.get("baseToken", {})
        return cls(
            pair_address=raw.get("pairAddress", ""),
            name=base.get("name", ""),
            symbol=base.get("symbol", ""),
            address=base.get("address", ""),
            price_native=float(raw.get("priceNative", 0)),
            price_usd=float(raw.get("priceUsd", 0)),
            pair_created_at=int(raw.get("pairCreatedAt", 0)),
            liquidity=float(raw.get("liquidity", 0).get("base", 0)),
            volume=float(raw.get("volume", 0).get("h24", 0)),
            buys=int(raw.get("txns", 0).get("h1", 0).get("buys", 0)),
            image_url=raw.get("info", {}).get("imageUrl", ""),
            open_graph=raw.get("url", ""),
            timestamp=int(time.time())
        )
    
    
