# controllers/autobuy_controller.py
from __future__ import annotations
import os, time, json
from typing import Optional

from services.web3_service import Web3Service
from repositories.history_repository import HistoryRepository
from repositories.monitor_repository import MonitorRepository
from repositories.action_repository import ActionRepository
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

# ----------- Parámetros de negocio (todo en BNB) -----------
PNL_THRESHOLD_PERCENT = float(os.getenv("PNL_THRESHOLD_PERCENT", "2.0"))
MAX_FEE_BNB = float(os.getenv("MAX_FEE_BNB", "0.02"))  # ej. 0.02 BNB de tope; ajusta a tu gusto
WBNB_ADDRESS = os.getenv("WBNB_ADDRESS")

# Razones estándar para acciones pendientes (por claridad)
REASON_FEE_HIGH = "FEE_HIGH"
REASON_PNL_LOW  = "PNL_BELOW_THRESHOLD"

class AutoBuyController:
    """
    Flujo:
      0) propose_buy -> si fuera de parámetros -> crea acción PENDING (action_repository)
                        si ok -> inicia compra inmediatamente (crea history + retorna tx)
      1) confirm_pending_buy/cancel_pending_buy -> tras decisión del usuario via Telegram
      2) record_buy_receipt -> cuando tenemos datos reales de compra
      3) finalize_sell -> actualizar venta, pnl (%) y bnb_amount
    NOTA: aquí NO se envía la tx; eso lo hará tu trade_session/servicio.
    """
    def __init__(self, db_path: str) -> None:
        self.w3s = Web3Service()
        self.history_repo = HistoryRepository(db_path=db_path)
        self.monitor_repo = MonitorRepository(db_path=db_path)
        self.action_repo  = ActionRepository(db_path=db_path)

    # --------------- Utilidades en BNB ---------------
    def _estimate_fee_bnb(self, gas_used: int, gas_price_wei: int) -> float:
        wei_cost = (gas_price_wei or 0) * (gas_used or 0)
        return wei_cost / 1e18

    def _compute_pnl_percent(self, expected_unit_cost_bnb: float, current_price_bnb: float) -> float:
        # pnl% = ((coste_unitario - precio_actual) / precio_actual) * 100
        denom = max(current_price_bnb, 1e-18)
        return ((expected_unit_cost_bnb - current_price_bnb) / denom) * 100.0

    def _expected_out_tokens(self, token_address: str, amount_out_min_raw: int) -> float:
        """
        Convierte amountOutMin (en unidades "raw") a unidades humanas según decimals del token.
        """
        erc20 = self.w3s.load_erc20(token_address)
        decimals = self.w3s.get_token_decimals(erc20)
        return amount_out_min_raw / (10 ** decimals)

    def _preview_amount_out_min(self, token_address: str, amount_bnb_wei: int) -> int:
        path = [WBNB_ADDRESS, token_address]
        return self.w3s.get_amount_out_min(amount_bnb_wei, path, None)

    # ==========================================================
    # FASE 0: propuesta (decidir si va directa o queda "PENDING")
    # ==========================================================
    @log_function
    def propose_buy(self,
                    pair_address: str,
                    token_address: str,
                    symbol: Optional[str],
                    name: Optional[str],
                    amount_bnb_wei: int,
                    price_ctx: dict) -> dict:
        """
        price_ctx (TODO: confirma estos campos):
          - price_native_bnb: float     # precio unitario en BNB al iniciar compra (buy_entry_price)
          - buy_fee_bnb_per_unit: float # fee de compra por unidad (si no lo tienes, pasa 0.0)
          - transfer_fee_bnb_per_unit: float # fee de transferencia por unidad (si aplica; si no, 0.0)
          - current_price_bnb: float    # precio unitario actual del token (BNB) para calcular PnL esperado

        Devuelve:
          - {"ok": True, "mode": "IMMEDIATE", "history_id": ..., "tx": ..., "amount_out_min": ..., ...}
          - {"ok": True, "mode": "PENDING_USER", "action_id": ..., "reason": ...}
          - {"ok": False, "reason": "..."}
        """
        # 1) amountOutMin y expected_out (para distribuir gas por unidad si quieres)
        amount_out_min = self._preview_amount_out_min(token_address, amount_bnb_wei)
        if not amount_out_min or amount_out_min <= 0:
            return {"ok": False, "reason": "amountOutMin inválido"}

        expected_out_tokens = self._expected_out_tokens(token_address, amount_out_min)
        if expected_out_tokens <= 0:
            return {"ok": False, "reason": "expected_out_tokens inválido"}

        # 2) Construye TX para estimar gas
        tx = self.w3s.build_swap_exact_eth_for_tokens(amount_bnb_wei, amount_out_min, token_address)
        fee_bnb_total = self._estimate_fee_bnb(tx.get("gas", 0), tx.get("gasPrice", 0) or 0)

        # 3) Precio unitario estimado con fees (todo en BNB)
        #    gas por unidad = fee_bnb_total / expected_out_tokens
        gas_bnb_per_unit = fee_bnb_total / max(expected_out_tokens, 1e-18)
        expected_unit_cost_bnb = (
            float(price_ctx["price_native_bnb"]) +
            float(price_ctx.get("buy_fee_bnb_per_unit", 0.0)) +
            float(price_ctx.get("transfer_fee_bnb_per_unit", 0.0)) +
            gas_bnb_per_unit
        )

        # 4) PnL esperado en %
        pnl_percent = self._compute_pnl_percent(expected_unit_cost_bnb, float(price_ctx["current_price_bnb"]))

        # 5) Reglas de negocio para pasar a PENDING
        if pnl_percent < PNL_THRESHOLD_PERCENT:
            payload = {
                "pair_address": pair_address,
                "token_address": token_address,
                "symbol": symbol,
                "name": name,
                "amount_bnb_wei": amount_bnb_wei,
                "price_ctx": price_ctx,
                "amount_out_min": amount_out_min,
                "expected_out_tokens": expected_out_tokens,
                "expected_unit_cost_bnb": expected_unit_cost_bnb,
                "pnl_percent": pnl_percent,
            }
            action_id = self.action_repo.create_pending_action(
                pair_address=pair_address,
                token_address=token_address,
                action_type="BUY",
                reason=REASON_PNL_LOW,
                payload=json.dumps(payload, ensure_ascii=False)
            )
            return {"ok": True, "mode": "PENDING_USER", "action_id": action_id, "reason": REASON_PNL_LOW}

        if fee_bnb_total > MAX_FEE_BNB:
            payload = {
                "pair_address": pair_address,
                "token_address": token_address,
                "symbol": symbol,
                "name": name,
                "amount_bnb_wei": amount_bnb_wei,
                "price_ctx": price_ctx,
                "amount_out_min": amount_out_min,
                "expected_out_tokens": expected_out_tokens,
                "expected_unit_cost_bnb": expected_unit_cost_bnb,
                "pnl_percent": pnl_percent,
                "fee_bnb_total": fee_bnb_total,
                "tx": tx,  # opcional guardarlo; también se puede reconstruir en confirm
            }
            action_id = self.action_repo.create_pending_action(
                pair_address=pair_address,
                token_address=token_address,
                action_type="BUY",
                reason=REASON_FEE_HIGH,
                payload=json.dumps(payload, ensure_ascii=False)
            )
            return {"ok": True, "mode": "PENDING_USER", "action_id": action_id, "reason": REASON_FEE_HIGH}

        # 6) Dentro de parámetros → inicia compra inmediata
        return self._start_buy_immediate(
            pair_address=pair_address,
            token_address=token_address,
            symbol=symbol,
            name=name,
            amount_bnb_wei=amount_bnb_wei,
            amount_out_min=amount_out_min,
            tx=tx,
            buy_entry_price_bnb=float(price_ctx["price_native_bnb"]),
            # precio unitario con fees (estimado) para llenar history
            buy_price_with_fees_bnb=expected_unit_cost_bnb
        )

    # ================================================
    # FASE 1: iniciar compra (IMMEDIATE o tras CONFIRM)
    # ================================================
    def _start_buy_immediate(self,
                             pair_address: str,
                             token_address: str,
                             symbol: Optional[str],
                             name: Optional[str],
                             amount_bnb_wei: int,
                             amount_out_min: int,
                             tx: dict,
                             buy_entry_price_bnb: float,
                             buy_price_with_fees_bnb: float) -> dict:
        # Crear registro history AL INICIAR compra
        history_id = self.history_repo.create_buy(
            pair_address=pair_address,
            token_address=token_address,
            symbol=symbol,
            name=name,
            buy_entry_price=buy_entry_price_bnb,
            buy_price_with_fees=buy_price_with_fees_bnb,
            buy_date_ts=int(time.time())
        )
        # Vincular el ciclo (para localizar history_id en receipt/venta)
        self.monitor_repo.set_open_trade(pair_address, history_id)

        return {
            "ok": True,
            "mode": "IMMEDIATE",
            "history_id": history_id,
            "tx": tx,
            "amount_out_min": amount_out_min
        }

    @log_function
    def confirm_pending_buy(self, action_id: int) -> dict:
        """
        Llamado por el monitor cuando el usuario AUTORIZA la acción PENDING.
        Recalcula amounts/gas por seguridad, crea history y devuelve la tx.
        """
        action = self.action_repo.get_by_id(action_id)
        if not action or action.get("status") != "PENDING":
            return {"ok": False, "reason": "acción no encontrada o no está en estado PENDING"}

        payload = json.loads(action["payload"])
        pair_address   = payload["pair_address"]
        token_address  = payload["token_address"]
        symbol         = payload.get("symbol")
        name           = payload.get("name")
        amount_bnb_wei = int(payload["amount_bnb_wei"])
        price_ctx      = payload["price_ctx"]

        # Recomputa amountOutMin y gas
        amount_out_min = self._preview_amount_out_min(token_address, amount_bnb_wei)
        if not amount_out_min or amount_out_min <= 0:
            return {"ok": False, "reason": "amountOutMin inválido tras confirmación"}

        tx = self.w3s.build_swap_exact_eth_for_tokens(amount_bnb_wei, amount_out_min, token_address)
        fee_bnb_total = self._estimate_fee_bnb(tx.get("gas", 0), tx.get("gasPrice", 0) or 0)

        expected_out_tokens = self._expected_out_tokens(token_address, amount_out_min)
        gas_bnb_per_unit = fee_bnb_total / max(expected_out_tokens, 1e-18)
        buy_entry_price_bnb = float(price_ctx["price_native_bnb"])
        buy_price_with_fees_bnb = (
            buy_entry_price_bnb +
            float(price_ctx.get("buy_fee_bnb_per_unit", 0.0)) +
            float(price_ctx.get("transfer_fee_bnb_per_unit", 0.0)) +
            gas_bnb_per_unit
        )

        # Marcar acción como autorizada/cerrada
        self.action_repo.mark_authorized(action_id)

        # Iniciar compra (history + tx)
        return self._start_buy_immediate(
            pair_address=pair_address,
            token_address=token_address,
            symbol=symbol,
            name=name,
            amount_bnb_wei=amount_bnb_wei,
            amount_out_min=amount_out_min,
            tx=tx,
            buy_entry_price_bnb=buy_entry_price_bnb,
            buy_price_with_fees_bnb=buy_price_with_fees_bnb
        )

    @log_function
    def cancel_pending_buy(self, action_id: int) -> dict:
        """
        Llamado por el monitor cuando el usuario CANCELA.
        El monitor se encargará de excluir el token del seguimiento.
        """
        action = self.action_repo.get_by_id(action_id)
        if not action or action.get("status") != "PENDING":
            return {"ok": False, "reason": "acción no encontrada o no está en estado PENDING"}
        self.action_repo.mark_canceled(action_id)
        return {"ok": True}

    # ================================================
    # FASE 2: registrar receipt de compra (datos reales)
    # ================================================
    @log_function
    def record_buy_receipt(self,
                           pair_address: str,
                           buy_real_price_bnb: float,
                           buy_amount_tokens: float) -> dict:
        """
        Cuando llega el receipt con datos reales:
          - buy_real_price_bnb: (precio total en BNB / unidades reales)
          - buy_amount_tokens:  unidades reales compradas (ya normalizadas por decimals)
        """
        history_id = self.monitor_repo.get_history_id(pair_address)
        if not history_id:
            return {"ok": False, "reason": "history_id no encontrado en monitor"}
        self.history_repo.set_buy_final_result(history_id, buy_real_price_bnb, buy_amount_tokens)
        return {"ok": True, "history_id": history_id}

    # ================================================
    # FASE 3: finalizar venta
    # ================================================
    @log_function
    def finalize_sell(self,
                      pair_address: str,
                      sell_entry_price_bnb: Optional[float],
                      sell_price_with_fees_bnb: Optional[float],
                      sell_real_price_bnb: float,
                      sell_amount_tokens: float,
                      bnb_amount: float) -> dict:
        """
        Actualiza venta y resultados.
        pnl = (((sell_real_price - buy_real_price)/buy_real_price) * sell_amount * 100)
        Todos los precios unitarios en BNB; bnb_amount = beneficio en BNB.
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

        # El vínculo pair_address -> history_id lo puede limpiar el monitor cuando cierre el ciclo
        self.monitor_repo.clear_open_trade(pair_address)
        return {"ok": True, "history_id": history_id, "pnl": pnl_percent, "bnb_amount": bnb_amount}
