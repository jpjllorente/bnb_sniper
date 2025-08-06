"""
Service for executing automatic buys of tokens.

This service coordinates honeypot checks, fee estimation and user
confirmation before performing a buy. Currently the implementation is a
placeholder and does not interact with smart contracts.
"""

from __future__ import annotations

from typing import Any

from models.token import Token
from services.telegram_service import TelegramService
from services.honeypot_service import HoneypotService
from utils.logger import log_function, setup_logger

logger = setup_logger(__name__)

FEE_THRESHOLD_PERCENT = 10  # porcentaje máximo de fee aceptable

class AutobuyService:
    """Manage the logic for buying tokens automatically."""

    def __init__(
        self,
        telegram_service: TelegramService | None = None,
        honeypot_service: HoneypotService | None = None
    ) -> None:
        self.telegram_service = telegram_service or TelegramService()
        self.honeypot_service = honeypot_service or HoneypotService()

    @log_function
    def buy_token(self, token: Token) -> None:
        logger.info(f"🛒 Intentando comprar token: {token.symbol} ({token.pair_address})")

        # Paso 1: Validar honeypot
        if self.honeypot_service.is_honeypot(token):
            logger.warning(f"❌ Token {token.symbol} detectado como honeypot. Compra cancelada.")
            return

        # Paso 2: Estimar fees
        estimated_fee_percent = self._estimate_fee(token)

        # Paso 3: Confirmar si fees altos
        if estimated_fee_percent > FEE_THRESHOLD_PERCENT:
            confirmed = self.telegram_service.confirm_high_fee(token, estimated_fee_percent)
            if not confirmed:
                logger.info("❌ Compra cancelada por el usuario.")
                return

        # Paso 4: Ejecutar compra (placeholder)
        logger.info(f"✅ Compra ejecutada (simulada) de {token.symbol} a {token.price_native} BNB")

        # Paso 5: Lanzar monitor (no implementado aún)
        logger.info(f"📈 Lanzando monitor para {token.symbol}...")

    def _estimate_fee(self, token: Token) -> float:
        return 12.5 if "rug" in token.name.lower() else 5.0