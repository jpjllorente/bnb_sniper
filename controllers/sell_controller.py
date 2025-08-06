"""
Controller for handling sell requests.

Exposes an interface for other parts of the application to initiate sales
through the ``AutosellService``.
"""

from __future__ import annotations

from models.token import Token
from models.trade_session import TradeSession
from services.telegram_service import TelegramService
from utils.logger import log_function, setup_logger

logger = setup_logger(__name__)

class SellController:
    """Handle sell operations for tokens."""

    def __init__(self, dry_run: bool = True, telegram_service: TelegramService | None = None) -> None:
        self.dry_run = dry_run
        self.telegram_service = telegram_service or TelegramService()

    @log_function
    def sell_token(self, token: Token, session: TradeSession) -> None:
        logger.info(f"💰 Evaluando venta de {token.symbol}...")

        pnl = self._calculate_pnl(session.entry_price, token.price_native)
        logger.info(f"🔍 PnL estimado: {pnl:.2f}%")

        if pnl < session.min_acceptable_pnl:
            logger.warning("⚠️ PnL bajo. Confirmación requerida vía Telegram.")
            confirm = self.telegram_service.confirm_low_pnl(token, pnl)
            if not confirm:
                logger.info("❌ Venta cancelada por el usuario.")
                return

        if self.dry_run:
            logger.info(f"[DRY-RUN] Venta simulada de {token.symbol} completada.")
            return

        # Aquí iría la lógica real de venta vía Web3
        logger.info(f"✅ Token {token.symbol} vendido a {token.price_native} BNB")

    def _calculate_pnl(self, entry_price: float, current_price: float) -> float:
        # Simplificación: PnL en porcentaje
        return ((current_price - entry_price) / entry_price) * 100