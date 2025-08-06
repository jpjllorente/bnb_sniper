"""
Controller orchestrating the discovery of new tokens and the automatic buy
pipeline.

This controller coordinates discovery, filtering and the initial purchase
process. It demonstrates how controllers use services to perform their
tasks while remaining decoupled from implementation details.
"""

from __future__ import annotations

from bsc_sniper.models.token import Token
from bsc_sniper.services.autobuy_service import AutobuyService
from bsc_sniper.services.discovery_service import DiscoveryService
from bsc_sniper.utils.logger import setup_logger, log_function


logger = setup_logger(__name__)


class DiscoveryController:
    """Coordinate discovery and initial token processing."""

    def __init__(self, discovery_service: DiscoveryService | None = None, autobuy_service: AutobuyService | None = None) -> None:
        self.discovery_service = discovery_service or DiscoveryService()
        self.autobuy_service = autobuy_service or AutobuyService()

    @log_function
    def buscar_pares_con_bnb(self) -> list[dict[str, str]]:
        """Discover new token pairs with BNB liquidity."""
        return self.discovery_service.discover_new_tokens()

    @log_function
    def procesar_tokens_descubiertos(self) -> None:
        """Process each discovered token and attempt to buy."""
        candidates = self.buscar_pares_con_bnb()
        for t in candidates:
            token = Token(address=t.get("address", ""), name=t.get("name", ""))
            self.autobuy_service.buy_token(token)
