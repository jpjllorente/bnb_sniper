# orchestrators/monitor_orchestrator.py
from __future__ import annotations
import threading
import time
import os
from typing import Callable, Dict, Optional

from controllers.autobuy_controller import AutoBuyController
from controllers.autosell_controller import AutoSellController
from services.market_service import MarketService
from repositories.monitor_repository import MonitorRepository
from repositories.action_repository import ActionRepository
from repositories.token_repository import TokenRepository
from utils.log_config import logger_manager, log_function
from models.trade_session import TradeSession
from models.token import Token

# --- Config por entorno (todo en BNB) ---
TAKE_PROFIT_PCT   = float(os.getenv("TAKE_PROFIT_PCT",   "5.0"))  # arma trailing al superar +5%
TRAILING_GAP_PCT  = float(os.getenv("TRAILING_GAP_PCT",  "3.0"))  # trailing gap (bajo el pico)
STOP_LOSS_PCT     = float(os.getenv("STOP_LOSS_PCT",     "7.0"))  # stop loss duro desde buy_real
DEFAULT_SLIPPAGE  = float(os.getenv("DEFAULT_SLIPPAGE",  "3.0"))
MIN_SELL_TOKENS   = float(os.getenv("MIN_SELL_TOKENS",   "0.0"))  # umbral mínimo en unidades
MIN_SELL_VALUE_BNB= float(os.getenv("MIN_SELL_VALUE_BNB","0.0"))  # umbral mínimo en BNB
SELL_PERCENT_1    = float(os.getenv("SELL_PERCENT_1",    "0.6"))  # 60% primera salida
SELL_PERCENT_2    = float(os.getenv("SELL_PERCENT_2",    "1.0"))  # 100% del remanente

logger = logger_manager.setup_logger(__name__)

