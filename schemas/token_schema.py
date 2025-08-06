"""
Data schema definitions for tokens.

These simple dataclasses can be used for validating incoming data or
serialising token information in API responses. In a real application you
might choose to use Pydantic models instead.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenCreate:
    """Schema for creating a new token entry."""

    address: str
    name: str


@dataclass
class TokenResponse(TokenCreate):
    """Schema for returning token information."""

    risk: float = 0.0
