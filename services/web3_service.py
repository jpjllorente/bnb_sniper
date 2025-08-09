from __future__ import annotations
import os
from typing import Any, List
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxReceipt, HexBytes
from eth_account import Account
from utils.load_abi import load_erc20_abi, load_pancake_router_abi
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
PRIVATE_KEY = os.getenv("PRIVATE_KEY") or ""
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS") or ""
WBNB_ADDRESS = os.getenv("WBNB_ADDRESS", "0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
ROUTER_ADDRESS = os.getenv("ROUTER_ADDRESS", "0x10ED43C718714eb63d5aA57B78B54704E256024E")
DEFAULT_SLIPPAGE = float(os.getenv("DEFAULT_SLIPPAGE", "3.0"))  # %
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
GAS_PRICE_WEI = int(os.getenv("GAS_PRICE_WEI", "0"))

class Web3Service:
    def __init__(self, rpc_url: str | None = None) -> None:
        rpc = rpc_url or BSC_RPC_URL
        self._w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
        self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if not self._w3.is_connected():
            raise ConnectionError(f"No conectado al nodo: {rpc}")
        self._account = Account.from_key(PRIVATE_KEY) if PRIVATE_KEY else None
        self._router_addr = self._w3.to_checksum_address(ROUTER_ADDRESS)
        self._wbnb_addr = self._w3.to_checksum_address(WBNB_ADDRESS)
        self._router_abi = load_pancake_router_abi()
        self._erc20_abi = load_erc20_abi()
        logger.debug(f"Conectado a {rpc}; chain_id={self._w3.eth.chain_id}")

    # ---- helpers controlados (no exponer .eth/.contract fuera) ----
    def checksum(self, address: str) -> str:
        return self._w3.to_checksum_address(address)

    def load_router(self):
        return self._w3.eth.contract(address=self._router_addr, abi=self._router_abi)

    def load_erc20(self, address: str):
        return self._w3.eth.contract(address=self.checksum(address), abi=self._erc20_abi)

    @log_function
    def get_token_decimals(self, erc20_contract) -> int:
        return int(erc20_contract.functions.decimals().call())

    # ---- amounts / slippage ----
    @log_function
    def get_amounts_out(self, amount_in_wei: int, path: List[str]) -> list[int]:
        router = self.load_router()
        path_cs = [self.checksum(p) for p in path]
        amounts = router.functions.getAmountsOut(int(amount_in_wei), path_cs).call()
        return [int(x) for x in amounts]

    @log_function
    def get_amount_out_min(self, amount_in_wei: int, path: List[str], slippage_percent: float | None = None) -> int:
        slippage = DEFAULT_SLIPPAGE if slippage_percent is None else slippage_percent
        amounts = self.get_amounts_out(amount_in_wei, path)
        amt_out = amounts[-1]
        return int(amt_out * (1 - (slippage / 100.0)))

    # ---- tx build / gas / send ----
    def _legacy_gas_price(self) -> int | None:
        if GAS_PRICE_WEI > 0:
            return GAS_PRICE_WEI
        try:
            return int(self._w3.eth.gas_price)
        except Exception:
            return None

    @log_function
    def build_swap_exact_eth_for_tokens(
        self, amount_in_wei: int, amount_out_min: int, token_address: str, deadline_secs_from_now: int = 60
    ) -> dict[str, Any]:
        from time import time
        if not self._account:
            raise RuntimeError("No hay PRIVATE_KEY configurada para firmar.")
        router = self.load_router()
        path = [self._wbnb_addr, self.checksum(token_address)]
        tx = router.functions.swapExactETHForTokens(
            int(amount_out_min), path, self._account.address, int(time()) + deadline_secs_from_now
        ).build_transaction({
            "from": self._account.address,
            "value": int(amount_in_wei),
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "chainId": self._w3.eth.chain_id,
        })
        gas_price = self._legacy_gas_price()
        if gas_price:
            tx["gasPrice"] = gas_price
        estimated_gas = self._w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated_gas * 1.20)  # colchón 20%
        return tx

    @log_function
    def sign_and_send(self, tx: dict) -> str:
        if DRY_RUN:
            logger.info(f"[DRY_RUN] No se envía tx. TX={tx}")
            return "0x" + "0"*64
        signed = self._w3.eth.account.sign_transaction(tx, private_key=self._account.key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()

    # ---- misc ----
    @log_function
    def wei_balance(self, address: str | None = None) -> int:
        addr = self.checksum(address or (self._account.address if self._account else WALLET_ADDRESS))
        return int(self._w3.eth.get_balance(addr))

    @log_function
    def get_last_block_timestamp(self) -> int:
        return int(self._w3.eth.get_block('latest')['timestamp'])

    # --- allowance / approve ---
    def allowance(self, token_address: str, owner: str, spender: str) -> int:
        erc20 = self.load_erc20(token_address)
        return int(erc20.functions.allowance(self.checksum(owner), self.checksum(spender)).call())

    def build_approve(self, token_address: str, spender: str, amount_wei: int) -> dict:
        if not self._account:
            raise RuntimeError("No hay PRIVATE_KEY configurada para firmar.")
        erc20 = self.load_erc20(token_address)
        tx = erc20.functions.approve(self.checksum(spender), int(amount_wei)).build_transaction({
            "from": self._account.address,
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "chainId": self._w3.eth.chain_id,
        })
        gas_price = self._legacy_gas_price()
        if gas_price:
            tx["gasPrice"] = gas_price
        estimated_gas = self._w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated_gas * 1.20)
        return tx

    # --- swapExactTokensForETH (token -> BNB) ---
    def build_swap_exact_tokens_for_eth(
        self,
        token_address: str,
        amount_in_tokens_raw: int,    # cantidad en unidades "raw" del token (según decimals)
        amount_out_min_bnb_wei: int,
        deadline_secs_from_now: int = 60
    ) -> dict:
        from time import time
        if not self._account:
            raise RuntimeError("No hay PRIVATE_KEY configurada para firmar.")
        router = self.load_router()
        path = [self.checksum(token_address), self._wbnb_addr]
        tx = router.functions.swapExactTokensForETH(
            int(amount_in_tokens_raw),
            int(amount_out_min_bnb_wei),
            path,
            self._account.address,
            int(time()) + deadline_secs_from_now,
        ).build_transaction({
            "from": self._account.address,
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "chainId": self._w3.eth.chain_id,
        })
        gas_price = self._legacy_gas_price()
        if gas_price:
            tx["gasPrice"] = gas_price
        estimated_gas = self._w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated_gas * 1.20)
        return tx

    # --- helper para amountOutMin token->BNB ---
    def get_amount_out_min_token_to_bnb(self, token_address: str, amount_in_tokens_raw: int, slippage_percent: float | None) -> int:
        slippage = DEFAULT_SLIPPAGE if slippage_percent is None else slippage_percent
        path = [self.checksum(token_address), self._wbnb_addr]
        amounts = self.get_amounts_out(amount_in_wei=amount_in_tokens_raw, path=path)  # reutiliza get_amounts_out
        amt_out = amounts[-1]
        return int(amt_out * (1 - (slippage / 100.0)))
    
    # -- utilidades de recibos/tx (añádelas a Web3Service) --

    def wait_for_receipt(self, tx_hash: str | HexBytes, timeout: int = 180) -> TxReceipt:
        return self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def get_transaction(self, tx_hash: str | HexBytes):
        return self._w3.eth.get_transaction(tx_hash)

    def wei_to_bnb(self, wei: int | float) -> float:
        return float(wei) / 1e18
