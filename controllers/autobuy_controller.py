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
from services.web3_service import Web3Service
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
        web3_service: Web3Service | None = None,
        autobuy_service: AutobuyService | None = None
    ) -> None:
        self.dry_run = dry_run
        self.honeypot_service = goplus_service or GoplusService()
        self.telegram_service = telegram_service or TelegramService()
        self.web3_service = web3_service or Web3Service()
        self.autobuy_service = autobuy_service or AutobuyService(dry_run=dry_run)
        
    @log_function
    def procesar_token(self, token: Token) -> None:
        logger.info(f"🧪 Analizando {token.symbol} para posible compra...")

        if not self._evaluar_token(token):
            logger.info(f"❌ {token.symbol} no cumple criterios de compra. Se descarta.")
            return
        if not self._validar_rentabilidad(token.price_native, token, "compra", FEE_THRESHOLD_PERCENT):
            logger.info(f"❌ {token.symbol} Esperando confirmación del usuario.")
            return
        if self.autobuy_service.execute_buy(token):
            logger.info(f"✅ Compra exitosa de {token.symbol}!")
            TokenRepository.update_status(token, TokenStatus.FOLLOWING)
        
    @log_function
    def _calcular_coste_unitario(self, token: Token, amount_bnb: float) -> float:
        contrato = self.web3_service.build_contract()
        unidades = self.web3_service.get_amount_out_min(amount_bnb=amount_bnb,contract=contrato, token_address=token.address) / (10 ** self.web3_service.get_token_decimals())
        if unidades == 0:
            raise ValueError("No se puede dividir entre 0 unidades compradas")

        coste_total = (
            token.price_native +
            self.web3_service.estimate_gas / unidades +
            (token.buy_tax + token.transfer_tax) / unidades
        )
        logger.info(f"Coste total por token (BNB): {coste_total:.10f}")
        return coste_total

    @log_function
    def _calcular_pnl_porcentual(self, precio_actual: float) -> float:
        if precio_actual == 0:
            logger.error("Precio actual es 0, no se puede calcular PnL")
            return -100.0
        pnl = ((self._calcular_coste_unitario - precio_actual) / precio_actual) * 100
        logger.info(f"PnL estimado: {pnl:.2f}%")
        return pnl

    @log_function
    def _validar_rentabilidad(
        self,
        precio_actual: float,
        token_obj,
        contexto: str,
        umbral_pnl_negativo: float
    ) -> bool:
        """
        Retorna True si la rentabilidad es aceptable.
        Si el PnL es demasiado negativo (porcentaje), pausa y notifica al usuario.
        """
        pnl = self._calcular_pnl_porcentual(precio_actual)

        if pnl < -abs(umbral_pnl_negativo):
            logger.warning(f"❌ Rentabilidad insuficiente (PnL={pnl:.2f}%). Acción pausada.")
            self.telegram_service.solicitar_accion("compra", token_obj, contexto)
            return False

        return True
    
    @log_function
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