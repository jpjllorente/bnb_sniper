import os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from controllers.web3_controller import Web3Controller
from utils.load_abi import load_erc20_abi, load_pancake_router_abi
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

BSC_RPC_URL = os.getenv("BSC_RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
WBNB_ADDRESS = os.getenv("WBNB_ADDRESS")

class Web3Service:
    def __init__(self, 
                rpc_url: str = BSC_RPC_URL,
                private_key: str = PRIVATE_KEY,
                wallet_address: str = WALLET_ADDRESS,
                wbnb_address: str = WBNB_ADDRESS,
                web3_controller: Web3Controller | None = None,
                dry_run: bool = True):
                
        
        self.rpc_url = rpc_url
        self.private_key = private_key
        self.wallet_address = wallet_address
        self.wbnb_address = wbnb_address
        self.erc20_abi = load_erc20_abi()
        self.router_abi = load_pancake_router_abi()
        self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.web3_controller = web3_controller or Web3Controller()
        self.dry_run = dry_run

        if not self.web3.is_connected():
            logger.error("No se pudo conectar a la BNB Chain")
            raise ConnectionError("Error al conectar con BNB Chain")

        logger.debug("Conectado correctamente a la BNB Chain")

        self.wallet_address = self.to_checksum_address(self.wallet_address)
        self.router_address = self.to_checksum_address(self.router_address)
        self.wbnb_address = self.to_checksum_address(self.wbnb_address)    

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
    def get_in_wei(self, amount: float) -> int:
        return self.web3.to_wei(amount, 'ether')

    @log_function
    def estimate_gas(self, tx: dict):
        return self.web3.eth.estimate_gas(tx)

    @log_function
    def get_gas_price(self):
        return self.web3.eth.gas_price

    """
    Ejecuta la compra del token con la lógica completa de evaluación.
    :param address_token: Dirección del token a comprar.
    """
    @log_function
    def build_contract(self, token_address: str | None = None):
        if token_address:
            abi = self.router_abi()
            address = self.router_address
        else:
            abi = self.erc20_abi()
            address = self.to_checksum_address(token_address)
        return self.web3.eth.contract(address, abi=abi)

    @log_function
    def get_amount_out_min(self, amount_bnb, contract, token_address) -> int | None:
        amount_wei = self.web3.to_wei(amount_bnb, 'ether')
        amounts = contract.functions.getAmountsOut(amount_wei,
            [self.to_checksum_address(token_address), self.wbnb_address]).call()
        amount_out_min = int(amounts[1] * (1 - self.slippage / 100))
        if amount_out_min <= 0:
            logger.warning("Amount out min es 0 o negativo, no se puede continuar")
            return
        return amount_out_min

    @log_function
    def get_token_decimals(self, contract) -> int:
        return contract.functions.decimals().call()
    
    @log_function
    def get_last_block_timestamp(self) -> int:
        return self.web3.eth.get_block('latest')['timestamp']
    
    @log_function
    def create_transaction(self, contract, token_address, amount_out_min, amount_bnb):
        tx = self.web3_controller.create_transaction(contract, token_address, amount_out_min, amount_bnb)
        return tx

    @log_function
    def sign_and_send(self, tx: dict):
        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return self.web3.to_hex(tx_hash)
