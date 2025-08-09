# services/goplus_service.py
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
        token_repository: TokenRepository | None = None
    ) -> None:
        self.goplus_token = goplus_token or GoplusToken()
        self.token_repository = token_repository or TokenRepository()

    @log_function
    def get_token_data(self, token: Token) -> dict:
        """Devuelve el dict de seguridad de GoPlus para el token."""
        try:
            data = self.goplus_token.token_security(chain_id=56, addresses=[token.address])
            # Estructura típica: {"result": { "<addr_lower>": {...} } }
            return data.json().get("result", {}).get(token.address.lower(), {}) or {}
        except Exception as e:
            logger.error(f"GoPlus error get_token_data({token.symbol}): {e}")
            return {}

    @log_function
    def _is_honeypot(self, token: Token) -> bool:
        """
        True  => si la API devuelve exactamente "1"
        False => "0", None, "unknown", o errores
        """
        try:
            data = self.get_token_data(token)
            flag = data.get("is_honeypot")
            return str(flag) == "1"
        except Exception as e:
            logger.error(f"GoPlus error _is_honeypot({token.symbol}): {e}")
            return False

    @log_function
    def _save_token_taxes(self, token: Token) -> None:
        data = self.get_token_data(token)
        try:
            token.buy_tax = float(data.get("buy_tax", 0.0) or 0.0)
            token.sell_tax = float(data.get("sell_tax", 0.0) or 0.0)
            token.transfer_tax = float(data.get("transfer_tax", 0.0) or 0.0)
            self.token_repository.update_taxes(token)
        except Exception as e:
            logger.error(f"Error updating taxes for {token.symbol}: {e}")

    @log_function
    def update_token_and_get_honeypot(self, token: Token) -> bool:
        self._save_token_taxes(token)
        return self._is_honeypot(token)
