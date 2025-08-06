"""
Represents the lifecycle of a trade session for a given token.

This class can be expanded to hold state about open positions, buy and sell
transactions, profit/loss, and any other metrics relevant to the trading
strategy.
"""

from __future__ import annotations

from pydantic import BaseModel

class TradeSession(BaseModel):
    token_address: str
    entry_price: float
    min_acceptable_pnl: float = 2.0  # se puede parametrizar