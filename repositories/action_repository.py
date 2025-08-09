# repositories/action_repository.py (añadidos opcionales)
import sqlite3
import os
from utils.log_config import log_function

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class ActionRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS acciones (
                    pair_address TEXT PRIMARY KEY,
                    tipo TEXT,
                    estado TEXT,
                    timestamp INTEGER
                )
            ''')
            conn.commit()

    @log_function
    def registrar_accion(self, pair_address: str, tipo: str):
        with self._connect() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO acciones (
                    pair_address, tipo, estado, timestamp
                ) VALUES (?, ?, 'pendiente', strftime('%s', 'now'))
            ''', (pair_address, tipo))
            conn.commit()

    @log_function
    def autorizar_accion(self, pair_address: str):
        with self._connect() as conn:
            conn.execute('''
                UPDATE acciones
                SET estado = 'aprobada'
                WHERE pair_address = ?
            ''', (pair_address,))
            conn.commit()

    @log_function
    def cancelar_accion(self, pair_address: str):
        with self._connect() as conn:
            conn.execute('''
                UPDATE acciones
                SET estado = 'cancelada'
                WHERE pair_address = ?
            ''', (pair_address,))
            conn.commit()

    @log_function
    def obtener_estado(self, pair_address: str) -> str | None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute('SELECT estado FROM acciones WHERE pair_address = ?', (pair_address,))
            row = cur.fetchone()
            return row[0] if row else None

    # opcionales
    @log_function
    def limpiar(self, pair_address: str):
        with self._connect() as conn:
            conn.execute('DELETE FROM acciones WHERE pair_address = ?', (pair_address,))
            conn.commit()

    @log_function
    def obtener_tipo(self, pair_address: str) -> str | None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute('SELECT tipo FROM acciones WHERE pair_address = ?', (pair_address,))
            row = cur.fetchone()
            return row[0] if row else None
        
    @log_function
    def list_pairs(self, estado: str | None = None) -> list[str]:
        q = "SELECT pair_address FROM acciones"
        params = ()
        if estado:
            q += " WHERE estado = ?"
            params = (estado,)
        with self._connect() as conn:
            cur = conn.execute(q, params)
            return [r[0] for r in cur.fetchall()]
