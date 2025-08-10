# services/discovery_service.py
from __future__ import annotations
import os
import requests
from typing import List, Optional

from models.token import Token
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

# Mapear CHAIN_ID → nombre de red que usa Dexscreener
_CHAIN_MAP = {
    "56": "bsc",
    "97": "bsc",   # Dexscreener no separa testnet; ajusta si cambias de red
}

class DiscoveryService:
    """
    Config por .env:
      - DEXSCREENER_BASE_URL (default: https://api.dexscreener.com/latest/dex)
      - DISCOVERY_QUERY (default: "*/BNB")
      - CHAIN_ID (default: "56") → filtra a 'bsc'
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        query: Optional[str] = None,
        chain_id: Optional[str] = None
    ) -> None:
        self.base_url = (base_url or os.getenv("DEXSCREENER_BASE_URL")
                         or "https://api.dexscreener.com/latest/dex").rstrip("/")
        # muy importante el "*": capta pares con BNB/WBNB como referencia (no solo que contengan "BNB" en el símbolo)
        self.query = (query or os.getenv("DISCOVERY_QUERY") or "*/BNB").strip()
        self.chain_name = _CHAIN_MAP.get(str(chain_id or os.getenv("CHAIN_ID", "56")), "bsc")

    @property
    def url(self) -> str:
        return f"{self.base_url}/search?q={self.query}"

    @log_function
    def discover_new_tokens(self) -> List[Token]:
        logger.debug(f"[discovery] GET {self.url} (chain={self.chain_name})")
        try:
            r = requests.get(self.url, timeout=12)
            r.raise_for_status()
            data = r.json() or {}
            pairs = data.get("pairs", []) or []
            logger.debug(f"[discovery] devueltos={len(pairs)}")

            # Filtro por cadena (Dexscreener devuelve 'bsc' para BNB Chain)
            filtered = [p for p in pairs if p.get("chainId") == self.chain_name]
            if not filtered:
                logger.debug("[discovery] 0 pares tras filtro de cadena.")
                return []

            tokens: List[Token] = []
            for p in filtered:
                try:
                    # Debes tener Token.from_dexscreener(p)
                    t = Token.from_dexscreener(p)
                    # Aseguro price_native unitario BNB/token si tu factory no lo puso
                    if getattr(t, "price_native", None) is None and "priceNative" in p:
                        t.price_native = float(p["priceNative"])
                    tokens.append(t)
                except Exception as e:
                    logger.debug(f"[discovery] parse saltado: {e}")

            logger.debug(f"[discovery] sample: {[(getattr(t,'pair_address',None), getattr(t,'symbol',None)) for t in tokens[:2]]}")
            return tokens

        except Exception as e:
            logger.error(f"[discovery] error consultando Dexscreener: {e}")
            return []
