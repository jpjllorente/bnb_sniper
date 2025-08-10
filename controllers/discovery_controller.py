# controllers/discovery_controller.py
from __future__ import annotations
from typing import List
from models.token import Token
from controllers.autobuy_controller import AutobuyController
from services.discovery_service import DiscoveryService
from repositories.token_repository import TokenRepository
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

class DiscoveryController:
    """
    Orquesta el descubrimiento y dispara el pipeline de compra.
    """
    def __init__(
        self,
        discovery_service: DiscoveryService | None = None,
        autobuy_controller: AutobuyController | None = None,
        token_repository: TokenRepository | None = None
    ) -> None:
        self.discovery_service = discovery_service or DiscoveryService()
        self.autobuy_controller = autobuy_controller or AutobuyController()
        self.token_repository = token_repository or TokenRepository()

    @log_function
    def buscar_pares_con_bnb(self) -> List[Token]:
        candidatos = self.discovery_service.discover_new_tokens()
        nuevos = [t for t in candidatos
                  if t and getattr(t, "pair_address", None)
                  and not self.token_repository.exists(t.pair_address)]
        logger.debug(f"[discovery_controller] nuevos={len(nuevos)}")
        return nuevos

    @log_function
    def procesar_tokens_descubiertos(self) -> None:
        nuevos = self.buscar_pares_con_bnb()
        for token in nuevos:
            try:
                self.token_repository.save(token)
                self.autobuy_controller.procesar_token(token)
                logger.debug(f"[discovery_controller] procesado {token.symbol} ({token.pair_address})")
            except Exception as e:
                logger.error(f"[discovery_controller] error con {getattr(token,'pair_address',None)}: {e}")
