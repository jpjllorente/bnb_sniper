"""
Controller for handling manual or scheduled buy requests.

Exposes a simple interface for other parts of the application to trigger
purchases of tokens through the ``AutobuyService``.
"""

from __future__ import annotations

from models.token import Token
from services.honeypot_service import HoneypotService
from services.telegram_service import TelegramService
from services.autobuy_service import AutobuyService
from utils.logger import log_function, setup_logger

logger = setup_logger(__name__)

FEE_THRESHOLD_PERCENT = 10


class AutobuyController:
    """Handle buy operations for tokens."""

    def __init__(
        self,
        dry_run: bool = True,
        honeypot_service: HoneypotService | None = None,
        telegram_service: TelegramService | None = None,
        autobuy_service: AutobuyService | None = None
    ) -> None:
        self.dry_run = dry_run
        self.honeypot_service = honeypot_service or HoneypotService()
        self.telegram_service = telegram_service or TelegramService()
        self.autobuy_service = autobuy_service or AutobuyService(dry_run=dry_run)
        
    @log_function
    def procesar_token(self, token: Token) -> None:
        logger.info(f"🧪 Analizando {token.symbol} para posible compra...")

        if self.honeypot_service.is_honeypot(token):
            logger.warning(f"❌ {token.symbol} identificado como honeypot. Se descarta.")
            return

        estimated_fee_percent = self._estimar_fees(token)
        logger.info(f"🔍 Fees estimados: {estimated_fee_percent:.2f}%")

        if estimated_fee_percent > FEE_THRESHOLD_PERCENT:
            confirmed = self.telegram_service.confirm_high_fee(token, estimated_fee_percent)
            if not confirmed:
                logger.info("❌ Usuario canceló la compra.")
                return

        self.autobuy_service.execute_buy(token)

    def _estimar_fees(self, token: Token) -> float:
        return 12.5 if "rug" in token.name.lower() else 4.0