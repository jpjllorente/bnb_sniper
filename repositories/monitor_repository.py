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
                    pnl REAL,
                    updated_at INTEGER
                )
            ''')
            conn.commit()

    def save_state(self, token: Token, session: TradeSession):
        pnl = ((token.price_native - session.entry_price) / session.entry_price) * 100
        with self._connect() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO monitor_state (
                    pair_address, symbol, price, entry_price, pnl, updated_at
                ) VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
            ''', (
                token.pair_address,
                token.symbol,
                token.price_native,
                session.entry_price,
                pnl
            ))
            conn.commit()