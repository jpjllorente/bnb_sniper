"""
Service for detecting honeypot tokens.

The honeypot check determines whether a token's smart contract prevents
sellers from selling or imposes excessive fees. Here we simply return
False for all tokens as a stub.
"""

from __future__ import annotations

import requests

from models.token import Token
from utils.logger import log_function, setup_logger

logger = setup_logger(__name__)

class HoneypotService:
    GOPLUS_URL = "https://api.gopluslabs.io/api/v1/token_security/56"

    @log_function
    def is_honeypot(self, token: Token) -> bool:
        try:
            url = f"{self.GOPLUS_URL}?contract_addresses={token.pair_address}"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"GoPlus API error: {response.status_code}")
                return False

            data = response.json().get("result", {}).get(token.pair_address.lower(), {})
            honeypot_result = data.get("is_honeypot", "0")  # 1 = honeypot
            return honeypot_result == "1"

        except Exception as e:
            logger.error(f"Error al consultar GoPlus: {e}")
            return False