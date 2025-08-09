import sqlite3
import os
from models.history import History
from utils.log_config import log_function

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class HystoryRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_table(self):
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS hystory (
                    pair_address TEXT PRIMARY KEY,
                    token_address TEXT,
                    symbol TEXT,
                    name TEXT,
                    buy_entry_price REAL,
                    buy_price_with_fees REAL,
                    buy_real_price REAL,
                    buy_amount REAL,
                    buy_date INTEGER,
                    sell_entry_price REAL DEFAULT 0.0,
                    sell_price_with_fees REAL DEFAULT 0.0,
                    sell_real_price REAL DEFAULT 0.0,
                    sell_date INTEGER DEFAULT 0,
                    sell_amount REAL DEFAULT 0.0,
                    pnl REAL DEFAULT 0.0,
                    bnb_amount REAL DEFAULT 0.0
                )
            ''')
            conn.commit()

    def save(self, history: History):
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO history (
                    pair_address, token_address, symbol, name, buy_entry_price,
                    buy_price_with_fees, buy_real_price, buy_amount, buy_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                history.pair_address,
                history.token_address,
                history.symbol,
                history.name,
                history.buy_entry_price,
                history.buy_price_with_fees,
                history.buy_real_price,
                history.buy_amount,
                history.buy_date
            ))
            conn.commit()
            
    def update_finished(self, history: History):
        with self._connect() as conn:
            conn.execute('''
                UPDATE history SET (
                    sell_entry_price, sell_price_with_fees, sell_real_price,
                    sell_date, sell_amount, pnl, bnb_amount
                ) = (?, ?, ?, ?, ?, ?, ?)
                WHERE pair_address = ?
            ''', (
                history.sell_entry_price,
                history.sell_price_with_fees,
                history.sell_real_price,
                history.sell_date,
                history.sell_amount,
                history.pnl,
                history.bnb_amount,
                history.pair_address
            ))
            conn.commit()