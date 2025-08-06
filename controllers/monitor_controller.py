"""
Controller for monitoring tokens after purchase.

This controller would normally spawn threads or asynchronous tasks to watch
price movements, liquidity, and other metrics, and trigger sales when
conditions are met. In this skeleton it provides a no‑op implementation.
"""

from __future__ import annotations

import threading
import time
from models.token import Token
from models.trade_session import TradeSession
from repositories.monitor_repository import MonitorRepository
from controllers.autosell_controller import AutosellController
from utils.logger import log_function


class MonitorController:
    """Monitor the state of open positions."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self.repo = MonitorRepository()
        self.autosell_controller = AutosellController(dry_run=dry_run)
        self.active_threads: dict[str, threading.Thread] = {}

    @log_function
    def lanzar_monitor(self, token: Token, entry_price: float) -> None:
        if token.pair_address in self.active_threads:
            return

        session = TradeSession(token_address=token.pair_address, entry_price=entry_price)

        thread = threading.Thread(target=self._ejecutar_monitor, args=(token, session))
        thread.daemon = True
        thread.start()

        self.active_threads[token.pair_address] = thread
        
    def _ejecutar_monitor(self, token: Token, session: TradeSession):
        while True:
            time.sleep(15)
            self.repo.save_state(token, session)
            self.autosell_controller.procesar_venta(token, session)
            break
