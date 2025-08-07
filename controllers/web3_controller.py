import os
from utils.log_config import logger_manager, log_function
from services.web3_service import Web3Service
from services.telegram_service import TelegramService
from utils.load_abi import load_erc20_abi, load_pancake_router_abi
from web3.exceptions import ContractLogicError
from models.token import Token

logger = logger_manager.setup_logger(__name__)


class Web3Controller:
    def __init__(self):
        self.web3_service = Web3Service()
        self.telegram = TelegramService()
        self.wallet = self.web3_service.get_wallet_address()
        self.router_address = self.web3_service.get_router_address()
        self.fee_estimado = float(os.getenv("DEFAULT_BUY_FEE", "0.003"))
        self.slippage = float(os.getenv("DEFAULT_SLIPPAGE", "0.01"))
        self.umbral_pnl = float(os.getenv("UMBRAL_PNL_NEGATIVO", "10.0"))
        self.router = self.web3_service.build_contract(
            self.router_address,
            load_pancake_router_abi()
        )

    @log_function
    def _get_erc20_contract(self, token_address: str):
        return self.web3_service.build_contract(
            token_address,
            load_erc20_abi()
        )

    @log_function
    def _get_token_decimals(self, contract):
        return self.web3_service.get_token_decimals(contract)

    @log_function
    def _get_amount_out_min(self, amount_in_wei, path: list) -> int | None:
        try:
            amounts = self.router.functions.getAmountsOut(amount_in_wei, path).call()
            return amounts[-1]
        except ContractLogicError as e:
            logger.error(f"Error en getAmountsOut: {e}")
            return None

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
    def _calcular_entry_price(self, bnb_usado: float, tokens_comprados: int, token_decimals: int) -> float:
        unidades = tokens_comprados / (10 ** token_decimals)
        if unidades == 0:
            raise ValueError("Unidades compradas es 0. No se puede dividir.")
        entry_price = bnb_usado / unidades
        logger.info(f"Entry price (BNB por token): {entry_price:.10f}")
        return entry_price

    @log_function
    def _calcular_coste_unitario(
        self,
        entry_price_bnb: float,
        gas_cost: float,
        fee_bnb: float,
        tokens_comprados: int,
        token_decimals: int
    ) -> float:
        unidades = tokens_comprados / (10 ** token_decimals)
        if unidades == 0:
            raise ValueError("No se puede dividir entre 0 unidades compradas")

        coste_total = (
            entry_price_bnb +
            gas_cost / unidades +
            fee_bnb / unidades
        )
        logger.info(f"Coste total por token (BNB): {coste_total:.10f}")
        return coste_total

    @log_function
    def _calcular_pnl_porcentual(self, coste_unitario: float, precio_actual: float) -> float:
        if precio_actual == 0:
            logger.error("Precio actual es 0, no se puede calcular PnL")
            return -100.0
        pnl = ((coste_unitario - precio_actual) / precio_actual) * 100
        logger.info(f"PnL estimado: {pnl:.2f}%")
        return pnl

    @log_function
    def _validar_rentabilidad(
        self,
        coste_unitario: float,
        precio_actual: float,
        token_obj,
        contexto: str,
        umbral_pnl_negativo: float
    ) -> bool:
        """
        Retorna True si la rentabilidad es aceptable.
        Si el PnL es demasiado negativo (porcentaje), pausa y notifica al usuario.
        """
        pnl = self._calcular_pnl_porcentual(coste_unitario, precio_actual)

        if pnl < -abs(umbral_pnl_negativo):
            logger.warning(f"❌ Rentabilidad insuficiente (PnL={pnl:.2f}%). Acción pausada.")
            self.telegram.solicitar_accion("compra", token_obj, contexto)
            return False

        return True

    @log_function
    def procesar_compra(self, token: Token, bnb_amount: float, auth_buy: bool = True, dry_run: bool = False):
        logger.info(f"🚀 Iniciando pipeline de compra para {token.symbol}")

        path = [os.getenv("WBNB_ADDRESS"), token.address]
        amount_in_wei = int(bnb_amount * 1e18)

        amount_out_min = self._get_amount_out_min(amount_in_wei, path)
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