"""
Controller for handling manual or scheduled buy requests.

Exposes a simple interface for other parts of the application to trigger
purchases of tokens through the ``AutobuyService``.
"""

from __future__ import annotations

from bsc_sniper.models.token import Token
from bsc_sniper.services.autobuy_service import AutobuyService
from bsc_sniper.utils.logger import log_function


class BuyController:
    """Handle buy operations for tokens."""

    def __init__(self, autobuy_service: AutobuyService | None = None) -> None:
        self.autobuy_service = autobuy_service or AutobuyService()

    @log_function
    def buy(self, token: Token) -> bool:
        """Execute a buy for the given token."""
        return self.autobuy_service.buy_token(token)
