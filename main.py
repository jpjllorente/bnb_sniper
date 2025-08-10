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
from orchestrators.discovery_orchestrator import DiscoveryOrchestrator

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
    Arranca el bot v20+ en un hilo secundario *creando la Application y el loop en ese hilo*.
    Desactiva signal handlers (solo válidos en el hilo principal).
    """
    start_telegram_bot.instance = None  # será asignado dentro del hilo

    def _run():
        import asyncio, platform
        # Policy compatible con hilos en Windows
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 👇 construir el bot (y la Application) *dentro del hilo con loop activo*
            from services.telegram_bot import TelegramBot
            bot = TelegramBot()
            start_telegram_bot.instance = bot  # para poder pararlo desde fuera

            # run_polling en este hilo, sin instalar signal handlers
            bot.application.run_polling(stop_signals=None, close_loop=False)
        except Exception as e:
            logger.error(f"Fallo en TelegramBot: {e}")
        finally:
            try:
                loop.stop()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_run, name="Telegram", daemon=True)
    t.start()

    # Esperar solicitud de parada global
    while not stop_event.is_set():
        time.sleep(0.5)

    # Parada suave del bot cuando exista la instancia
    try:
        for _ in range(50):  # esperar hasta 5s a que se cree la instancia
            bot = getattr(start_telegram_bot, "instance", None)
            if bot is not None:
                break
            time.sleep(0.1)
        if bot is not None:
            bot.stop_running()  # hace que run_polling() termine
    except Exception as e:
        logger.error(f"Error al parar TelegramBot: {e}")

def start_discovery(stop_event: threading.Event):
    """
    Hilo de descubrimiento periódico (Dexscreener + GoPlus).
    Crea acciones 'compra' y las autoriza si están dentro de parámetros,
    o deja 'pendiente' y notifica por Telegram si no lo están.
    """
    disc = DiscoveryOrchestrator(db_path=DB_PATH)
    start_discovery.instance = disc  # type: ignore[attr-defined]
    disc.start()
    while not stop_event.is_set():
        time.sleep(0.5)
    try:
        disc.stop()
    except Exception as e:
        logger.error(f"Error al parar Discovery: {e}")

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

    # 3) Discovery
    disc_thread = threading.Thread(target=start_discovery, args=(stop_all_evt,), name="Discovery", daemon=True)
    disc_thread.start()

    # 4) Streamlit (proceso)
    streamlit_proc = start_streamlit_process()

    # 5) Espera bloqueante hasta que streamlit termine o llegue señal
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
        
