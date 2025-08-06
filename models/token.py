"""
Domain model representing a cryptocurrency token.

This class encapsulates basic attributes such as contract address, name and
risk score. Additional attributes can be added as needed (e.g. decimals,
symbol, liquidity, etc.).
"""

from __future__ import annotations

from pydantic import BaseModel


class Token(BaseModel):
    
    pair_address: str
    name: str
    symbol: str
    price_native: float
    price_usd: float
    pair_created_at: int
    image_url: str
    open_graph: str

    @classmethod
    def from_dexscreener(cls, raw: dict) -> "Token":
        base = raw.get("baseToken", {})
        return cls(
            pair_address=raw.get("pairAddress", ""),
            name=base.get("name", ""),
            symbol=base.get("symbol", ""),
            price_native=float(raw.get("priceNative", 0)),
            price_usd=float(raw.get("priceUsd", 0)),
            pair_created_at=int(raw.get("pairCreatedAt", 0)),
            image_url=raw.get("info", {}).get("imageUrl", ""),
            open_graph=raw.get("url", "")
        )
    
    
