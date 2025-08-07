"""
Controller for handling manual or scheduled buy requests.

Exposes a simple interface for other parts of the application to trigger
purchases of tokens through the ``AutobuyService``.
"""

from __future__ import annotations

from models.token import Token
from services.goplus_service import GoplusService
from services.telegram_service import TelegramService
from services.autobuy_service import AutobuyService
from repositories.token_repository import TokenRepository
from utils.log_config import logger_manager, log_function

from enums.token_status import TokenStatus

logger = logger_manager.setup_logger(__name__)

FEE_THRESHOLD_PERCENT = 10


class AutobuyController:
    """Handle buy operations for tokens."""

    def __init__(
        self,
        dry_run: bool = True,
        goplus_service: GoplusService | None = None,
        telegram_service: TelegramService | None = None,
        autobuy_service: AutobuyService | None = None
    ) -> None:
        self.dry_run = dry_run
        self.honeypot_service = goplus_service or GoplusService()
        self.telegram_service = telegram_service or TelegramService()
        self.autobuy_service = autobuy_service or AutobuyService(dry_run=dry_run)
        
    @log_function
    def procesar_token(self, token: Token) -> None:
        logger.info(f"🧪 Analizando {token.symbol} para posible compra...")

        if not self._evaluar_token(token):
            logger.info(f"❌ {token.symbol} no cumple criterios de compra. Se descarta.")
            return

        self.autobuy_service.execute_buy(token)

    def _evaluar_token(self, token: Token) -> bool:
        status: TokenStatus = TokenStatus.DISCOVERED
        """Evaluate if the token meets criteria for purchase."""
        if self.honeypot_service.update_token_and_get_honeypot(token):
            status = TokenStatus.HONEYPOT
            TokenRepository.update_status(token, status)
            logger.warning(f"❌ {token.symbol} identificado como honeypot. Se descarta.")
            return False
        if token.liquidity < 2000 and token.volume < 1000 and token.buys < 2:
            status = TokenStatus.EXCLUDED
            TokenRepository.update_status(token, status)
            return False
        status = TokenStatus.CANDIDATE
        TokenRepository.update_status(token, status)
        return True