"""
State repository for tracking per‑token status in bsc_sniper.

This repository stores the state of each token as a simple in‑memory map.
Production implementations could persist to a database or other durable
storage.
"""

from __future__ import annotations

from typing import Dict

from bsc_sniper.models.token import Token
from bsc_sniper.enums.token_status import TokenStatus


class StateRepository:
    """Repository for storing the processing state of tokens."""

    def __init__(self) -> None:
        self._state: Dict[str, TokenStatus] = {}

    def get_state(self, token: Token) -> TokenStatus | None:
        """Return the current status of a token, if any."""
        return self._state.get(token.address)

    def update_state(self, token: Token, status: TokenStatus) -> None:
        """Update the state of a token."""
        self._state[token.address] = status
