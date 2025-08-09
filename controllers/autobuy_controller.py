# controllers/autobuy_controller.py
from __future__ import annotations
import os, time
from typing import Optional

from services.web3_service import Web3Service
from repositories.history_repository import HistoryRepository
from repositories.monitor_repository import MonitorRepository
from repositories.action_repository import ActionRepository
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

# Todo en BNB
PNL_THRESHOLD_PERCENT = float(os.getenv("PNL_THRESHOLD_PERCENT", "2.0"))
MAX_FEE_BNB = float(os.getenv("MAX_FEE_BNB", "0.02"))
WBNB_ADDRESS = os.getenv("WBNB_ADDRESS")

class AutoBuyController:
    """
    Flujo:
      propose_buy -> si fuera de parámetros -> registrar_accion('pendiente') en ActionRepository (tipo='BUY')
                   -> si ok -> iniciar compra inmediata (crea history + retorna tx)
      confirm_pending_buy / cancel_pending_buy -> el monitor llama tras decisión del usuario
      record_buy_receipt -> con datos reales de compra
      finalize_sell -> cierra el ciclo con venta + pnl + bnb_amount
    """
    def __init__(self, db_path: str) -> None:
        self.w3s = Web3Service()
        self.history_repo = HistoryRepository(db_path=db_path)
        self.monitor_repo = MonitorRepository(db_path=db_path)
        self.action_repo  = ActionRepository(db_path=db_path)

    # ---------------- utilidades en BNB ----------------
    def _estimate_fee_bnb(self, gas_used: int, gas_price_wei: int) -> float:
        wei_cost = (gas_price_wei or 0) * (gas_used or 0)
        return wei_cost / 1e18

    def _compute_pnl_percent(self, expected_unit_cost_bnb: float, current_price_bnb: float) -> float:
        denom = max(current_price_bnb, 1e-18)
        return ((expected_unit_cost_bnb - current_price_bnb) / denom) * 100.0

    def _preview_amount_out_min(self, token_address: str, amount_bnb_wei: int) -> int:
        path = [WBNB_ADDRESS, token_address]
        return self.w3s.get_amount_out_min(amount_bnb_wei, path, None)

    def _expected_out_tokens(self, token_address: str, amount_out_min_raw: int) -> float:
        erc20 = self.w3s.load_erc20(token_address)
        decimals = self.w3s.get_token_decimals(erc20)
        return amount_out_min_raw / (10 ** decimals)

    # ============================
    # Propuesta de compra (fase 0)
    # ============================
    @log_function
    def propose_buy(
        self,
        pair_address: str,
        token_address: str,
        symbol: Optional[str],
        name: Optional[str],
        amount_bnb_wei: int,
        price_native_bnb: float,              # unitario al iniciar compra (de DexScreener)
        current_price_bnb: float,             # unitario actual (para PnL esperado)
        buy_fee_bnb_per_unit: float = 0.0,    # de GoPlus vía token_repository
        transfer_fee_bnb_per_unit: float = 0.0
    ) -> dict:
        # 1) amountOutMin y salida esperada (para prorratear gas)
        amount_out_min = self._preview_amount_out_min(token_address, amount_bnb_wei)
        if not amount_out_min or amount_out_min <= 0:
            return {"ok": False, "reason": "amountOutMin inválido"}

        expected_out_tokens = self._expected_out_tokens(token_address, amount_out_min)
        if expected_out_tokens <= 0:
            return {"ok": False, "reason": "expected_out_tokens inválido"}

        # 2) construir tx y estimar gas->fee BNB
        tx = self.w3s.build_swap_exact_eth_for_tokens(amount_bnb_wei, amount_out_min, token_address)
        fee_bnb_total = self._estimate_fee_bnb(tx.get("gas", 0), tx.get("gasPrice", 0) or 0)

        gas_bnb_per_unit = fee_bnb_total / max(expected_out_tokens, 1e-18)
        expected_unit_cost_bnb = price_native_bnb + buy_fee_bnb_per_unit + transfer_fee_bnb_per_unit + gas_bnb_per_unit

        pnl_percent = self._compute_pnl_percent(expected_unit_cost_bnb, current_price_bnb)

        # 3) reglas de negocio -> acciones pendientes si fuera de umbral o fee demasiado alta
        if pnl_percent < PNL_THRESHOLD_PERCENT or fee_bnb_total > MAX_FEE_BNB:
            self.action_repo.registrar_accion(pair_address=pair_address, tipo="BUY")
            # El monitor vigilará estado: 'pendiente' -> 'aprobada'/'cancelada'
            reason = "PNL_BELOW_THRESHOLD" if pnl_percent < PNL_THRESHOLD_PERCENT else "FEE_HIGH"
            return {
                "ok": True,
                "mode": "PENDING_USER",
                "reason": reason,
                "pnl_percent": pnl_percent,
                "fee_bnb_total": fee_bnb_total
            }

        # 4) dentro de parámetros -> iniciar compra inmediata
        return self._start_buy_immediate(
            pair_address=pair_address,
            token_address=token_address,
            symbol=symbol,
            name=name,
            amount_bnb_wei=amount_bnb_wei,
            amount_out_min=amount_out_min,
            tx=tx,
            buy_entry_price_bnb=price_native_bnb,
            buy_price_with_fees_bnb=expected_unit_cost_bnb
        )

    # ==============================
    # Iniciar compra (fase 1: buy)
    # ==============================
    def _start_buy_immediate(
        self,
        pair_address: str,
        token_address: str,
        symbol: Optional[str],
        name: Optional[str],
        amount_bnb_wei: int,
        amount_out_min: int,
        tx: dict,
        buy_entry_price_bnb: float,
        buy_price_with_fees_bnb: float
    ) -> dict:
        history_id = self.history_repo.create_buy(
            pair_address=pair_address,
            token_address=token_address,
            symbol=symbol,
            name=name,
            buy_entry_price=buy_entry_price_bnb,
            buy_price_with_fees=buy_price_with_fees_bnb,
            buy_date_ts=int(time.time())
        )
        # guardar el vínculo en monitor_state
        self.monitor_repo.set_history_id(pair_address, history_id)
        return {
            "ok": True,
            "mode": "IMMEDIATE",
            "history_id": history_id,
            "tx": tx,
            "amount_out_min": amount_out_min
        }

    @log_function
    def confirm_pending_buy(
        self,
        pair_address: str,
        token_address: str,
        symbol: Optional[str],
        name: Optional[str],
        amount_bnb_wei: int,
        price_native_bnb: float,
        current_price_bnb: float,
        buy_fee_bnb_per_unit: float = 0.0,
        transfer_fee_bnb_per_unit: float = 0.0
    ) -> dict:
        """
        Llamar cuando el monitor detecta 'aprobada' en ActionRepository para este par.
        Recalculo amounts/gas y procedo a iniciar compra.
        """
        estado = self.action_repo.obtener_estado(pair_address)
        if estado != "aprobada":
            return {"ok": False, "reason": f"acción no aprobada (estado={estado})"}

        amount_out_min = self._preview_amount_out_min(token_address, amount_bnb_wei)
        if not amount_out_min or amount_out_min <= 0:
            return {"ok": False, "reason": "amountOutMin inválido tras confirmación"}

        tx = self.w3s.build_swap_exact_eth_for_tokens(amount_bnb_wei, amount_out_min, token_address)
        fee_bnb_total = self._estimate_fee_bnb(tx.get("gas", 0), tx.get("gasPrice", 0) or 0)
        expected_out_tokens = self._expected_out_tokens(token_address, amount_out_min)
        gas_bnb_per_unit = fee_bnb_total / max(expected_out_tokens, 1e-18)
        buy_price_with_fees_bnb = price_native_bnb + buy_fee_bnb_per_unit + transfer_fee_bnb_per_unit + gas_bnb_per_unit

        # iniciamos compra
        result = self._start_buy_immediate(
            pair_address, token_address, symbol, name,
            amount_bnb_wei, amount_out_min, tx,
            buy_entry_price_bnb=price_native_bnb,
            buy_price_with_fees_bnb=buy_price_with_fees_bnb
        )
        return result

    @log_function
    def cancel_pending_buy(self, pair_address: str) -> dict:
        """El monitor llama cuando la acción se cancela; el monitor decide excluir el token."""
        estado = self.action_repo.obtener_estado(pair_address)
        if estado != "cancelada":
            return {"ok": False, "reason": f"acción no cancelada (estado={estado})"}
        # nada más que hacer aquí
        return {"ok": True}

    # =======================================
    # Registrar receipt de compra (fase 2)
    # =======================================
    @log_function
    def record_buy_receipt(self, pair_address: str, buy_real_price_bnb: float, buy_amount_tokens: float) -> dict:
        history_id = self.monitor_repo.get_history_id(pair_address)
        if not history_id:
            return {"ok": False, "reason": "history_id no encontrado en monitor"}
        self.history_repo.set_buy_final_result(history_id, buy_real_price_bnb, buy_amount_tokens)
        return {"ok": True, "history_id": history_id}

    # =========================
    # Finalizar venta (fase 3)
    # =========================
    @log_function
    def finalize_sell(
        self,
        pair_address: str,
        sell_entry_price_bnb: Optional[float],
        sell_price_with_fees_bnb: Optional[float],
        sell_real_price_bnb: float,
        sell_amount_tokens: float,
        bnb_amount: float
    ) -> dict:
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
