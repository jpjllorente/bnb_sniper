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

    @log_function
    def procesar_compra(self, token: Token, bnb_amount: float, auth_buy: bool = False, dry_run: bool = False):
        logger.info(f"🚀 Iniciando pipeline de compra para {token.symbol}")

        tx = self.web3_service.create_transaction(
            token_address=token.address,
            bnb_amount=bnb_amount,
            dry_run=dry_run
        )    






        path = [os.getenv("WBNB_ADDRESS"), token.address]
        amount_in_wei = int(bnb_amount * 1e18)

        amount_out_min = self.get_amount_out_min(amount_in_wei, path)
        if not amount_out_min:
            logger.error("❌ No se pudo obtener amountOutMin")
            return

        contrato = self._get_erc20_contract(token.address)
        decimals = self._get_token_decimals(contrato)

        entry_price = self._calcular_entry_price(
            bnb_usado=bnb_amount,
            tokens_comprados=amount_out_min,
            token_decimals=decimals
        )

        fee_bnb = bnb_amount * self.fee_estimado

        estimacion_tx = {
            "from": self.wallet,
            "to": self.router_address,
            "value": amount_in_wei,
            "gas": 300000  # tentativa para estimar
        }

        gas, gas_price, gas_cost_bnb = self._estimate_gas_cost(estimacion_tx)
        if gas is None:
            logger.error("❌ Error al estimar el gas.")
            return

        coste_unitario = self._calcular_coste_unitario(
            entry_price_bnb=entry_price,
            gas_cost=gas_cost_bnb,
            fee_bnb=fee_bnb,
            tokens_comprados=amount_out_min,
            token_decimals=decimals
        )
        if not auth_buy:
            if not self._validar_rentabilidad(
                coste_unitario=coste_unitario,
                precio_actual=token.price_native,
                token_obj=token,
                contexto="Rentabilidad insuficiente",
                umbral_pnl_negativo=self.umbral_pnl
            ):
                logger.warning("⏸ Compra detenida por baja rentabilidad.")
                return

        deadline = int(token.timestamp + 60 * 5)
        min_tokens = int(amount_out_min * (1 - self.slippage))

        tx = {
            "from": self.wallet,
            "to": self.router_address,
            "value": amount_in_wei,
            "gas": 300000,
            "data": self.router.encodeABI(
                fn_name="swapExactETHForTokensSupportingFeeOnTransferTokens",
                args=[min_tokens, path, self.wallet, deadline]
            ),
            "nonce": self.web3_service.get_nonce(),
            "gasPrice": gas_price
        }

        if dry_run:
            logger.info("🚧 DRY-RUN activado. Transacción no enviada.")
            return None

        return self.web3_service.sign_and_send(tx)