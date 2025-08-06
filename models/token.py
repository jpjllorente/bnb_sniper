"""
Domain model representing a cryptocurrency token.

This class encapsulates basic attributes such as contract address, name and
risk score. Additional attributes can be added as needed (e.g. decimals,
symbol, liquidity, etc.).
"""

from __future__ import annotations


class Token:
    """A simple token representation."""

    def __init__(self, address: str, name: str, risk: float = 0.0) -> None:
        self.address = address
        self.name = name
        self.risk = risk

    def __repr__(self) -> str:
        return f"Token(address={self.address!r}, name={self.name!r}, risk={self.risk})"
