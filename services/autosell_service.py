"""
Service for executing automatic sells of tokens.

This service evaluates profit and loss (PnL) and may ask the user for
confirmation before selling if the trade appears unfavourable. The actual
contract interactions are omitted in this skeleton implementation.
"""

from __future__ import annotations

from models.token import Token
from services.telegram_service import TelegramService
from utils.log_config import log_function, logger_manager

logger = logger_manager.setup_logger(__name__)

class AutosellService:
    """Manage the logic for selling tokens automatically."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    @log_function
    def execute_sell(self, token: Token) -> None:
        if self.dry_run:
            logger.info(f"[DRY-RUN] Simulación de venta de {token.symbol} completada.")
            return

        # Aquí va la lógica real de venta
        logger.info(f"✅ Token {token.symbol} vendido a {token.price_native} BNB")