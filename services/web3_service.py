import os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)


class Web3Service:
    def __init__(self):
        self.rpc_url = os.getenv("BSC_RPC_URL")
        self.private_key = os.getenv("PRIVATE_KEY")
        self.wallet_address = os.getenv("WALLET_ADDRESS")
        self.router_address = os.getenv("PANCAKE_ROUTER")

        if not all([self.rpc_url, self.private_key, self.wallet_address, self.router_address]):
            logger.error("Faltan variables de entorno necesarias")
            raise EnvironmentError("Variables de entorno incompletas")

        self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self.web3.is_connected():
            logger.error("No se pudo conectar a la BNB Chain")
            raise ConnectionError("Error al conectar con BNB Chain")

        logger.debug("Conectado correctamente a la BNB Chain")

        self.wallet_address = self.to_checksum_address(self.wallet_address)
        self.router_address = self.to_checksum_address(self.router_address)

    def to_checksum_address(self, address: str) -> str:
        return self.web3.to_checksum_address(address)

    @log_function
    def get_wallet_address(self):
        return self.wallet_address

    @log_function
    def get_router_address(self):
        return self.router_address

    @log_function
    def get_nonce(self):
        return self.web3.eth.get_transaction_count(self.wallet_address)

    @log_function
    def get_balance(self):
        balance_wei = self.web3.eth.get_balance(self.wallet_address)
        return self.web3.from_wei(balance_wei, 'ether')

    @log_function
    def estimate_gas(self, tx: dict):
        return self.web3.eth.estimate_gas(tx)

    @log_function
    def get_gas_price(self):
        return self.web3.eth.gas_price

    @log_function
    def build_contract(self, address: str, abi: dict):
        checksum_address = self.to_checksum_address(address)
        return self.web3.eth.contract(address=checksum_address, abi=abi)

    @log_function
    def get_token_decimals(self, contract) -> int:
        return contract.functions.decimals().call()

    @log_function
    def sign_and_send(self, tx: dict):
        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return self.web3.to_hex(tx_hash)
