# services/discovery_service.py
from __future__ import annotations
import requests
from models.token import Token
from utils.log_config import log_function

class DiscoveryService:
    # Usa comodín para capturar pares con BNB/WBNB como referencia
    DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/search?q=*/BNB"

    @log_function
    def discover_new_tokens(self) -> list[Token]:
        r = requests.get(self.DEXSCREENER_URL, timeout=10)
        r.raise_for_status()
        pairs = r.json().get("pairs", []) or []
        # Filtramos a BSC; si ya lo haces fuera, puedes quitar esta línea.
        return [Token.from_dexscreener(p) for p in pairs if p.get("chainId") == "bsc"]
