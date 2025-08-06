"""
Represents the lifecycle of a trade session for a given token.

This class can be expanded to hold state about open positions, buy and sell
transactions, profit/loss, and any other metrics relevant to the trading
strategy.
"""

from __future__ import annotations

from typing import Optional

from models.token import Token


class TradeSession:
    """Encapsulate trading state for a single token."""

    def __init__(self, token: Token) -> None:
        self.token = token
        self.position: Optional[Any] = None  # type: ignore[name-defined]
        self.pnl: float = 0.0

    def update_pnl(self, pnl: float) -> None:
        """Update the profit and loss for the session."""
        self.pnl = pnl

    def __repr__(self) -> str:
        return f"TradeSession(token={self.token}, pnl={self.pnl})"
