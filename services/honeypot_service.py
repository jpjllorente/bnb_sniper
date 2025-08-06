"""
Service for detecting honeypot tokens.

The honeypot check determines whether a token's smart contract prevents
sellers from selling or imposes excessive fees. Here we simply return
False for all tokens as a stub.
"""

from __future__ import annotations

from utils.logger import log_function


class HoneypotService:
    """Detect whether a token is a honeypot."""

    @log_function
    def is_honeypot(self, token_address: str) -> bool:
        """Return True if the token is a honeypot, False otherwise."""
        # TODO: integrate with on‑chain analysis or external APIs
        return False