class MonitorOrchestrator:
    """
    Orquesta hilos de monitorización por par:
      - Un hilo por pair_address (identificador del hilo).
      - Arranque/parada individual por par.
      - Trailing + stop loss + salidas parciales 60%/40%.
    """
    def __init__(
        self,
        db_path: str,
        plan_fn: Optional[Callable[[str], dict]] = None,
        poll_seconds: float = 2.0,
        tick_seconds: float = 3.0
    ) -> None:
        self.db_path = db_path
        self.monitor_repo = MonitorRepository(db_path=db_path)
        self.action_repo  = ActionRepository(db_path=db_path)
        self.token_repo   = TokenRepository(db_path=db_path)
        self.autobuy      = AutoBuyController(db_path=db_path)
        self.autosell     = AutoSellController(db_path=db_path)
        self.market       = MarketService()

        self.poll_seconds = poll_seconds
        self.tick_seconds = tick_seconds
        self.plan_fn = plan_fn or (lambda pair: {"amount_bnb_wei": int(0.01 * 1e18)})

        self._threads: Dict[str, dict] = {}   # pair_address -> {thread, stop_evt}
        self._stop_evt = threading.Event()

        # Estado de trailing/stop-loss por par
        self._trail: Dict[str, dict] = {}     # pair -> {"armed": bool, "peak": float, "trailing_stop": float, "stop_loss": float}
        # Estado de ventas parciales por par
        self._partial: Dict[str, dict] = {}   # pair -> {"stage": 0|1, "sold_tokens": float, "bnb_received": float}

    # ---------- API pública ----------
    @log_function
    def start(self) -> None:
        self._stop_evt.clear()
        t = threading.Thread(target=self._run_loop, name="MonitorOrchestrator", daemon=True)
        t.start()
        logger.info("MonitorOrchestrator arrancado.")

    @log_function
    def stop(self) -> None:
        self._stop_evt.set()
        for _, info in list(self._threads.items()):
            info["stop_evt"].set()
        logger.info("MonitorOrchestrator detenido (orden enviada).")

    @log_function
    def start_thread_for_pair(self, pair_address: str) -> None:
        if pair_address in self._threads and self._threads[pair_address]["thread"].is_alive():
            return
        stop_evt = threading.Event()
        th = threading.Thread(
            target=self._monitor_worker,
            args=(pair_address, stop_evt),
            name=f"MonitorPair-{pair_address}",
            daemon=True
        )
        self._threads[pair_address] = {"thread": th, "stop_evt": stop_evt}
        th.start()
        logger.info(f"Hilo iniciado para {pair_address}")

    @log_function
    def stop_thread_for_pair(self, pair_address: str) -> None:
        info = self._threads.get(pair_address)
        if not info:
            return
        info["stop_evt"].set()
        logger.info(f"Parada solicitada para hilo {pair_address}")

    # ---------- Loop principal ----------
    def _run_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._spawn_threads_for_open_trades()
                self._digest_actions()
            except Exception as e:
                logger.exception(f"Error en loop de orquestador: {e}")
            time.sleep(self.poll_seconds)

    # ---------- Gestión de estados ----------
    def _spawn_threads_for_open_trades(self) -> None:
        """
        Si implementas un listado en monitor_repo (p.ej. list_pairs_with_history),
        aquí arrancas los hilos que falten. Placeholder para no romper nada.
        """
        pass

    def _digest_actions(self) -> None:
        """
        Acciones en ActionRepository:
          - 'aprobada' -> confirmar compra y lanzar hilo
          - 'cancelada' -> limpiar y excluir
        """
        for pair in self._list_action_pairs_safe():
            estado = self.action_repo.obtener_estado(pair)
            tipo = self.action_repo.obtener_tipo(pair)
            if estado == "aprobada" and tipo == "compra":
                self._handle_authorized(pair)
            elif estado == "cancelada":
                self._handle_canceled(pair)
            # 'pendiente' -> no hacer nada

    def _list_action_pairs_safe(self) -> list[str]:
        """
        Si tu ActionRepository no tiene list_pairs(), devolvemos [] sin romper.
        """
        try:
            return self.action_repo.list_pairs()  # si no existe, el except devuelve []
        except Exception:
            return []

    # ---------- Transiciones ----------
    def _handle_authorized(self, pair_address: str) -> None:
        """
        Usuario autoriza BUY -> confirmar compra y arrancar hilo de monitor.
        """
        row = self.token_repo.get_by_pair(pair_address)
        if not row:
            logger.warning(f"No hay token en token_repository para {pair_address}")
            return

        token = Token.from_row(row) if hasattr(Token, "from_row") else Token(
            pair_address=row["pair_address"], name=row["name"], symbol=row["symbol"],
            address=row["address"], price_native=row["price_native"], price_usd=row["price_usd"],
            pair_created_at=row["pair_created_at"], image_url=row["image_url"], open_graph=row["open_graph"]
        )
        buy_tax, _, transfer_tax = self.token_repo.get_taxes(pair_address)

        plan = self.plan_fn(pair_address)
        amount_bnb_wei = int(plan["amount_bnb_wei"])

        price_native_bnb  = float(token.price_native or 0.0)
        current_price_bnb = price_native_bnb

        res = self.autobuy.confirm_pending_buy(
            pair_address=pair_address,
            token_address=token.address,
            symbol=token.symbol,
            name=token.name,
            amount_bnb_wei=amount_bnb_wei,
            price_native_bnb=price_native_bnb,
            current_price_bnb=current_price_bnb,
            buy_fee_bnb_per_unit=float(buy_tax or 0.0),
            transfer_fee_bnb_per_unit=float(transfer_tax or 0.0),
        )
        if not res.get("ok"):
            logger.warning(f"Confirmación de compra fallida para {pair_address}: {res}")
            return

        self.start_thread_for_pair(pair_address)

    def _handle_canceled(self, pair_address: str) -> None:
        self.action_repo.limpiar(pair_address)
        logger.info(f"Acción cancelada y limpiada para {pair_address}")

    # ---------- Worker por par ----------
    def _monitor_worker(self, pair_address: str, stop_evt: threading.Event) -> None:
        logger.info(f"[{pair_address}] monitor iniciado")

        # Inicializa estado parcial si no existe
        if pair_address not in self._partial:
            self._partial[pair_address] = {"stage": 0, "sold_tokens": 0.0, "bnb_received": 0.0}

        while not stop_evt.is_set():
            try:
                # 1) history_id (si no hay, terminamos)
                history_id = self.monitor_repo.get_history_id(pair_address)
                if not history_id:
                    logger.info(f"[{pair_address}] sin history_id; parando hilo.")
                    break

                # 2) Token + sesión (ajusta a tu modelo real)
                token_row = self.token_repo.get_by_pair(pair_address)
                if not token_row:
                    stop_evt.wait(self.tick_seconds); continue

                token = Token.from_row(token_row) if hasattr(Token, "from_row") else Token(
                    pair_address=token_row["pair_address"], name=token_row["name"], symbol=token_row["symbol"],
                    address=token_row["address"], price_native=token_row["price_native"], price_usd=token_row["price_usd"],
                    pair_created_at=token_row["pair_created_at"], image_url=token_row["image_url"], open_graph=token_row["open_graph"]
                )
                session = TradeSession(entry_price=token_row.get("price_native") or 0.0,
                                       buy_price_with_fees=token_row.get("price_native") or 0.0)

                # 3) Precio actual
                price_now = self.market.get_price_native_bnb(pair_address)
                if price_now is not None:
                    token.price_native = price_now

                # 4) Actualizar monitor_state (Streamlit lee de aquí)
                self.monitor_repo.save_state(token, session)

                # 5) Trailing / Stop Loss / Salidas parciales
                hid = self.monitor_repo.get_history_id(pair_address)
                if not hid:
                    logger.info(f"[{pair_address}] sin history_id; parando hilo.")
                    break

                h = self.autobuy.history_repo.get_by_id(hid)
                if not h or h.get("buy_real_price") is None:
                    # Aún sin precio real (no llegó el receipt)
                    stop_evt.wait(self.tick_seconds)
                    continue

                buy_real = float(h["buy_real_price"])
                if token.price_native is None:
                    stop_evt.wait(self.tick_seconds)
                    continue

                current = float(token.price_native)

                decision = self._update_trailing(pair_address, current, buy_real)
                if decision["action"] != "SELL":
                    stop_evt.wait(self.tick_seconds)
                    continue

                # ---- Disparo de venta ----
                stage = self._partial[pair_address]["stage"]
                sell_amount_tokens = self._determine_sell_amount(token.address, current, stage)
                if sell_amount_tokens <= 0:
                    logger.warning(f"[{pair_address}] cantidad a vender no disponible; skipping sell.")
                    stop_evt.wait(self.tick_seconds)
                    continue

                prep = self.autosell.prepare_sell(
                    pair_address=pair_address,
                    token_address=token.address,
                    sell_amount_tokens=sell_amount_tokens,
                    slippage_percent=DEFAULT_SLIPPAGE
                )
                if not prep.get("ok"):
                    logger.warning(f"[{pair_address}] prepare_sell falló: {prep}")
                    stop_evt.wait(self.tick_seconds)
                    continue

                if prep["approve_tx"] is not None:
                    self.autobuy.w3s.sign_and_send(prep["approve_tx"])

                # Enviar y medir (parcial)
                meas = self.autosell.send_sell_and_measure(
                    token_address=token.address,
                    sell_amount_tokens=sell_amount_tokens,
                    sell_tx=prep["sell_tx"]
                )
                if not meas.get("ok"):
                    logger.warning(f"[{pair_address}] send_sell_and_measure falló: {meas}")
                    stop_evt.wait(self.tick_seconds)
                    continue

                # Acumular parciales
                self._partial[pair_address]["sold_tokens"] += sell_amount_tokens
                self._partial[pair_address]["bnb_received"] += float(meas["bnb_bruto_recibido"])

                if stage == 0:
                    # Primera venta (≈60%): rearmar trailing sobre el remanente
                    self._trail[pair_address]["armed"] = True
                    self._trail[pair_address]["peak"] = current
                    self._trail[pair_address]["trailing_stop"] = current * (1 - TRAILING_GAP_PCT/100.0)
                    self._partial[pair_address]["stage"] = 1
                    logger.info(f"[{pair_address}] Venta parcial 1/2 completada (~60%).")
                    stop_evt.wait(self.tick_seconds)
                    continue

                # Segunda venta (≈40% remanente): cerrar ciclo e historial
                total_tokens = self._partial[pair_address]["sold_tokens"]
                total_bnb    = self._partial[pair_address]["bnb_received"]
                if total_tokens <= 0:
                    logger.warning(f"[{pair_address}] total_tokens=0 en segunda venta; abort.")
                    break

                sell_real_price_agg = total_bnb / total_tokens
                pnl_total = ((sell_real_price_agg - buy_real) / max(buy_real, 1e-18)) * total_tokens * 100.0
                bnb_amount = (sell_real_price_agg - buy_real) * total_tokens

                self.autobuy.history_repo.finalize_sell(
                    history_id=hid,
                    sell_entry_price=current,
                    sell_price_with_fees=sell_real_price_agg,  # si estimas fees aparte, ajusta aquí
                    sell_real_price=sell_real_price_agg,
                    sell_amount=total_tokens,
                    pnl=pnl_total,
                    bnb_amount=bnb_amount
                )
                self.monitor_repo.clear_history_id(pair_address)

                logger.info(f"[{pair_address}] Venta total completada. Tokens={total_tokens:.6f} BNB={total_bnb:.6f}")
                # Limpieza de estados locales
                self._partial.pop(pair_address, None)
                self._trail.pop(pair_address, None)
                break  # fin del hilo

            except Exception as e:
                logger.exception(f"[{pair_address}] error en worker: {e}")

            stop_evt.wait(self.tick_seconds)

        logger.info(f"[{pair_address}] monitor detenido")

    # ---------- Trailing / Stop-loss ----------
    def _init_trailing(self, pair_address: str, buy_real: float) -> None:
        self._trail[pair_address] = {
            "armed": TAKE_PROFIT_PCT <= 0.0,  # arma desde el inicio si TP=0
            "peak": buy_real,
            "trailing_stop": buy_real * (1 - TRAILING_GAP_PCT/100.0),
            "stop_loss":     buy_real * (1 - STOP_LOSS_PCT/100.0),
        }

    def _update_trailing(self, pair_address: str, current: float, buy_real: float) -> dict:
        st = self._trail.get(pair_address)
        if not st:
            self._init_trailing(pair_address, buy_real)
            st = self._trail[pair_address]

        # Stop-loss duro
        if current <= st["stop_loss"]:
            return {"action": "SELL", "reason": "STOP_LOSS"}

        # Armar trailing al superar el TP
        if not st["armed"]:
            arm_level = buy_real * (1 + TAKE_PROFIT_PCT/100.0)
            if current >= arm_level:
                st["armed"] = True
                st["peak"] = current
                st["trailing_stop"] = current * (1 - TRAILING_GAP_PCT/100.0)
                return {"action": "HOLD", "reason": "ARMED_TRAILING"}
        else:
            # Si sube, sube el pico y recalcula trailing_stop
            if current > st["peak"]:
                st["peak"] = current
                st["trailing_stop"] = current * (1 - TRAILING_GAP_PCT/100.0)
                return {"action": "HOLD", "reason": "NEW_PEAK"}
            # Si cae hasta el trailing_stop, vender
            if current <= st["trailing_stop"]:
                return {"action": "SELL", "reason": "TRAILING_HIT"}

        return {"action": "HOLD", "reason": "NONE"}

    # ---------- Cantidad a vender (on-chain) ----------
    def _determine_sell_amount(self, token_address: str, current_price_bnb: float, stage: int) -> float:
        """
        Lee on‑chain el balance y devuelve la cantidad a vender según la etapa:
          stage 0 -> 60% del balance
          stage 1 -> 100% del remanente
        Aplica mínimos (unidades/valor).
        """
        balance = self.autobuy.w3s.token_balance_tokens(token_address)
        if balance <= 0:
            return 0.0

        percent = SELL_PERCENT_1 if stage == 0 else SELL_PERCENT_2
        amount = balance * percent

        if amount < MIN_SELL_TOKENS:
            return 0.0
        if amount * current_price_bnb < MIN_SELL_VALUE_BNB:
            return 0.0
        return float(amount)
