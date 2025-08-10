# repositories/monitor_repository.py
import sqlite3
import os
from models.token import Token
from models.trade_session import TradeSession
from utils.log_config import log_function

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class MonitorRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_table()
        self._ensure_history_id_column()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_table(self):
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS monitor_state (
                    pair_address TEXT PRIMARY KEY,
                    symbol TEXT,
                    price REAL,
                    entry_price REAL,
                    buy_price_with_fees REAL,
                    pnl REAL,
                    updated_at INTEGER
                )
            ''')
            conn.commit()

    def _ensure_history_id_column(self):
        with self._connect() as conn:
            cur = conn.execute("PRAGMA table_info(monitor_state)")
            cols = {r[1] for r in cur.fetchall()}
            if "history_id" not in cols:
                conn.execute("ALTER TABLE monitor_state ADD COLUMN history_id INTEGER")
                conn.commit()

    @log_function
    def save_state(self, token: Token, session: TradeSession):
        """Actualiza fila del par con PnL basado en la sesión (todo en BNB)."""
        pnl = None
        if session.buy_price_with_fees and token.price_native:
            try:
                pnl = ((token.price_native - session.buy_price_with_fees) / session.buy_price_with_fees) * 100.0
            except ZeroDivisionError:
                pnl = None

        with self._connect() as conn:
            conn.execute('''
                INSERT INTO monitor_state (
                    pair_address, symbol, price, entry_price, buy_price_with_fees, pnl, updated_at, history_id
                ) VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'),
                    COALESCE((SELECT history_id FROM monitor_state WHERE pair_address = ?), NULL)
                )
                ON CONFLICT(pair_address) DO UPDATE SET
                    symbol = excluded.symbol,
                    price  = excluded.price,
                    entry_price = excluded.entry_price,
                    buy_price_with_fees = excluded.buy_price_with_fees,
                    pnl = excluded.pnl,
                    updated_at = excluded.updated_at
            ''', (
                token.pair_address,
                token.symbol,
                token.price_native,
                session.entry_price,
                session.buy_price_with_fees,
                pnl,
                token.pair_address
            ))
            conn.commit()

    # Vinculación con history
    @log_function
    def set_history_id(self, pair_address: str, history_id: int) -> None:
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO monitor_state (pair_address, history_id, updated_at)
                VALUES (?, ?, strftime('%s','now'))
                ON CONFLICT(pair_address) DO UPDATE SET history_id = excluded.history_id
            ''', (pair_address, history_id))
            conn.commit()

    @log_function
    def get_history_id(self, pair_address: str) -> int | None:
        with self._connect() as conn:
            cur = conn.execute("SELECT history_id FROM monitor_state WHERE pair_address = ?", (pair_address,))
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None

    @log_function
    def clear_history_id(self, pair_address: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE monitor_state SET history_id = NULL WHERE pair_address = ?", (pair_address,))
            conn.commit()

    # Listado para Telegram/Streamlit
    @log_function
    def list_monitored(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT pair_address, symbol, price, entry_price, buy_price_with_fees, pnl, updated_at, history_id
                FROM monitor_state
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
