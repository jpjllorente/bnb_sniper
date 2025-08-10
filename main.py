# ---------- VALIDACIÓN DE ENTORNO (PEGAR ARRIBA EN main.py) ----------
from __future__ import annotations
import os, sys, re, requests
from utils.log_config import logger_manager

vlog = logger_manager.setup_logger("env_validator")

# Obligatorias sí o sí para operar en real
REQUIRED_ENV = [
    "DB_PATH",
    "RPC_URL",
    "WALLET_ADDRESS",
    "PRIVATE_KEY",
    "ROUTER_ADDRESS",
    "WBNB_ADDRESS",
    "CHAIN_ID",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
]

# Opcionales pero recomendadas (las validamos si están presentes)
OPTIONAL_ENV_FLOATS_MIN0 = [
    "DEFAULT_BUY_BNB",
    "DEFAULT_SLIPPAGE",
    "TAKE_PROFIT_PCT",
    "TRAILING_GAP_PCT",
    "STOP_LOSS_PCT",
    "PNL_THRESOLD_PERCENT",
    "MAX_FEE_BNB",
    "SELL_PERCENT_1",
    "SELL_PERCENT_2",
    "MIN_SELL_TOKENS",
    "MIN_SELL_VALUE_BNB",
    "DISCOVERY_INTERVAL_SEC",
    "MIN_LIQUIDITY_BNB",
    "MAX_BUY_TAX_PCT",
    "MAX_SELL_TAX_PCT",
    "MAX_TRANSFER_TAX",
]
OPTIONAL_ENV_INTS_MIN0 = [
    "GAS_PRICE_WEI",
    "MIN_AGE_MIN",
]
OPTIONAL_ENV_BOOLS = [
    "DRY_RUN",
    "LOG_TELEGRAM_ERRORS",
]

_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_PRIV_RE = re.compile(r"^(0x)?[a-fA-F0-9]{64}$")

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default if default is not None else None)
    return v.strip() if isinstance(v, str) else v

def _boolish(val: str | None) -> bool | None:
    if val is None: return None
    s = val.lower()
    if s in ("1","true","yes","y","on"): return True
    if s in ("0","false","no","n","off"): return False
    return None

def _check_addr(name: str, val: str | None, errs: list[str]) -> None:
    if not val or not _ADDR_RE.match(val):
        errs.append(f"{name} debe ser dirección EVM válida (0x + 40 hex). Valor='{val}'")

def _check_priv(name: str, val: str | None, errs: list[str]) -> None:
    if not val or not _PRIV_RE.match(val):
        preview = (val[:6] + "…" + val[-4:]) if val and len(val) > 12 else str(val)
        errs.append(f"{name} debe ser clave privada hex de 64 chars (con o sin 0x). Valor='{preview}'")

def _check_float_min0(name: str, val: str | None, errs: list[str]) -> None:
    if val is None or val == "": return
    try:
        x = float(val)
        if x < 0.0:
            errs.append(f"{name} debe ser >= 0. Valor='{val}'")
    except Exception:
        errs.append(f"{name} debe ser numérico. Valor='{val}'")

def _check_int_min0(name: str, val: str | None, errs: list[str]) -> None:
    if val is None or val == "": return
    try:
        x = int(val)
        if x < 0:
            errs.append(f"{name} debe ser entero >= 0. Valor='{val}'")
    except Exception:
        errs.append(f"{name} debe ser entero. Valor='{val}'")

