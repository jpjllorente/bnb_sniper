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

logger = logger_manager.setup_logger(__name__)

class MonitorOrchestrator:
    """
    Orquesta hilos de monitorización por par:
      - Cada hilo = 1 pair_address (identificador del hilo).
      - Podemos start/stop un hilo concreto sin parar todo.

    Dependencias:
      - plan_fn(pair_address) -> dict con 'amount_bnb_wei' y parámetros necesarios para buy.
        (Puedes inyectar tu propia función o servicio que devuelva el plan de compra)
    """
    def __init__(
        self,
        db_path: str,
        plan_fn: Optional[Callable[[str], dict]] = None,
        poll_seconds: float = 2.0,    # frecuencia del loop del orquestador
        tick_seconds: float = 3.0     # frecuencia de actualización de cada hilo
    ) -> None:
        self.db_path = db_path
        self.monitor_repo = MonitorRepository(db_path=db_path)
        self.action_repo = ActionRepository(db_path=db_path)
        self.token_repo  = TokenRepository(db_path=db_path)
        self.autobuy     = AutoBuyController(db_path=db_path)
        self.autosell = AutoSellController(db_path=self.db_path)
        self.market      = MarketService()

        self.poll_seconds = poll_seconds
        self.tick_seconds = tick_seconds
        self.plan_fn = plan_fn or (lambda pair: {"amount_bnb_wei": int(0.01 * 1e18)})

        self._threads: Dict[str, dict] = {}  # pair_address -> {thread, stop_evt}
        self._stop_evt = threading.Event()

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
        # parar todos los hilos de pares
        for pair, info in list(self._threads.items()):
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
                # 1) Arrancar hilos para pares con compra ya iniciada (history_id presente)
                self._spawn_threads_for_open_trades()

                # 2) Gestionar acciones pendientes (aprobadas/canceladas)
                self._digest_actions()

            except Exception as e:
                logger.exception(f"Error en loop de orquestador: {e}")

            time.sleep(self.poll_seconds)

    # ---------- Gestión de estados ----------
    def _spawn_threads_for_open_trades(self) -> None:
        """
        Busca pares con 'history_id' ya registrado en monitor_state y arranca/asegura su hilo.
        """
        # Leer estados actuales
        # Nota: si tienes un método para listar monitor_state, úsalo; si no, trae de token_repo + monitor_repo.
        # Aquí asumo que token_repo puede listar pares descubiertos; si tienes otro repo para "open trades", úsalo.
        # Este ejemplo arranca hilo si monitor_state ya tiene history_id no nulo.
        # Implementa un 'list_pairs_with_history()' en monitor_repo si lo prefieres.
        # --- ejemplo genérico ---
        # pairs = self.monitor_repo.list_pairs_with_history()  # si lo implementas
        # for pair in pairs: self.start_thread_for_pair(pair)

        # Si no tienes listados, no hacemos nada aquí; el hilo se arrancará al confirmar/abrir compra.
        pass

    def _digest_actions(self) -> None:
        """
        Revisa acciones en ActionRepository y actúa:
          - 'aprobada' -> lanzar compra confirmada y arrancar hilo
          - 'cancelada' -> limpiar acción y excluir (lo haces en tu pipeline)
        """
        # Si dispones de un 'list_pending()', 'list_all()', etc., úsalo.
        # Aquí ejemplo genérico para todos los pares que tengan acción:
        for pair in self._list_action_pairs_safe():
            estado = self.action_repo.obtener_estado(pair)
            if estado == "aprobada":
                self._handle_authorized(pair)
            elif estado == "cancelada":
                self._handle_canceled(pair)
            # 'pendiente' -> no hacemos nada

    def _list_action_pairs_safe(self) -> list[str]:
        try:
            return self.action_repo.list_pairs()  # o list_pairs('pendiente') si quieres filtrar
        except Exception:
            return []

    # ---------- Transiciones ----------
    def _handle_authorized(self, pair_address: str) -> None:
        """
        Cuando el usuario autoriza la acción 'BUY' para un par:
          - obtenemos plan de compra (amount_bnb_wei)
          - leemos token/tasas de token_repository
          - confirmamos compra con autobuy
          - arrancamos hilo para monitorizar
        """
        # 1) Token + tasas
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

        # 2) Plan de compra
        plan = self.plan_fn(pair_address)
        amount_bnb_wei = int(plan["amount_bnb_wei"])

        # 3) Precios (todo en BNB)
        price_native_bnb = float(token.price_native or 0.0)
        current_price_bnb = price_native_bnb  # si tienes fuente distinta, cámbiala aquí

        # 4) Confirmar compra en autobuy (esto crea history_id y construye tx)
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

        # 5) Registrar/arrancar thread de monitor
        self.start_thread_for_pair(pair_address)

    def _handle_canceled(self, pair_address: str) -> None:
        """
        Acción cancelada -> borrar acción y excluir del pipeline.
        """
        self.action_repo.limpiar(pair_address)
        # si tienes lista de seguimiento, elimínalo allí también
        logger.info(f"Acción cancelada y limpiada para {pair_address}")

    # ---------- Worker de cada par ----------
    def _monitor_worker(self, pair_address: str, stop_evt: threading.Event) -> None:
        """
        Supervisa un trade activo:
          - Obtiene history_id del monitor_repo
          - Actualiza monitor_state (pnl) usando TradeSession y precio actual
          - Ejecuta finalize_sell(...) si toca (tu regla)
        """
        logger.info(f"[{pair_address}] monitor iniciado")
        last_update = 0.0

        while not stop_evt.is_set():
            try:
                # 1) Recuperar history_id
                history_id = self.monitor_repo.get_history_id(pair_address)
                if not history_id:
                    logger.info(f"[{pair_address}] sin history_id; parando hilo.")
                    break

                # 2) Cargar token y session (ajusta a tu modelo real)
                token_row = self.token_repo.get_by_pair(pair_address)
                if not token_row:
                    time.sleep(self.tick_seconds); continue

                # Construye Token / TradeSession según tus modelos
                token = Token.from_row(token_row) if hasattr(Token, "from_row") else Token(
                    pair_address=token_row["pair_address"], name=token_row["name"], symbol=token_row["symbol"],
                    address=token_row["address"], price_native=token_row["price_native"], price_usd=token_row["price_usd"],
                    pair_created_at=token_row["pair_created_at"], image_url=token_row["image_url"], open_graph=token_row["open_graph"]
                )
                # TradeSession: debes tener persistido entry_price y buy_price_with_fees
                session = TradeSession(entry_price=token_row.get("price_native") or 0.0,
                                       buy_price_with_fees=token_row.get("price_native") or 0.0)

                # 3) Precio actual
                price_now = self.market.get_price_native_bnb(pair_address)
                if price_now is not None:
                    token.price_native = price_now

                # 4) Actualizar monitor_state (tu Streamlit usa este repo)
                self.monitor_repo.save_state(token, session)

                # 5) Lógica de auto-sell (coloca aquí tu política real)
                h = self.autobuy.history_repo.get_by_id(self.monitor_repo.get_history_id(pair_address))
                if h and h.get("buy_real_price") is not None and token.price_native:
                    buy_real = float(h["buy_real_price"])        # unitario BNB/token (con fees reales)
                    take_profit = buy_real * 1.05                # +5%
                    if float(token.price_native) >= take_profit:
                        sell_amount_tokens = ...  # define cuánto vendes (100% o un %)
                        prep = self.autosell.prepare_sell(
                            pair_address=pair_address,
                            token_address=token.address,
                            sell_amount_tokens=sell_amount_tokens,
                            slippage_percent=float(os.getenv("DEFAULT_SLIPPAGE", "3.0"))
                        )
                        if prep.get("ok"):
                            # approve si hace falta
                            if prep["approve_tx"] is not None:
                                self.autobuy.w3s.sign_and_send(prep["approve_tx"])
                            # enviar y registrar venta real
                            self.autosell.send_and_record_sell(
                                pair_address=pair_address,
                                token_address=token.address,
                                sell_amount_tokens=sell_amount_tokens,
                                sell_tx=prep["sell_tx"]
                            )
                            break
            except Exception as e:
                logger.exception(f"[{pair_address}] error en worker: {e}")

            # Ritmo del hilo
            stop_evt.wait(self.tick_seconds)

        logger.info(f"[{pair_address}] monitor detenido")
