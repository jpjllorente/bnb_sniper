"""
Service for detecting honeypot tokens.

The honeypot check determines whether a token's smart contract prevents
sellers from selling or imposes excessive fees. Here we simply return
False for all tokens as a stub.
"""

from __future__ import annotations

from goplus.token import Token as GoplusToken

from models.token import Token
from repositories.token_repository import TokenRepository
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

class GoplusService:
    
    def __init__(
        self,
        goplus_token: GoplusToken | None = None,
        token: Token | None = None,
        token_repository: TokenRepository | None = None
    ) -> None:
        self.goplus_token = goplus_token or GoplusToken()
        self.token = token or Token()
        self.token_repository = token_repository or TokenRepository()

    @log_function
    def get_token_data(self, token: Token) -> dict:
        """Fetch token data from GoPlus API.""" 
        try:
            data = self.goplus_token.token_security(
                chain_id=56, addresses=[token.address]
            )
            return data.json().get("result", {}).get(token.address.lower(), {})
        except Exception as e:
            logger.error(f"Error fetching token data: {e}")
            return {}
    
    @log_function
    def _is_honeypot(self, token_address: str) -> bool:
        try:
            data = self.get_token_data(token_address)
            
            if data.get("is_honeypot", "0") == "1":
                return True
            return False
        except Exception as e:
            logger.error(f"Error al consultar GoPlus: {e}")
            
    def _save_token_taxes(self, token: Token) -> None:
        data = self.get_token_data(token)
        token.buy_tax = float(data.get("buy_tax", 0.0))
        token.sell_tax = float(data.get("sell_tax", 0.0))
        token.transfer_tax = float(data.get("transfer_tax", 0.0))
        
        self.token_repository.update_taxes(token)
        logger.info(f"Taxes for {token.symbol} updated successfully.")  
        
    def update_token_and_get_honeypot(self, token: Token) -> bool:
        """Update token data and check if it's a honeypot."""
        self._save_token_taxes(token)
        return self._is_honeypot(token.address)