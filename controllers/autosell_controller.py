# controllers/autosell_controller.py
from __future__ import annotations
import os, time
from typing import Optional

from services.web3_service import Web3Service
from repositories.history_repository import HistoryRepository
from repositories.monitor_repository import MonitorRepository
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

WBNB_ADDRESS = os.getenv("WBNB_ADDRESS")

class AutoSellController:
    """
    Prepara y ejecuta la venta token->BNB:
      - calcula amountOutMin (slippage)
      - hace approve si es necesario
      - construye y (si quieres) envía la tx de venta
      - actualiza history con sell_* y resultados
    """
    def __init__(self, db_path: str) -> None:
        self.w3s = Web3Service()
        self.history_repo = HistoryRepository(db_path=db_path)
        self.monitor_repo = MonitorRepository(db_path=db_path)

    # -------- utilidades --------
    def _tokens_to_raw(self, token_address: str, amount_tokens: float) -> int:
        erc20 = self.w3s.load_erc20(token_address)
        decimals = self.w3s.get_token_decimals(erc20)
        return int(round(amount_tokens * (10 ** decimals)))

    def _raw_to_tokens(self, token_address: str, amount_raw: int) -> float:
        erc20 = self.w3s.load_erc20(token_address)
        decimals = self.w3s.get_token_decimals(erc20)
        return amount_raw / (10 ** decimals)

    # -------- API --------
    @log_function
    def prepare_sell(
        self,
        pair_address: str,
        token_address: str,
        sell_amount_tokens: float,
        slippage_percent: float
    ) -> dict:
        """
        Devuelve dict con approve_tx (opcional), sell_tx y amount_out_min_bnb_wei.
        """
        # 1) convertir a "raw"
        amount_in_raw = self._tokens_to_raw(token_address, sell_amount_tokens)

        # 2) amountOutMin en BNB
        amount_out_min_bnb_wei = self.w3s.get_amount_out_min_token_to_bnb(token_address, amount_in_raw, slippage_percent)
        if amount_out_min_bnb_wei <= 0:
            return {"ok": False, "reason": "amountOutMin inválido para venta"}

        # 3) allowance y approve si hace falta
        owner = os.getenv("WALLET_ADDRESS")
        allowance = self.w3s.allowance(token_address, owner, os.getenv("ROUTER_ADDRESS"))
        approve_tx = None
        if allowance < amount_in_raw:
            approve_tx = self.w3s.build_approve(token_address, os.getenv("ROUTER_ADDRESS"), amount_in_raw)

        # 4) construir tx de venta
        sell_tx = self.w3s.build_swap_exact_tokens_for_eth(token_address, amount_in_raw, amount_out_min_bnb_wei)

        return {
            "ok": True,
            "approve_tx": approve_tx,    # si None, no hace falta aprobar
            "sell_tx": sell_tx,
            "amount_out_min_bnb_wei": amount_out_min_bnb_wei
        }

    @log_function
    def record_sell_result(
        self,
        pair_address: str,
        sell_entry_price_bnb: Optional[float],
        sell_price_with_fees_bnb: Optional[float],
        sell_real_price_bnb: float,
        sell_amount_tokens: float,
        bnb_amount: float
    ) -> dict:
        """
        Llamar tras confirmar la venta para persistir valores en history y cerrar el ciclo.
        """
        history_id = self.monitor_repo.get_history_id(pair_address)
        if not history_id:
            return {"ok": False, "reason": "history_id no encontrado en monitor"}

        h = self.history_repo.get_by_id(history_id)
        if not h or h.get("buy_real_price") is None:
            return {"ok": False, "reason": "compra real no registrada todavía"}

        buy_real_price_bnb = float(h["buy_real_price"])
        denom = max(buy_real_price_bnb, 1e-18)
        pnl_percent = ((sell_real_price_bnb - buy_real_price_bnb) / denom) * sell_amount_tokens * 100.0

        self.history_repo.finalize_sell(
            history_id=history_id,
            sell_entry_price=sell_entry_price_bnb,
            sell_price_with_fees=sell_price_with_fees_bnb,
            sell_real_price=sell_real_price_bnb,
            sell_amount=sell_amount_tokens,
            pnl=pnl_percent,
            bnb_amount=bnb_amount
        )

        self.monitor_repo.clear_history_id(pair_address)
        return {"ok": True, "history_id": history_id, "pnl": pnl_percent, "bnb_amount": bnb_amount}
