"""
Service responsible for discovering new trading opportunities.

In this skeleton implementation the discovery simply returns an empty list.
Extend this service to query Dexscreener or other APIs to discover new
token pairs with BNB liquidity.
"""

from __future__ import annotations

import requests

from models.token import Token
from utils.log_config import log_function


class DiscoveryService:
    """Find new token pairs that might be interesting to trade."""
    DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/search?q=*/BNB"

    @log_function
    def discover_new_tokens(self) -> list[Token]:
        response = requests.get(self.DEXSCREENER_URL, timeout=10)
        response.raise_for_status()

        data = response.json().get("pairs", [])
        tokens = [Token.from_dexscreener(pair) for pair in data if pair.get("chainId") == "bsc"]
        return tokens