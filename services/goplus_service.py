# services/goplus_service.py
from __future__ import annotations
import os
from goplus.token import Token as GoPlusToken
from utils.logger import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

class GoplusService:
    """
    Servicio para consultar datos de seguridad de tokens usando el SDK oficial de GoPlus.
    Guarda tasas en repositorio y devuelve si es honeypot o no.
    """

    def __init__(self, repo, access_token: str | None = None):
        self.repo = repo
        self.access_token = access_token or os.getenv("GOPLUS_ACCESS_TOKEN") or None
        self.client = GoPlusToken(access_token=self.access_token)

    @log_function
    def get_token_data(self, token) -> dict:
        """
        Llama a la API de GoPlus y devuelve el nodo de datos del token como dict.
        """
        try:
            resp = self.client.token_security(
                chain_id="56",  # BSC mainnet
                addresses=[token.address],
                **{"_request_timeout": 10}
            )
        except Exception as e:
            logger.error(f"GoPlus error get_token_data({token.symbol}): {e}")
            return {}

        try:
            if not hasattr(resp, "result") or not isinstance(resp.result, dict):
                logger.error(f"Respuesta inesperada de GoPlus para {token.symbol}: {resp}")
                return {}

            token_addr_lower = token.address.lower()
            if token_addr_lower in resp.result:
                return resp.result[token_addr_lower]

            for k, v in resp.result.items():
                if k.lower() == token_addr_lower:
                    return v

            logger.warning(f"No se encontró nodo de datos para {token.symbol} ({token.address})")
            return {}
        except Exception as e:
            logger.error(f"GoPlus parse error ({token.symbol}): {e}")
            return {}

    @log_function
    def update_token_and_get_honeypot(self, token) -> bool:
        """
        Obtiene datos de GoPlus, guarda tasas en repo y devuelve si es honeypot.
        """
        data = self.get_token_data(token)
        if not data:
            return False

        try:
            is_hp = bool(data.get("is_honeypot") or data.get("honeypot_result") or False)
            buy_tax = float(data.get("buy_tax", 0))
            sell_tax = float(data.get("sell_tax", 0))
            transfer_tax = float(data.get("transfer_tax", 0))

            self.repo.save_taxes(
                pair_address=token.pair_address,
                buy_tax=buy_tax,
                sell_tax=sell_tax,
                transfer_tax=transfer_tax,
                is_honeypot=is_hp
            )

            return is_hp
        except Exception as e:
            logger.error(f"GoPlus save_taxes error ({token.symbol}): {e}")
            return False
