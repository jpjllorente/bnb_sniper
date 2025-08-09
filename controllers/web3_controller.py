import os
from utils.log_config import logger_manager, log_function
from services.web3_service import Web3Service
from services.telegram_service import TelegramService
from web3.exceptions import ContractLogicError
from models.token import Token

logger = logger_manager.setup_logger(__name__)


class Web3Controller:
    def __init__(self):
        self.web3_service = Web3Service()
        self.telegram = TelegramService()
        self.slippage = float(os.getenv("DEFAULT_SLIPPAGE"))

    @log_function
    def get_amount_out_min(self, amount_bnb, contract, token_address) -> int | None:
        try:
            amounts = self.web3_service.get_amount_out_min(amount_bnb, contract, token_address)
            amount_out_min = int(amounts[1] * (1 - self.slippage / 100))
        except ContractLogicError as e:
            logger.error(f"Error en getAmountsOut: {e}")
            return None

        if amount_out_min <= 0:
            logger.warning("Amount out min es 0 o negativo, no se puede continuar")
            return
        return amount_out_min
        
    @log_function
    def _estimate_gas_cost(self, tx: dict) -> tuple[int, int, float] | tuple[None, None, None]:
        try:
            gas = self.web3_service.estimate_gas(tx)
            gas_price = self.web3_service.get_gas_price()
            cost_bnb = gas * gas_price / 1e18
            return gas, gas_price, cost_bnb
        except Exception as e:
            logger.error(f"Error estimando gas: {e}")
            return None, None, None

    @log_function
    def create_transaction(self, contract, token_address, amount_out_min, amount_bnb):
        tx = contract.swapExactETHForTokensSupportingFeeOnTransferTokens(
            amount_out_min,
            [self.web3_service.wbnb_address, self.web3_service.to_checksum_address(token_address)],
            self.web3_service.wallet_address,
            int(self.web3_service.get_last_block_timestamp) + 300
        ).build_transaction({
            "from": self.web3_service.wallet_address,
            "value": self.web3_service.get_in_wei(amount_bnb),
            "gas": 300000,  
            "nonce": self.web3_service.get_nonce(),
            "gasPrice": self.web3_service.get_gas_price()
        })
        return tx