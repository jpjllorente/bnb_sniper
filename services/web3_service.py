from __future__ import annotations
import os
from typing import Any, List, Optional
from time import time
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxReceipt, HexBytes
from eth_account import Account
from web3.exceptions import ContractLogicError

from utils.load_abi import load_erc20_abi, load_pancake_router_abi
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

# --- ENV ---
BSC_RPC_URL      = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
PRIVATE_KEY      = os.getenv("PRIVATE_KEY") or ""
WALLET_ADDRESS   = os.getenv("WALLET_ADDRESS") or ""
WBNB_ADDRESS     = os.getenv("WBNB_ADDRESS", "0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
ROUTER_ADDRESS   = os.getenv("ROUTER_ADDRESS", "0x10ED43C718714eb63d5aA57B78B54704E256024E")
DEFAULT_SLIPPAGE = float(os.getenv("DEFAULT_SLIPPAGE", "3.0"))  # %
DRY_RUN          = os.getenv("DRY_RUN", "true").lower() == "true"

# GAS_MODE: auto | legacy | 1559
GAS_MODE                = os.getenv("GAS_MODE", "auto").lower()
GAS_PRICE_WEI_OVERRIDE  = int(os.getenv("GAS_PRICE_WEI", "0"))  # fuerza gasPrice legacy si > 0
PRIORITY_FEE_GWEI       = float(os.getenv("PRIORITY_FEE_GWEI", "1.5"))
MAX_FEE_MULTIPLIER      = float(os.getenv("MAX_FEE_MULTIPLIER", "2.0"))  # maxFeePerGas ≈ baseFee*mult + priority
GAS_LIMIT_MULTIPLIER    = float(os.getenv("GAS_LIMIT_MULTIPLIER", "1.20"))

# ABI mínima de la factory (para comprobar pares)
PANCAKE_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]


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

        # Contratos
        self._router = self._w3.eth.contract(address=self._router_addr, abi=self._router_abi)
        try:
            factory_addr = self._router.functions.factory().call()
            self._factory = self._w3.eth.contract(
                address=self._w3.to_checksum_address(factory_addr),
                abi=PANCAKE_FACTORY_ABI,
            )
        except Exception as e:
            logger.warning(f"No se pudo obtener la factory del router: {e}")
            self._factory = None

        # Detección de modo gas
        self._gas_mode = self._detect_gas_mode()
        logger.debug(f"Conectado a {rpc}; chain_id={self._w3.eth.chain_id}; gas_mode={self._gas_mode}")

    # ---------- util ----------
    def checksum(self, address: str) -> str:
        return self._w3.to_checksum_address(address)

    def load_router(self):
        return self._router

    def load_erc20(self, address: str):
        return self._w3.eth.contract(address=self.checksum(address), abi=self._erc20_abi)

    @log_function
    def get_token_decimals(self, erc20_contract) -> int:
        return int(erc20_contract.functions.decimals().call())

    # ---------- detección gas ----------
    def _detect_gas_mode(self) -> str:
        # Override manual
        if GAS_MODE in ("legacy", "1559"):
            return GAS_MODE

        # AUTO:
        try:
            latest = self._w3.eth.get_block("latest")
            base_fee = latest.get("baseFeePerGas", None)
            if base_fee is not None:
                # Nodo expone baseFeePerGas → probable 1559
                return "1559"
        except Exception:
            pass
        return "legacy"

    def _legacy_gas_price(self) -> int | None:
        if GAS_PRICE_WEI_OVERRIDE > 0:
            return GAS_PRICE_WEI_OVERRIDE
        try:
            return int(self._w3.eth.gas_price)
        except Exception:
            return None

    def _apply_gas_fields(self, tx: dict) -> dict:
        """
        Aplica **solo** los campos del modo activo y elimina los del otro para evitar:
        'both gasPrice and (maxFeePerGas or maxPriorityFeePerGas) specified'
        """
        # Limpieza
        tx.pop("gasPrice", None)
        tx.pop("maxFeePerGas", None)
        tx.pop("maxPriorityFeePerGas", None)
        tx.pop("accessList", None)

        if self._gas_mode == "1559":
            # type 2 (EIP-1559)
            tx["type"] = 2
            # baseFee
            try:
                latest = self._w3.eth.get_block("latest")
                base_fee = int(latest.get("baseFeePerGas") or self._w3.eth.gas_price)
            except Exception:
                base_fee = int(self._w3.eth.gas_price)
            # priority
            try:
                # web3.py 7.x
                priority = int(self._w3.eth.max_priority_fee)
            except Exception:
                priority = int(Web3.to_wei(PRIORITY_FEE_GWEI, "gwei"))
            # maxFee (margen sobre baseFee)
            max_fee = int(base_fee * MAX_FEE_MULTIPLIER + priority)
            tx["maxPriorityFeePerGas"] = priority
            tx["maxFeePerGas"] = max_fee
        else:
            # Legacy (type 0)
            tx["type"] = 0
            gas_price = self._legacy_gas_price()
            if gas_price:
                tx["gasPrice"] = int(gas_price)

        return tx

    # ---------- pares ----------
    def _pair_exists(self, token_a: str, token_b: str) -> bool:
        if not self._factory:
            return True
        try:
            pair = self._factory.functions.getPair(self.checksum(token_a), self.checksum(token_b)).call()
            return int(pair, 16) != 0
        except Exception:
            return False

    def _path_pairs_exist(self, path_cs: List[str]) -> bool:
        if len(path_cs) < 2:
            return False
        for i in range(len(path_cs) - 1):
            if not self._pair_exists(path_cs[i], path_cs[i + 1]):
                return False
        return True

    # ---------- quotes ----------
    @log_function
    def get_amounts_out(self, amount_in_wei: int, path: List[str]) -> list[int]:
        router = self.load_router()
        path_cs = [self.checksum(p) for p in path]
        if amount_in_wei is None or int(amount_in_wei) <= 0:
            return [0] * len(path_cs)
        if not self._path_pairs_exist(path_cs):
            logger.debug(f"get_amounts_out: par inexistente para path={path_cs}")
            return [0] * len(path_cs)
        try:
            amounts = router.functions.getAmountsOut(int(amount_in_wei), path_cs).call()
            return [int(x) for x in amounts]
        except ContractLogicError as e:
            logger.error(f"✗ get_amounts_out (revert): {e}")
            return [0] * len(path_cs)
        except Exception as e:
            logger.error(f"✗ get_amounts_out: {e}")
            return [0] * len(path_cs)

    @log_function
    def get_amount_out_min(self, amount_in_wei: int, path: List[str], slippage_percent: float | None = None) -> int:
        slippage = DEFAULT_SLIPPAGE if slippage_percent is None else slippage_percent
        amts = self.get_amounts_out(amount_in_wei, path)
        if not amts or int(amts[-1]) <= 0:
            return 0
        return int(int(amts[-1]) * (1 - (slippage / 100.0)))

    # ---------- builders ----------
    @log_function
    def build_swap_exact_eth_for_tokens(
        self,
        amount_in_wei: int,
        amount_out_min: int,
        token_address: str,
        deadline_secs_from_now: int = 60,
    ) -> dict[str, Any]:
        if not self._account:
            raise RuntimeError("No hay PRIVATE_KEY configurada para firmar.")

        path = [self._wbnb_addr, self.checksum(token_address)]
        tx = self._router.functions.swapExactETHForTokens(
            int(amount_out_min), path, self._account.address, int(time()) + deadline_secs_from_now
        ).build_transaction({
            "from": self._account.address,
            "value": int(amount_in_wei),
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "chainId": self._w3.eth.chain_id,
        })

        # aplicar modo gas (UN estilo) y estimar gas
        tx = self._apply_gas_fields(tx)
        estimated_gas = int(self._w3.eth.estimate_gas(tx))
        tx["gas"] = int(estimated_gas * GAS_LIMIT_MULTIPLIER)
        return tx

    def build_approve(self, token_address: str, spender: str, amount_wei: int) -> dict:
        if not self._account:
            raise RuntimeError("No hay PRIVATE_KEY configurada para firmar.")

        erc20 = self.load_erc20(token_address)
        tx = erc20.functions.approve(self.checksum(spender), int(amount_wei)).build_transaction({
            "from": self._account.address,
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "chainId": self._w3.eth.chain_id,
        })

        tx = self._apply_gas_fields(tx)
        estimated_gas = int(self._w3.eth.estimate_gas(tx))
        tx["gas"] = int(estimated_gas * GAS_LIMIT_MULTIPLIER)
        return tx

    def build_swap_exact_tokens_for_eth(
        self,
        token_address: str,
        amount_in_tokens_raw: int,
        amount_out_min_bnb_wei: int,
        deadline_secs_from_now: int = 60,
    ) -> dict:
        if not self._account:
            raise RuntimeError("No hay PRIVATE_KEY configurada para firmar.")

        path = [self.checksum(token_address), self._wbnb_addr]
        tx = self._router.functions.swapExactTokensForETH(
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

        tx = self._apply_gas_fields(tx)
        estimated_gas = int(self._w3.eth.estimate_gas(tx))
        tx["gas"] = int(estimated_gas * GAS_LIMIT_MULTIPLIER)
        return tx

    # ---------- send / misc ----------
    @log_function
    def sign_and_send(self, tx: dict) -> str:
        if DRY_RUN:
            logger.info(f"[DRY_RUN] No se envía tx. TX={tx}")
            return "0x" + "0" * 64
        signed = self._w3.eth.account.sign_transaction(tx, private_key=self._account.key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()

    @log_function
    def wei_balance(self, address: str | None = None) -> int:
        addr = self.checksum(address or (self._account.address if self._account else WALLET_ADDRESS))
        return int(self._w3.eth.get_balance(addr))

    @log_function
    def get_last_block_timestamp(self) -> int:
        return int(self._w3.eth.get_block("latest")["timestamp"])

    def allowance(self, token_address: str, owner: str, spender: str) -> int:
        erc20 = self.load_erc20(token_address)
        return int(erc20.functions.allowance(self.checksum(owner), self.checksum(spender)).call())

    def get_amount_out_min_token_to_bnb(self, token_address: str, amount_in_tokens_raw: int, slippage_percent: float | None) -> int:
        slippage = DEFAULT_SLIPPAGE if slippage_percent is None else slippage_percent
        path = [self.checksum(token_address), self._wbnb_addr]
        amts = self.get_amounts_out(amount_in_wei=amount_in_tokens_raw, path=path)
        if not amts or int(amts[-1]) <= 0:
            return 0
        return int(int(amts[-1]) * (1 - (slippage / 100.0)))

    def wait_for_receipt(self, tx_hash: str | HexBytes, timeout: int = 180) -> TxReceipt:
        return self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def get_transaction(self, tx_hash: str | HexBytes):
        return self._w3.eth.get_transaction(tx_hash)

    def wei_to_bnb(self, wei: int | float) -> float:
        return float(wei) / 1e18

    def token_balance_raw(self, token_address: str, wallet_address: Optional[str] = None) -> int:
        erc20 = self.load_erc20(token_address)
        wallet = self.checksum(wallet_address or os.getenv("WALLET_ADDRESS"))
        return int(erc20.functions.balanceOf(wallet).call())

    def token_balance_tokens(self, token_address: str, wallet_address: Optional[str] = None) -> float:
        raw = self.token_balance_raw(token_address, wallet_address)
        erc20 = self.load_erc20(token_address)
        decimals = self.get_token_decimals(erc20)
        return raw / (10 ** decimals)
