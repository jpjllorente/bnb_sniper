"""
Controller for handling sell requests.

Exposes an interface for other parts of the application to initiate sales
through the ``AutosellService``.
"""

from __future__ import annotations

from models.token import Token
from models.trade_session import TradeSession
from services.telegram_service import TelegramService
from services.autosell_service import AutosellService
from utils.logger import log_function, setup_logger

logger = setup_logger(__name__)

class AutosellController:
    """Handle sell operations for tokens."""

    def __init__(
        self,
        dry_run: bool = True,
        telegram_service: TelegramService | None = None,
        autosell_service: AutosellService | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.telegram_service = telegram_service or TelegramService()
        self.autosell_service = autosell_service or AutosellService(dry_run=dry_run)

    @log_function
    def procesar_venta(self, token: Token, session: TradeSession) -> None:
        logger.info(f"📉 Evaluando venta de {token.symbol}...")

        pnl = self._calcular_pnl(session.entry_price, token.price_native)
        logger.info(f"🔍 PnL estimado: {pnl:.2f}%")

        if pnl < session.min_acceptable_pnl:
            confirmed = self.telegram_service.confirm_low_pnl(token, pnl)
            if not confirmed:
                logger.info("❌ Venta cancelada por el usuario.")
                return

        self.autosell_service.execute_sell(token)

    def _calcular_pnl(self, entry: float, current: float) -> float:
        return ((current - entry) / entry) * 100
