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
        dry_run: bool = True,
        telegram_service: TelegramService | None = None,
        honeypot_service: HoneypotService | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.telegram_service = telegram_service or TelegramService()
        self.honeypot_service = honeypot_service or HoneypotService()

    @log_function
    def buy_token(self, token: Token) -> None:
        logger.info(f"🛒 Intentando comprar token: {token.symbol} ({token.pair_address})")

        # Paso 1: validación honeypot
        if self.honeypot_service.is_honeypot(token):
            logger.warning(f"❌ Token {token.symbol} identificado como honeypot. Compra cancelada.")
            return

        # Paso 2: estimación de fees (simulada por ahora)
        estimated_fee_percent = self._estimate_fee(token)
        logger.info(f"🔍 Fees estimados: {estimated_fee_percent}%")

        # Paso 3: si fees son altos, pedir confirmación vía Telegram
        if estimated_fee_percent > FEE_THRESHOLD_PERCENT:
            confirmed = self.telegram_service.confirm_high_fee(token, estimated_fee_percent)
            if not confirmed:
                logger.info(f"❌ Compra cancelada por el usuario vía Telegram")
                return

        # Paso 4: dry-run
        if self.dry_run:
            logger.info(f"[DRY-RUN] Simulación de compra de {token.symbol} completada.")
            return

        # Paso 5: ejecución real (pendiente de integración con Web3)
        logger.info(f"✅ Compra ejecutada de {token.symbol} a {token.price_native} BNB")

    def _estimate_fee(self, token: Token) -> float:
        # Aquí irá la lógica real basada en Web3 en el futuro
        return 12.5 if "rug" in token.name.lower() else 4.0