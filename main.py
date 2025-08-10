# main.py
from __future__ import annotations
import os
import sys
import time
import signal
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any

# ---- carga .env si existe (opcional) ----
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

# ---- imports del proyecto ----
from orchestrators.monitor_orchestrator import MonitorOrchestrator
from services.telegram_bot import TelegramBot
from utils.log_config import logger_manager

logger = logger_manager.setup_logger(__name__)

# ------------------------------
# Configuración
# ------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv("DB_PATH", str(PROJECT_ROOT / "memecoins.db"))
STREAMLIT_APP = os.getenv("STREAMLIT_APP", str(PROJECT_ROOT / "streamlit_app" / "dashboard.py"))
STREAMLIT_PORT = os.getenv("STREAMLIT_PORT", "8501")

# Plan de compra por defecto (puedes afinarlo por ENV)
DEFAULT_BUY_BNB = float(os.getenv("DEFAULT_BUY_BNB", "0.02"))  # 0.02 BNB
def plan_fn(pair_address: str) -> Dict[str, Any]:
    """Devuelve el plan de compra para un par. Puedes sofisticarlo después."""
    return {"amount_bnb_wei": int(DEFAULT_BUY_BNB * 1e18)}

# ------------------------------
# Lanzadores
# ------------------------------
def start_orchestrator(stop_event: threading.Event):
    """
    Arranca el orquestador en un hilo.
    Usa stop_event únicamente para esperar cierre coordinado (el propio orquestador tiene su .stop()).
    """
    orch = MonitorOrchestrator(db_path=DB_PATH, plan_fn=plan_fn)
    # guardamos referencia para poder pararlo desde el manejador de señales
    start_orchestrator.instance = orch  # type: ignore[attr-defined]
    orch.start()
    # esperar hasta que nos pidan parar
    while not stop_event.is_set():
        time.sleep(0.5)
    # parada suave
    try:
        orch.stop()
    except Exception as e:
        logger.error(f"Error al parar orquestador: {e}")

def start_telegram_bot(stop_event: threading.Event):
    """
    Arranca el bot de Telegram en un hilo.
    Internamente, TelegramBot.start() bloquea con idle(); al apagar, forzamos .updater.stop()
    """
    try:
        bot = TelegramBot()
    except Exception as e:
        logger.error(f"No se pudo iniciar TelegramBot: {e}")
        return
    start_telegram_bot.instance = bot  # type: ignore[attr-defined]
    # lo lanzamos en un hilo aparte para poder detener el proceso principal con señales
    def _run():
        try:
            bot.start()
        except Exception as e:
            logger.error(f"Fallo en TelegramBot: {e}")
    t = threading.Thread(target=_run, name="TelegramBot", daemon=True)
    t.start()
    # esperar señal de parada
    while not stop_event.is_set():
        time.sleep(0.5)
    # parada suave
    try:
        # el bot expone updater; podemos parar el polling
        if hasattr(bot, "updater"):
            bot.updater.stop()
    except Exception as e:
        logger.error(f"Error al parar TelegramBot: {e}")

def start_streamlit_process() -> subprocess.Popen:
    """
    Lanza streamlit como proceso aparte.
    """
    app_path = Path(STREAMLIT_APP)
    if not app_path.exists():
        logger.error(f"Streamlit app no encontrada: {app_path}")
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless=true",
        f"--server.port={STREAMLIT_PORT}",
        # Puedes fijar el directorio raíz si lo necesitas:
        # f"--server.fileWatcherType=none"
    ]
    logger.info(f"Lanzando Streamlit: {' '.join(cmd)}")
    # heredamos entorno (DB_PATH etc.)
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    return proc

# ------------------------------
# Señales / apagado limpio
# ------------------------------
stop_all_evt = threading.Event()
streamlit_proc: subprocess.Popen | None = None

def shutdown(*_):
    logger.info("🛑 Señal de apagado recibida, deteniendo servicios...")
    stop_all_evt.set()
    # parar streamlit
    global streamlit_proc
    if streamlit_proc and streamlit_proc.poll() is None:
        try:
            # intento de cierre suave
            if os.name == "nt":
                streamlit_proc.terminate()
            else:
                streamlit_proc.send_signal(signal.SIGTERM)
            # timeout corto
            for _ in range(10):
                if streamlit_proc.poll() is not None:
                    break
                time.sleep(0.3)
            if streamlit_proc.poll() is None:
                streamlit_proc.kill()
        except Exception as e:
            logger.error(f"No se pudo cerrar Streamlit: {e}")
    logger.info("✅ Apagado completado.")

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ------------------------------
# Main
# ------------------------------
if __name__ == "__main__":
    logger.info("🚀 Iniciando backend (orquestador + bot) y Streamlit...")

    # 1) Orquestador
    orch_thread = threading.Thread(target=start_orchestrator, args=(stop_all_evt,), name="Orchestrator", daemon=True)
    orch_thread.start()

    # 2) Telegram Bot
    bot_thread = threading.Thread(target=start_telegram_bot, args=(stop_all_evt,), name="Telegram", daemon=True)
    bot_thread.start()

    # 3) Streamlit (proceso)
    streamlit_proc = start_streamlit_process()

    # 4) Espera bloqueante hasta que streamlit termine o llegue señal
    try:
        while not stop_all_evt.is_set():
            # si streamlit muere solo, paramos todo
            if streamlit_proc and streamlit_proc.poll() is not None:
                logger.warning("El proceso de Streamlit finalizó. Cerrando servicios...")
                stop_all_evt.set()
                break
            time.sleep(0.5)
    finally:
        shutdown()
        # dar un poco de tiempo a los hilos a cerrarse bien
        time.sleep(0.8)
