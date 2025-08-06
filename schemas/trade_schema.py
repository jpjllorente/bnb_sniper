"""
Data schema definitions for trades.

Dataclasses representing incoming trade requests and responses. They can be
used as request/response models in an API layer if needed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradeCreate:
    """Schema for creating a trade."""

    token_address: str
    amount: float


@dataclass
class TradeResponse(TradeCreate):
    """Schema for returning trade details."""

    pnl: float = 0.0
