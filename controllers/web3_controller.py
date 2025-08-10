import os
from utils.log_config import logger_manager, log_function
from services.web3_service import Web3Service
from web3.exceptions import ContractLogicError

logger = logger_manager.setup_logger(__name__)
DEFAULT_SLIPPAGE = float(os.getenv("DEFAULT_SLIPPAGE", "3.0"))

class Web3Controller:
    def __init__(self):
        self.web3_service = Web3Service()
        self.slippage = DEFAULT_SLIPPAGE

    @log_function
    def get_amount_out_min(self, amount_bnb_wei: int, token_address: str) -> int | None:
        try:
            path = [os.getenv("WBNB_ADDRESS"), token_address]
            return self.web3_service.get_amount_out_min(amount_bnb_wei, path, self.slippage)
        except ContractLogicError as e:
            logger.error(f"Error en getAmountsOut: {e}")
            return None

    @log_function
    def preview_swap(self, token_address: str, amount_bnb_wei: int) -> dict | None:
        aomin = self.get_amount_out_min(amount_bnb_wei, token_address)
        if not aomin or aomin <= 0:
            logger.warning("amountOutMin inválido; cancelando preview")
            return None
        return {
            "path": [os.getenv("WBNB_ADDRESS"), token_address],
            "amount_in_wei": int(amount_bnb_wei),
            "amount_out_min": int(aomin),
            "slippage_percent": float(self.slippage),
        }

    @log_function
    def build_swap_tx(self, token_address: str, amount_bnb_wei: int) -> dict | None:
        aomin = self.get_amount_out_min(amount_bnb_wei, token_address)
        if not aomin or aomin <= 0:
            return None
        return self.web3_service.build_swap_exact_eth_for_tokens(amount_bnb_wei, aomin, token_address)
