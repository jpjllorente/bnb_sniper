"""
In‑memory token repository for bsc_sniper.

In the initial skeleton this repository simply holds tokens in memory. In a
real implementation it would persist data to a database or file, such as
SQLite, PostgreSQL or JSON files, depending on the configuration.
"""

from __future__ import annotations

from typing import List

from models.token import Token


class TokenRepository:
    """A very simple token repository."""

    def __init__(self) -> None:
        self._tokens: List[Token] = []

    def get_all(self) -> List[Token]:
        """Return all stored tokens."""
        return list(self._tokens)

    def save(self, token: Token) -> None:
        """Save a new token."""
        self._tokens.append(token)
