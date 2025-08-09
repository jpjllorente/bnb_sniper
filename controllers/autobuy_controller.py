import os
from utils.log_config import logger_manager, log_function
from services.web3_service import Web3Service
from services.telegram_service import TelegramService

logger = logger_manager.setup_logger(__name__)
PNL_THRESHOLD_PERCENT = float(os.getenv("PNL_THRESHOLD_PERCENT", "2.0"))
MAX_FEE_USD = float(os.getenv("MAX_FEE_USD", "5.0"))

class AutoBuyController:
    def __init__(self) -> None:
        self.w3s = Web3Service()
        self.tg = TelegramService()

    def _estimate_fee_usd(self, gas_used: int, gas_price_wei: int, bnb_usd: float) -> float:
        wei_cost = gas_used * (gas_price_wei or 0)
        return (wei_cost / 1e18) * bnb_usd

    @log_function
    def preview_and_maybe_buy(self, token_address: str, amount_bnb_wei: int, price_ctx: dict) -> str | None:
        """
        price_ctx = {"bnb_usd": float, "expected_unit_cost_usd": float, "current_price_usd": float}
        pnl% = ((coste_unitario - precio_actual) / precio_actual) * 100
        """
        pnl_percent = ((price_ctx["expected_unit_cost_usd"] - price_ctx["current_price_usd"])
                        / price_ctx["current_price_usd"]) * 100.0
        if pnl_percent < PNL_THRESHOLD_PERCENT:
            logger.info(f"PnL% {pnl_percent:.2f} < umbral {PNL_THRESHOLD_PERCENT:.2f}. Compra pausada.")
            return None

        preview = {
            "path": [os.getenv("WBNB_ADDRESS"), token_address],
            "amount_out_min": self.w3s.get_amount_out_min(amount_bnb_wei, [os.getenv("WBNB_ADDRESS"), token_address], None)
        }
        if not preview["amount_out_min"] or preview["amount_out_min"] <= 0:
            logger.warning("amountOutMin inválido; cancelando compra")
            return None

        tx = self.w3s.build_swap_exact_eth_for_tokens(amount_bnb_wei, preview["amount_out_min"], token_address)
        fee_usd = self._estimate_fee_usd(tx.get("gas", 0), tx.get("gasPrice", 0) or 0, price_ctx["bnb_usd"])
        if fee_usd > MAX_FEE_USD:
            if not self.tg.ask_confirmation(f"Fee estimada {fee_usd:.2f} USD > {MAX_FEE_USD:.2f} USD. ¿Continuar?"):
                logger.info("Usuario canceló por fee elevada.")
                return None

        tx_hash = self.w3s.sign_and_send(tx)
        self.tg.notify(f"Compra enviada (dry-run={os.getenv('DRY_RUN','true')}) tx={tx_hash}")
        return tx_hash
