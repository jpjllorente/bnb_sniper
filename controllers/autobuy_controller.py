# controllers/autobuy_controller.py
from __future__ import annotations
import os
import time
from typing import Optional
from web3 import Web3

from services.web3_service import Web3Service
from repositories.history_repository import HistoryRepository
from repositories.monitor_repository import MonitorRepository
from repositories.action_repository import ActionRepository
from repositories.meta_repository import MetaRepository  # para el fusible de primera compra
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

# ----------------- Config vía entorno -----------------
PNL_THRESHOLD_PERCENT = float(os.getenv("PNL_THRESHOLD_PERCENT", "2.0"))
MAX_FEE_BNB = float(os.getenv("MAX_FEE_BNB", "0.02"))
WBNB_ADDRESS = os.getenv("WBNB_ADDRESS")

# Fusible y cap de gasto para la primera prueba real
FIRST_REAL_BUY = os.getenv("FIRST_REAL_BUY", "false").lower() == "true"
TEST_MAX_SPEND_BNB = float(os.getenv("TEST_MAX_SPEND_BNB", "0.001"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"


class AutoBuyController:
    """
    Flujo:
      propose_buy -> si fuera de parámetros -> registrar_accion('pendiente') en ActionRepository (tipo='BUY')
                   -> si ok -> iniciar compra inmediata (crea history + retorna tx)
      confirm_pending_buy / cancel_pending_buy -> el monitor llama tras decisión del usuario
      record_buy_receipt -> con datos reales de compra
      finalize_sell -> cierra el ciclo con venta + pnl + bnb_amount

    Compatibilidad:
      - DiscoveryController puede llamar a procesar_token(token) y aquí delega a propose_buy con cap de gasto.
    """

    def __init__(self, db_path: str) -> None:
        self.w3s = Web3Service()
        self.db_path = db_path or os.getenv("DB_PATH", "./data/memecoins.db")
        self.history_repo = HistoryRepository(db_path=self.db_path)
        self.monitor_repo = MonitorRepository(db_path=self.db_path)
        self.action_repo = ActionRepository(db_path=self.db_path)
        self.meta = MetaRepository(db_path=self.db_path)

    # ---------------- helpers fusible/cap ----------------
    def _first_buy_already_done(self) -> bool:
        return self.meta.get("first_buy_done", "0") == "1"

    def _apply_test_cap_wei(self, amount_bnb_wei: int) -> int:
        try:
            cap_wei = Web3.to_wei(TEST_MAX_SPEND_BNB, "ether")
        except Exception:
            cap_wei = Web3.to_wei(0.001, "ether")
        if amount_bnb_wei > cap_wei:
            logger.info(
                f"[autobuy] Cap de prueba activo. Ajuste de "
                f"{self.w3s.wei_to_bnb(amount_bnb_wei)} BNB → {self.w3s.wei_to_bnb(cap_wei)} BNB"
            )
            return cap_wei
        return amount_bnb_wei

    # ---------------- utilidades en BNB ----------------
    def _estimate_fee_bnb(self, gas_used: int, gas_price_wei: int) -> float:
        wei_cost = (gas_price_wei or 0) * (gas_used or 0)
        return wei_cost / 1e18

    def _compute_pnl_percent(self, expected_unit_cost_bnb: float, current_price_bnb: float) -> float:
        denom = max(current_price_bnb, 1e-18)
        return ((expected_unit_cost_bnb - current_price_bnb) / denom) * 100.0

    def _preview_amount_out_min(self, token_address: str, amount_bnb_wei: int) -> int:
        if not WBNB_ADDRESS:
            # Falla controlada si falta la variable
            logger.error("WBNB_ADDRESS no configurada en entorno.")
            return 0
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
        buy_fee_bnb_per_unit: float = 0.0,    # de GoPlus u otras fuentes
        transfer_fee_bnb_per_unit: float = 0.0
    ) -> dict:
        # Fusible de primera compra: si activo y ya se hizo una compra real, bloquea
        if FIRST_REAL_BUY and self._first_buy_already_done():
            logger.info("[autobuy] Fusible activo: primera compra ya realizada. Bloqueando nuevas compras.")
            return {"ok": False, "reason": "FIRST_BUY_FUSE_BLOCKED"}

        # Cap de gasto para la prueba
        amount_bnb_wei = self._apply_test_cap_wei(amount_bnb_wei)

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
        expected_unit_cost_bnb = (
            price_native_bnb + buy_fee_bnb_per_unit + transfer_fee_bnb_per_unit + gas_bnb_per_unit
        )

        pnl_percent = self._compute_pnl_percent(expected_unit_cost_bnb, current_price_bnb)

        # 3) reglas de negocio -> acciones pendientes si fuera de umbral o fee demasiado alta
        if pnl_percent < PNL_THRESHOLD_PERCENT or fee_bnb_total > MAX_FEE_BNB:
            reason = "PNL_BELOW_THRESHOLD" if pnl_percent < PNL_THRESHOLD_PERCENT else "FEE_HIGH"
            self.action_repo.registrar_accion(
                pair_address=pair_address,
                tipo="compra",
                token_address=token_address,
                motivo=reason
            )
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
        # Fusible de primera compra
        if FIRST_REAL_BUY and self._first_buy_already_done():
            logger.info("[autobuy] Fusible activo en confirm_pending_buy: primera compra ya realizada.")
            return {"ok": False, "reason": "FIRST_BUY_FUSE_BLOCKED"}

        estado = self.action_repo.obtener_estado(pair_address)
        if estado != "aprobada":
            return {"ok": False, "reason": f"acción no aprobada (estado={estado})"}

        # Cap de gasto
        amount_bnb_wei = self._apply_test_cap_wei(amount_bnb_wei)

        amount_out_min = self._preview_amount_out_min(token_address, amount_bnb_wei)
        if not amount_out_min or amount_out_min <= 0:
            return {"ok": False, "reason": "amountOutMin inválido tras confirmación"}

        tx = self.w3s.build_swap_exact_eth_for_tokens(amount_bnb_wei, amount_out_min, token_address)
        fee_bnb_total = self._estimate_fee_bnb(tx.get("gas", 0), tx.get("gasPrice", 0) or 0)
        expected_out_tokens = self._expected_out_tokens(token_address, amount_out_min)
        gas_bnb_per_unit = fee_bnb_total / max(expected_out_tokens, 1e-18)
        buy_price_with_fees_bnb = price_native_bnb + buy_fee_bnb_per_unit + transfer_fee_bnb_per_unit + gas_bnb_per_unit

        # iniciar compra
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

    @log_function
    def await_and_record_buy_receipt(self, pair_address: str, token_address: str, token_decimals: int, tx_hash: str) -> dict:
        """
        Espera el receipt de la compra, parsea cuántos tokens se recibieron realmente,
        calcula el precio real unitario (incluyendo gas) y lo persiste en history.
        Si el fusible está activo y es la primera compra real exitosa (no DRY_RUN),
        marca 'first_buy_done' para bloquear siguientes.
        """
        receipt = self.w3s.wait_for_receipt(tx_hash)
        tx = self.w3s.get_transaction(tx_hash)
        wallet = Web3.to_checksum_address(os.getenv("WALLET_ADDRESS"))
        token_addr_cs = Web3.to_checksum_address(token_address)

        TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()
        amount_received_tokens = None

        for log in receipt["logs"]:
            # topic0 puede venir bytes/HexBytes/str; normalizamos a hex
            topic0 = log["topics"][0].hex() if hasattr(log["topics"][0], "hex") else (log["topics"][0] if isinstance(log["topics"][0], str) else None)
            if log["address"].lower() == token_addr_cs.lower() and topic0 == TRANSFER_TOPIC:
                # topics[2] = 'to'
                to_hex = log["topics"][2].hex() if hasattr(log["topics"][2], "hex") else str(log["topics"][2])
                to_addr = Web3.to_checksum_address("0x" + to_hex[-40:])
                if to_addr == wallet:
                    raw = int(log["data"], 16)
                    amount_received_tokens = raw / (10 ** token_decimals)
                    break

        if amount_received_tokens is None or amount_received_tokens <= 0:
            return {"ok": False, "reason": "No se pudo determinar la cantidad real recibida (Transfer no encontrado)."}

        gas_used = int(receipt["gasUsed"])
        gas_price = int(tx.get("gasPrice") or 0)
        total_bnb_spent = self.w3s.wei_to_bnb(int(tx["value"]) + gas_used * gas_price)
        buy_real_price_bnb = total_bnb_spent / amount_received_tokens

        # persistimos en history
        history_id = self.monitor_repo.get_history_id(pair_address)
        if not history_id:
            return {"ok": False, "reason": "history_id no encontrado en monitor"}

        self.history_repo.set_buy_final_result(history_id, buy_real_price_bnb, amount_received_tokens)

        # Marcar fusible como usado SOLO si no es DRY_RUN y el flag está habilitado
        if FIRST_REAL_BUY and not DRY_RUN:
            logger.info("[autobuy] Marcando 'first_buy_done' tras receipt OK (no DRY_RUN).")
            self.meta.set("first_buy_done", "1")

        return {
            "ok": True,
            "history_id": history_id,
            "buy_real_price_bnb": buy_real_price_bnb,
            "buy_amount_tokens": amount_received_tokens,
            "gas_used": gas_used
        }

    # ==========================================
    # Compatibilidad con DiscoveryController
    # ==========================================
    @log_function
    def procesar_token(self, token) -> dict:
        """
        Compatibilidad con DiscoveryController: procesa un token descubierto y decide si propone compra.
        Limita el gasto a TEST_MAX_SPEND_BNB (por defecto 0.001 BNB).
        """
        # Si el fusible está activo y ya se hizo la primera compra, bloquea
        if FIRST_REAL_BUY and self._first_buy_already_done():
            logger.info("[autobuy] Fusible activo en procesar_token: primera compra ya realizada.")
            return {"ok": False, "reason": "FIRST_BUY_FUSE_BLOCKED"}

        # Cap de gasto (convierte a wei)
        try:
            amount_bnb_wei = Web3.to_wei(TEST_MAX_SPEND_BNB, "ether")
        except Exception:
            amount_bnb_wei = Web3.to_wei(0.001, "ether")
        amount_bnb_wei = self._apply_test_cap_wei(amount_bnb_wei)

        # Precio nativo actual como referencia
        price_native_bnb = float(getattr(token, "price_native", 0.0) or 0.0)
        current_price_bnb = price_native_bnb

        # Taxes por unidad en BNB (si los tuvieses en repositorio de tasas por unidad, intégralos aquí)
        buy_fee_bnb_per_unit = 0.0
        transfer_fee_bnb_per_unit = 0.0

        return self.propose_buy(
            pair_address=getattr(token, "pair_address"),
            token_address=getattr(token, "address"),
            symbol=getattr(token, "symbol", None),
            name=getattr(token, "name", None),
            amount_bnb_wei=amount_bnb_wei,
            price_native_bnb=price_native_bnb,
            current_price_bnb=current_price_bnb,
            buy_fee_bnb_per_unit=buy_fee_bnb_per_unit,
            transfer_fee_bnb_per_unit=transfer_fee_bnb_per_unit,
        )
