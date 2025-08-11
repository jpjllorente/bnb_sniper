# controllers/discovery_controller.py
from __future__ import annotations
import os, time
from typing import List
from models.token import Token
from controllers.autobuy_controller import AutoBuyController
from services.discovery_service import DiscoveryService
from services.goplus_service import GoplusService
from services.telegram_service import TelegramService
from repositories.token_repository import TokenRepository
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

# Umbrales desde entorno
MIN_LIQUIDITY_BNB   = float(os.getenv("MIN_LIQUIDITY_BNB", "0"))
MIN_AGE_MIN         = int(os.getenv("MIN_AGE_MIN", "0"))
MAX_BUY_TAX_PCT     = float(os.getenv("MAX_BUY_TAX_PCT", "100"))
MAX_SELL_TAX_PCT    = float(os.getenv("MAX_SELL_TAX_PCT", "100"))
MAX_TRANSFER_TAX    = float(os.getenv("MAX_TRANSFER_TAX", "100"))

class DiscoveryController:
    """
    Orquesta el descubrimiento, aplica filtros y decide:
      - Si NO pasa filtros -> pedir autorización con botones
      - Si SÍ pasa filtros -> intenta compra; si 'PENDING_USER' -> pedir autorización;
                              si 'IMMEDIATE' -> avisar informativo
    """

    def __init__(
        self,
        discovery_service: DiscoveryService | None = None,
        autobuy_controller: AutoBuyController | None = None,
        token_repository: TokenRepository | None = None,
        telegram: TelegramService | None = None,
        goplus: GoplusService | None = None,
        db_path: str | None = None
    ) -> None:
        self.db_path = db_path or os.getenv("DB_PATH", "./data/memecoins.db")
        self.discovery_service = discovery_service or DiscoveryService()
        self.autobuy_controller = autobuy_controller or AutoBuyController(db_path=self.db_path)
        self.token_repository = token_repository or TokenRepository()
        self.telegram = telegram or TelegramService()
        self.goplus = goplus or GoplusService()

    @log_function
    def buscar_pares_con_bnb(self) -> List[Token]:
        candidatos = self.discovery_service.discover_new_tokens()
        nuevos = [t for t in candidatos if t and getattr(t, "pair_address", None)
                  and not self.token_repository.exists(t.pair_address)]
        logger.debug(f"[discovery_controller] nuevos={len(nuevos)}")
        return nuevos

    def _filter_reasons(self, token: Token) -> list[str]:
        reasons: list[str] = []
        # Honeypot + taxes desde GoPlus (y persiste tasas)
        try:
            is_honeypot = self.goplus.update_token_and_get_honeypot(token)
        except Exception as e:
            logger.error(f"[filters] GoPlus error: {e}")
            is_honeypot = False

        if is_honeypot:
            reasons.append("honeypot detectado")

        # taxes guardadas en repo (goplus_service ya las persistió)
        buy_tax, sell_tax, transfer_tax = self.token_repository.get_taxes(token.pair_address)
        if buy_tax > MAX_BUY_TAX_PCT: reasons.append(f"buy_tax {buy_tax:.2f}% > {MAX_BUY_TAX_PCT:.2f}%")
        if sell_tax > MAX_SELL_TAX_PCT: reasons.append(f"sell_tax {sell_tax:.2f}% > {MAX_SELL_TAX_PCT:.2f}%")
        if transfer_tax > MAX_TRANSFER_TAX: reasons.append(f"transfer_tax {transfer_tax:.2f}% > {MAX_TRANSFER_TAX:.2f}%")

        # liquidez mínima
        try:
            liq = float(getattr(token, "liquidity", 0.0) or 0.0)
            if liq < MIN_LIQUIDITY_BNB:
                reasons.append(f"liquidez {liq:.4f} BNB < {MIN_LIQUIDITY_BNB:.4f} BNB")
        except Exception:
            pass

        # antigüedad del par
        try:
            ts = float(getattr(token, "pair_created_at", 0) or 0)
            if ts > 1e12:  # si es timestamp en milisegundos
                ts = ts / 1000.0
            age_min = (time.time() - ts) / 60.0
            if age_min < MIN_AGE_MIN:
                reasons.append(f"antigüedad {age_min:.1f}min < {MIN_AGE_MIN}min")
        except Exception as e:
            logger.debug(f"Error calculando antigüedad para {token.symbol}: {e}")

        return reasons

    @log_function
    def procesar_tokens_descubiertos(self) -> None:
        nuevos = self.buscar_pares_con_bnb()
        for token in nuevos:
            try:
                self.token_repository.save(token)

                # 1) Filtros “duros”
                reasons = self._filter_reasons(token)
                if reasons:
                    self.telegram.solicitar_autorizacion(token, tipo="compra", contexto="\n".join(reasons))
                    logger.debug(f"[discovery_controller] requiere autorización por filtros: {token.symbol}")
                    continue

                # 2) Pasa filtros → invocar flujo de compra
                result = self.autobuy_controller.procesar_token(token)  # usa cap de gasto de prueba
                if not result or not result.get("ok"):
                    logger.debug(f"[discovery_controller] sin resultado compra: {token.symbol}")
                    continue

                mode = result.get("mode")
                if mode == "PENDING_USER":
                    # Motivo origen: 'PNL_BELOW_THRESHOLD' o 'FEE_HIGH'
                    reason = result.get("reason") or "Condiciones fuera de umbral"
                    self.telegram.solicitar_autorizacion(token, tipo="compra", contexto=reason)
                elif mode == "IMMEDIATE":
                    self.telegram.notificar_autorizado_info(token)

                logger.debug(f"[discovery_controller] procesado {token.symbol} ({token.pair_address})")
            except Exception as e:
                logger.error(f"[discovery_controller] error con {getattr(token,'pair_address',None)}: {e}")
