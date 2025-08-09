"""
Represents the lifecycle of a trade session for a given token.

This class can be expanded to hold state about open positions, buy and sell
transactions, profit/loss, and any other metrics relevant to the trading
strategy.
"""

from __future__ import annotations

from pydantic import BaseModel

class TradeSession(BaseModel):
    pair_address: str
    symbol: str
    price_native: float
    entry_price: float
    buy_price_with_fees: float
    pnl: float
    updated_at: int = 0
    
    