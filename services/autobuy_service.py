"""
Service for executing automatic buys of tokens.

This service coordinates honeypot checks, fee estimation and user
confirmation before performing a buy. Currently the implementation is a
placeholder and does not interact with smart contracts.
"""

from __future__ import annotations

from models.token import Token
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

FEE_THRESHOLD_PERCENT = 10  # porcentaje máximo de fee aceptable

class AutobuyService:
    """Manage the logic for buying tokens automatically."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    @log_function
    def execute_buy(self, token: Token) -> None:
        if self.dry_run:
            logger.info(f"[DRY-RUN] Simulación de compra de {token.symbol}.")
            return