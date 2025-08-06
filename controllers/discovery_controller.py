"""
Controller orchestrating the discovery of new tokens and the automatic buy
pipeline.

This controller coordinates discovery, filtering and the initial purchase
process. It demonstrates how controllers use services to perform their
tasks while remaining decoupled from implementation details.
"""

from __future__ import annotations

from models.token import Token
from controllers.autobuy_controller import AutobuyController
from services.discovery_service import DiscoveryService
from repositories.token_repository import TokenRepository
from utils.logger import setup_logger, log_function


logger = setup_logger(__name__)


class DiscoveryController:
    """Coordinate discovery and initial token processing."""
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
    def buscar_pares_con_bnb(self) -> list[Token]:
        all_candidates = self.discovery_service.discover_new_tokens()
        nuevos = [t for t in all_candidates if not self.token_repository.exists(t.pair_address)]
        return nuevos

    @log_function
    def procesar_tokens_descubiertos(self) -> None:
        nuevos = self.buscar_pares_con_bnb()
        for token in nuevos:
            self.token_repository.save(token)
            self.autobuy_controller.procesar_token(token)