"""
Represents the history  of a trade session for a given token.

"""

from __future__ import annotations

from pydantic import BaseModel

class History(BaseModel):
    pair_address: str
    token_address: str
    symbol: str
    name: str
    buy_entry_price: float
    buy_price_with_fees: float
    buy_real_price: float
    buy_amount: float
    buy_date: int
    sell_entry_price: float
    sell_price_with_fees: float
    sell_real_price: float
    sell_date: int
    sell_amount: float
    pnl: float = 0.0
    bnb_amount: float = 0.0
    
    