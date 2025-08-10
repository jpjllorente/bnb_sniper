# orchestrators/discovery_orchestrator.py
from __future__ import annotations
import os, time, threading
from typing import Optional

from controllers.discovery_controller import DiscoveryController
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

class DiscoveryOrchestrator:
    """
    Hilo de descubrimiento periódico: llama a DiscoveryController.procesar_tokens_descubiertos()
    cada DISCOVERY_INTERVAL_SEC (por defecto 10s).
    """
    def __init__(self, interval_sec: Optional[float] = None) -> None:
        self.interval = float(interval_sec or os.getenv("DISCOVERY_INTERVAL_SEC", "10"))
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.controller = DiscoveryController()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run_loop, name="Discovery", daemon=True)
        self._thread.start()
        logger.info(f"DiscoveryOrchestrator iniciado (intervalo={self.interval}s).")

    def stop(self) -> None:
        self._stop_evt.set()
        logger.info("DiscoveryOrchestrator: parada solicitada.")

    @log_function
    def _run_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                logger.debug("[discovery] tick → procesar_tokens_descubiertos()")
                self.controller.procesar_tokens_descubiertos()
            except Exception as e:
                logger.exception(f"DiscoveryOrchestrator error: {e}")
            self._stop_evt.wait(self.interval)
