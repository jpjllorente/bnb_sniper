"""
In‑memory token repository for bsc_sniper.

In the initial skeleton this repository simply holds tokens in memory. In a
real implementation it would persist data to a database or file, such as
SQLite, PostgreSQL or JSON files, depending on the configuration.
"""

from __future__ import annotations

from typing import List

import sqlite3
import os
from models.token import Token
from utils.log_config import log_function

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class TokenRepository:
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)
    
    def _ensure_table(self):
        conn = self._connect()
        conn.execute('''CREATE TABLE IF NOT EXISTS discovered_tokens (
            pair_address TEXT PRIMARY KEY,
            name TEXT,
            symbol TEXT,
            price_native REAL,
            price_usd REAL,
            pair_created_at INTEGER,
            image_url TEXT,
            open_graph TEXT
        )''')
        conn.commit()
        conn.close()
        
    @log_function
    def exists(self, pair_address: str) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM discovered_tokens WHERE pair_address = ?", (pair_address,))
        result = cur.fetchone()
        conn.close()
        return result is not None
    
    @log_function
    def save(self, token: Token) -> None:
        conn = self._connect()
        conn.execute('''INSERT OR REPLACE INTO discovered_tokens 
            (pair_address, name, symbol, price_native, price_usd, pair_created_at, image_url, open_graph)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                token.pair_address,
                token.name,
                token.symbol,
                token.price_native,
                token.price_usd,
                token.pair_created_at,
                token.image_url,
                token.open_graph
            )
        )
        conn.commit()
        conn.close()