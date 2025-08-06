"""
Service for executing automatic sells of tokens.

This service evaluates profit and loss (PnL) and may ask the user for
confirmation before selling if the trade appears unfavourable. The actual
contract interactions are omitted in this skeleton implementation.
"""

from __future__ import annotations

from bsc_sniper.models.token import Token
from bsc_sniper.services.telegram_service import TelegramService
from bsc_sniper.utils.logger import log_function


class AutosellService:
    """Manage the logic for selling tokens automatically."""

    def __init__(self, telegram_service: TelegramService | None = None) -> None:
        self.telegram_service = telegram_service or TelegramService()

    @log_function
    def sell_token(self, token: Token, pnl: float) -> bool:
        """Attempt to sell a token based on current PnL.

        :param token: The token to sell.
        :param pnl: The profit or loss for the current position.
        :returns: True if the sell was executed, False otherwise.
        """
        # Confirm with the user if PnL is negative or suspiciously high
        if pnl < 0 or pnl > 10.0:  # placeholder thresholds
            confirmed = self.telegram_service.confirm_action(
                f"PNL ({pnl}) for {token.name} is outside the safe range. Proceed with sell?"
            )
            if not confirmed:
                return False
        # Execute sell (stub)
        # TODO: interact with smart contracts to perform the sale
        return True
