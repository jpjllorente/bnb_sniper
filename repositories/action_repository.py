import sqlite3, os
from pathlib import Path
from utils.log_config import log_function

def _resolve_db_path() -> str:
    env_path = os.getenv("DB_PATH")
    if env_path:
        return str(Path(env_path).expanduser().resolve())
    root = Path(__file__).resolve().parents[1]
    default = root / "data" / "memecoins.db"
    default.parent.mkdir(parents=True, exist_ok=True)
    return str(default)

DB_PATH = _resolve_db_path()

class ActionRepository:
    def __init__(self, db_path: str | None = None):
        self.db_path = str(Path(db_path).expanduser().resolve()) if db_path else DB_PATH
        self._create_table()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_table(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acciones(
                    pair_address TEXT PRIMARY KEY,
                    tipo        TEXT,
                    estado      TEXT,
                    timestamp   INTEGER
                )
            """)
            # añadir notified_at si no existe
            cols = {r[1] for r in conn.execute("PRAGMA table_info(acciones)").fetchall()}
            if "notified_at" not in cols:
                conn.execute("ALTER TABLE acciones ADD COLUMN notified_at INTEGER")
            conn.commit()

    @log_function
    def registrar_accion(self, pair_address: str, tipo: str):
        with self._connect() as conn:
            # nueva pendiente => limpiar notified_at para que se notifique
            conn.execute("""
                INSERT INTO acciones (pair_address, tipo, estado, timestamp, notified_at)
                VALUES (?, ?, 'pendiente', strftime('%s','now'), NULL)
                ON CONFLICT(pair_address) DO UPDATE SET
                    tipo=excluded.tipo,
                    estado='pendiente',
                    timestamp=strftime('%s','now'),
                    notified_at=NULL
            """, (pair_address, tipo))
            conn.commit()

    @log_function
    def autorizar_accion(self, pair_address: str):
        with self._connect() as conn:
            conn.execute('UPDATE acciones SET estado="aprobada" WHERE pair_address=?', (pair_address,))
            conn.commit()

    @log_function
    def cancelar_accion(self, pair_address: str):
        with self._connect() as conn:
            conn.execute('UPDATE acciones SET estado="cancelada" WHERE pair_address=?', (pair_address,))
            conn.commit()

    @log_function
    def obtener_estado(self, pair_address: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute('SELECT estado FROM acciones WHERE pair_address=?', (pair_address,)).fetchone()
            return row[0] if row else None

    @log_function
    def obtener_tipo(self, pair_address: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute('SELECT tipo FROM acciones WHERE pair_address=?', (pair_address,)).fetchone()
            return row[0] if row else None

    @log_function
    def limpiar(self, pair_address: str):
        with self._connect() as conn:
            conn.execute('DELETE FROM acciones WHERE pair_address=?', (pair_address,))
            conn.commit()

    @log_function
    def list_all(self, estado: str | None = None, limit: int = 50) -> list[dict]:
        q = "SELECT pair_address,tipo,estado,timestamp,notified_at FROM acciones"
        p: list = []
        if estado:
            q += " WHERE estado=?"
            p.append(estado)
        q += " ORDER BY timestamp DESC LIMIT ?"
        p.append(limit)
        with self._connect() as conn:
            cur = conn.execute(q, tuple(p))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    @log_function
    def list_pending_not_notified(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT pair_address, tipo, timestamp
                FROM acciones
                WHERE estado='pendiente' AND (notified_at IS NULL)
                ORDER BY timestamp ASC
                LIMIT ?
            """, (limit,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    @log_function
    def marcar_notificado(self, pair_address: str):
        with self._connect() as conn:
            conn.execute("UPDATE acciones SET notified_at=strftime('%s','now') WHERE pair_address=?", (pair_address,))
            conn.commit()
