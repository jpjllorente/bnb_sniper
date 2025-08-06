"""
Controller for handling sell requests.

Exposes an interface for other parts of the application to initiate sales
through the ``AutosellService``.
"""

from __future__ import annotations

from bsc_sniper.models.token import Token
from bsc_sniper.services.autosell_service import AutosellService
from bsc_sniper.utils.logger import log_function


class SellController:
    """Handle sell operations for tokens."""

    def __init__(self, autosell_service: AutosellService | None = None) -> None:
        self.autosell_service = autosell_service or AutosellService()

    @log_function
    def sell(self, token: Token, pnl: float) -> bool:
        """Execute a sell for the given token and profit/loss."""
        return self.autosell_service.sell_token(token, pnl)
