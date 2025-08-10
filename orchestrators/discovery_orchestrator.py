# orchestrators/discovery_orchestrator.py
from __future__ import annotations
import os, time, threading
from typing import Optional

from services.discovery_service import DiscoveryService
from services.goplus_service import GoPlusService
from services.telegram_service import TelegramService
from repositories.token_repository import TokenRepository
from repositories.action_repository import ActionRepository
from utils.log_config import logger_manager, log_function
from models.token import Token

logger = logger_manager.setup_logger(__name__)

# Parámetros por entorno (todo en BNB)
DISCOVERY_INTERVAL_SEC = float(os.getenv("DISCOVERY_INTERVAL_SEC", "10"))
DISCOVERY_QUERY = os.getenv("DISCOVERY_QUERY", "*/BNB")

# Filtros mínimos (ajústalos a tu gusto)
MIN_LIQUIDITY_BNB = float(os.getenv("MIN_LIQUIDITY_BNB", "1.0"))     # liquidez mínima
MAX_BUY_TAX_PCT   = float(os.getenv("MAX_BUY_TAX_PCT", "10.0"))      # %
MAX_SELL_TAX_PCT  = float(os.getenv("MAX_SELL_TAX_PCT", "10.0"))     # %
MAX_TRANSFER_TAX  = float(os.getenv("MAX_TRANSFER_TAX", "10.0"))     # %
MIN_AGE_MIN       = int(os.getenv("MIN_AGE_MIN", "5"))               # minutos mínimos desde creación del par

class DiscoveryOrchestrator:
    """
    Bucle de descubrimiento:
      - Busca pares nuevos en Dexscreener (*/BNB).
      - Enriquecido con GoPlus (taxes, honeypot).
      - Guarda en TokenRepository.
      - Crea acción de compra:
          * Si dentro de parámetros → autoriza (para compra automática)
          * Si fuera de parámetros → deja pendiente y notifica por Telegram.
    """
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.token_repo = TokenRepository(db_path=db_path)
        self.action_repo = ActionRepository(db_path=db_path)
        self.discovery = DiscoveryService()
        self.goplus = GoPlusService()
        self.tg = TelegramService()

        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run_loop, name="Discovery", daemon=True)
        self._thread.start()
        logger.info("DiscoveryOrchestrator iniciado.")

    def stop(self) -> None:
        self._stop_evt.set()
        logger.info("DiscoveryOrchestrator detenido (orden enviada).")

    @log_function
    def _run_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._discover_once()
            except Exception as e:
                logger.exception(f"Error en discovery: {e}")
            # latido
            logger.debug("[discovery] tick completado.")
            self._stop_evt.wait(DISCOVERY_INTERVAL_SEC)

    # --------- core ----------
    def _discover_once(self) -> None:
        # 1) pedir a dexscreener
        pairs = self.discovery.search_pairs(DISCOVERY_QUERY)  # usa tu método real
        if not pairs:
            logger.debug("[discovery] 0 pares devueltos.")
            return

        for p in pairs:
            try:
                token = self._map_to_token(p)
                if not token or not token.pair_address or not token.address:
                    continue

                if self.token_repo.exists(token.pair_address):
                    continue  # ya visto

                # 2) enriquecer con goplus (taxes, honeypot)
                taxes = self.goplus.get_taxes(token.address)  # {'buy':..,'sell':..,'transfer':..}
                token.buy_tax = float(taxes.get("buy", 0.0))
                token.sell_tax = float(taxes.get("sell", 0.0))
                token.transfer_tax = float(taxes.get("transfer", 0.0))

                is_honey = self._is_honeypot(token)  # True si honeypot
                # 3) persistir token
                self.token_repo.save(token)
                self.token_repo.update_taxes(token)

                # 4) decidir acción
                dentro = self._within_parameters(token, is_honey)
                if dentro:
                    # autorizar compra directa: creamos acción y la aprobamos
                    self.action_repo.registrar_accion(token.pair_address, "compra")
                    self.action_repo.autorizar_accion(token.pair_address)
                    logger.info(f"[discovery] {token.symbol} autorizado (parámetros OK) → orquestador comprará.")
                else:
                    # requerir confirmación por Telegram
                    contexto = self._context_for_telegram(token, is_honey)
                    self.tg.solicitar_accion("compra", token, contexto)
                    logger.info(f"[discovery] {token.symbol} pendiente (requiere confirmación Telegram).")

            except Exception as e:
                logger.exception(f"[discovery] error procesando par: {e}")

    # --------- helpers ----------
    def _map_to_token(self, p: dict) -> Optional[Token]:
        """
        Adapta la respuesta de dexscreener a tu modelo Token.
        Asegúrate de tomar price_native unitario BNB/token.
        """
        try:
            return Token(
                pair_address=p["pair_address"],
                address=p["token_address"],
                symbol=p.get("symbol") or "-",
                name=p.get("name") or "-",
                price_native=float(p.get("price_native") or 0.0),
                price_usd=None,
                pair_created_at=int(p.get("pair_created_at") or 0),
                image_url=p.get("image_url"),
                open_graph=p.get("open_graph"),
                buy_tax=0.0, sell_tax=0.0, transfer_tax=0.0
            )
        except Exception:
            return None

    def _is_honeypot(self, token: Token) -> bool:
        """
        Debe devolver True si es honeypot. Basado en tu aclaración:
        '1' → True; '0' o 'unknown' → False
        """
        res = self.goplus.is_honeypot(token)
        return True if res == "1" else False

    def _within_parameters(self, token: Token, is_honeypot: bool) -> bool:
        if is_honeypot:
            return False
        # edad del par (minutos)
        if token.pair_created_at:
            import time as _t
            age_min = max(0, (int(_t.time()) - int(token.pair_created_at)) // 60)
            if age_min < MIN_AGE_MIN:
                return False
        # liquidez (si tu DiscoveryService trae BNB de liquidez en el payload, úsalo aquí)
        liq = getattr(token, "liquidity", None)
        if liq is not None and liq < MIN_LIQUIDITY_BNB:
            return False
        # taxes
        if (token.buy_tax or 0) > MAX_BUY_TAX_PCT:
            return False
        if (token.sell_tax or 0) > MAX_SELL_TAX_PCT:
            return False
        if (token.transfer_tax or 0) > MAX_TRANSFER_TAX:
            return False
        return True

    def _context_for_telegram(self, token: Token, is_honeypot: bool) -> str:
        reasons = []
        if is_honeypot:
            reasons.append("Posible honeypot")
        if token.pair_created_at:
            import time as _t
            age_min = max(0, (int(_t.time()) - int(token.pair_created_at)) // 60)
            if age_min < MIN_AGE_MIN:
                reasons.append(f"Edad {age_min}m < {MIN_AGE_MIN}m")
        liq = getattr(token, "liquidity", None)
        if liq is not None and liq < MIN_LIQUIDITY_BNB:
            reasons.append(f"Liquidez {liq} < {MIN_LIQUIDITY_BNB} BNB")
        if (token.buy_tax or 0) > MAX_BUY_TAX_PCT:
            reasons.append(f"buy_tax {token.buy_tax}% > {MAX_BUY_TAX_PCT}%")
        if (token.sell_tax or 0) > MAX_SELL_TAX_PCT:
            reasons.append(f"sell_tax {token.sell_tax}% > {MAX_SELL_TAX_PCT}%")
        if (token.transfer_tax or 0) > MAX_TRANSFER_TAX:
            reasons.append(f"transfer_tax {token.transfer_tax}% > {MAX_TRANSFER_TAX}%")
        return "; ".join(reasons) or "Fuera de parámetros"
