# diagnostics.py
import os, time
from utils.log_config import logger_manager
from repositories.token_repository import TokenRepository
from repositories.action_repository import ActionRepository
from repositories.monitor_repository import MonitorRepository
from repositories.history_repository import HistoryRepository

logger = logger_manager.setup_logger("diagnostics")

DB_PATH = os.getenv("DB_PATH") or "./memecoins.db"
tok = TokenRepository(db_path=DB_PATH)
act = ActionRepository(db_path=DB_PATH)
mon = MonitorRepository(db_path=DB_PATH)
his = HistoryRepository(db_path=DB_PATH)

def ok(b, msg): print(("✅" if b else "❌"), msg)

print("== DIAGNÓSTICO BNB SNIPER ==")
ok(True, f"DB_PATH: {DB_PATH}")

# Tablas básicas (simplemente intentamos listados)
try:
    _ = tok.exists("dummy"); ok(True, "TokenRepository OK")
except Exception as e:
    ok(False, f"TokenRepository fallo: {e}")

try:
    _ = act.list_all(limit=1); ok(True, "ActionRepository OK")
except Exception as e:
    ok(False, f"ActionRepository fallo: {e}")

try:
    _ = mon.list_monitored(limit=1); ok(True, "MonitorRepository OK")
except Exception as e:
    ok(False, f"MonitorRepository fallo: {e}")

try:
    _ = his.list_recent(limit=1); ok(True, "HistoryRepository OK")
except Exception as e:
    ok(False, f"HistoryRepository fallo: {e}")

# Acciones pendientes visibles
rows = act.list_all(estado="pendiente", limit=5)
print(f"Acciones pendientes (top 5): {rows}")

# Monitor latente
rows_m = mon.list_monitored(limit=5)
print(f"Monitor rows (top 5): {rows_m}")

print("== FIN ==")