def _rpc_chain_id(rpc_url: str, timeout: float = 6.0) -> int | None:
    try:
        r = requests.post(
            rpc_url,
            json={"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]},
            timeout=timeout
        )
        r.raise_for_status()
        res = r.json().get("result")
        if isinstance(res, str) and res.startswith("0x"):
            return int(res, 16)
        if isinstance(res, int):
            return res
        return None
    except Exception as e:
        vlog.error(f"RPC check falló: {e}")
        return None

def validate_env_or_die() -> None:
    errs: list[str] = []

    # 1) Faltantes hard
    for name in REQUIRED_ENV:
        if not _env(name):
            errs.append(f"Falta variable obligatoria: {name}")

    # 2) Formatos duros
    _check_addr("WALLET_ADDRESS", _env("WALLET_ADDRESS"), errs)
    _check_addr("ROUTER_ADDRESS", _env("ROUTER_ADDRESS"), errs)
    _check_addr("WBNB_ADDRESS", _env("WBNB_ADDRESS"), errs)
    _check_priv("PRIVATE_KEY", _env("PRIVATE_KEY"), errs)

    # 3) CHAIN_ID entero > 0
    try:
        cid = int(_env("CHAIN_ID","0") or "0")
        if cid <= 0: errs.append("CHAIN_ID debe ser entero > 0.")
    except Exception:
        errs.append(f"CHAIN_ID debe ser entero. Valor='{_env('CHAIN_ID')}'")

    # 4) Floats e ints opcionales
    for name in OPTIONAL_ENV_FLOATS_MIN0:
        _check_float_min0(name, _env(name), errs)
    for name in OPTIONAL_ENV_INTS_MIN0:
        _check_int_min0(name, _env(name), errs)

    # 5) Booleans opcionales
    for name in OPTIONAL_ENV_BOOLS:
        b = _boolish(_env(name))
        if b is None and _env(name) is not None:
            errs.append(f"{name} debe ser booleano (true/false). Valor='{_env(name)}'")

    # 6) Ping RPC + verificación de CHAIN_ID
    rpc = _env("RPC_URL")
    want_cid = None
    try:
        want_cid = int(_env("CHAIN_ID","0") or "0")
    except Exception:
        pass
    got_cid = _rpc_chain_id(rpc) if rpc else None
    if got_cid is None:
        errs.append(f"No se pudo consultar eth_chainId en RPC_URL='{rpc}'")
    elif want_cid and got_cid != want_cid:
        errs.append(f"CHAIN_ID no coincide: RPC={got_cid} vs .env={want_cid} (RPC_URL='{rpc}')")

    # 7) Salida dura si hay errores
    if errs:
        vlog.error("❌ Validación de entorno FALLIDA. Corrige:")
        for e in errs:
            vlog.error(" - " + e)
        sys.exit(1)

    # 8) Información útil
    pk = _env("PRIVATE_KEY") or ""
    masked_pk = (pk[:6] + "…" + pk[-4:]) if len(pk) > 12 else pk
    vlog.info("✅ Entorno validado.")
    vlog.info(f"DB_PATH={_env('DB_PATH')} | RPC_URL={_env('RPC_URL')} | CHAIN_ID={_env('CHAIN_ID')}")
    vlog.info(f"WALLET_ADDRESS={_env('WALLET_ADDRESS')} | PRIVATE_KEY={masked_pk}")
    vlog.info(f"ROUTER_ADDRESS={_env('ROUTER_ADDRESS')} | WBNB_ADDRESS={_env('WBNB_ADDRESS')}")
    vlog.info(f"TELEGRAM_CHAT_ID={_env('TELEGRAM_CHAT_ID')}")
    # extras (si están definidos)
    if _env("GAS_PRICE_WEI") not in (None, "", "0"):
        vlog.info(f"GAS_PRICE_WEI={_env('GAS_PRICE_WEI')}")
    if _env("DRY_RUN"):
        vlog.info(f"DRY_RUN={_env('DRY_RUN')}")
    if _env("LOG_TELEGRAM_ERRORS"):
        vlog.info(f"LOG_TELEGRAM_ERRORS={_env('LOG_TELEGRAM_ERRORS')}")
# ---------- FIN VALIDACIÓN DE ENTORNO ----------

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
    disc = DiscoveryOrchestrator()
    start_discovery.instance = disc  # type: ignore[attr-defined]
    disc.start()
    while not stop_event.is_set():
        time.sleep(0.5)
    try:
        disc.stop()
    except Exception as e:
        logger.error(f"Error al parar DiscoveryOrchestrator: {e}")


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
    validate_env_or_die()   # <<<<<< IMPORTANTE
    logger.info("✅ Entorno OK. Lanzando servicios…")
    
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
        
