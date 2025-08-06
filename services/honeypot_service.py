"""
Service for detecting honeypot tokens.

The honeypot check determines whether a token's smart contract prevents
sellers from selling or imposes excessive fees. Here we simply return
False for all tokens as a stub.
"""

from __future__ import annotations

from models.token import Token
from utils.logger import log_function

class HoneypotService:
    """Detect whether a token is a honeypot."""

    @log_function
    def is_honeypot(self, token: Token) -> bool:
        # TODO: implementar con GoPlus o lógica real
        if "scam" in token.name.lower() or "rug" in token.symbol.lower():
            return True
        return False
