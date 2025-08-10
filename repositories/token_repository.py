"""
TokenRepository para BNB Sniper (SQLite).
Mantiene tokens descubiertos y sus tasas (GoPlus).
"""

from __future__ import annotations
from typing import Optional
import sqlite3
import os

from models.token import Token
from utils.log_config import log_function
from enums.token_status import TokenStatus

# Usa DB_PATH del entorno si existe; si no, fallback a ./data/memecoins.db
DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "../../data/memecoins.db")
)

class TokenRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_table(self):
        conn = self._connect()
        conn.execute('''CREATE TABLE IF NOT EXISTS discovered_tokens (
            pair_address     TEXT PRIMARY KEY,
            name             TEXT,
            symbol           TEXT,
            address          TEXT,
            price_native     REAL,
            price_usd        REAL,
            pair_created_at  INTEGER,
            liquidity        REAL,
            volume           REAL,
            buys             INTEGER,
            image_url        TEXT,
            open_graph       TEXT,
            buy_tax          REAL DEFAULT 0.0,
            sell_tax         REAL DEFAULT 0.0,
            transfer_tax     REAL DEFAULT 0.0,
            status           TEXT DEFAULT '',
            timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP
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
        """
        Inserta/actualiza un token descubierto.
        NOTA: no incluimos 'timestamp' en el INSERT; deja que SQLite use su DEFAULT.
        """
        conn = self._connect()
        conn.execute(
            '''
            INSERT OR REPLACE INTO discovered_tokens (
                pair_address,
                name,
                symbol,
                address,
                price_native,
                price_usd,
                pair_created_at,
                liquidity,
                volume,
                buys,
                image_url,
                open_graph
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                token.pair_address,
                token.name,
                token.symbol,
                token.address,
                float(token.price_native) if token.price_native is not None else None,
                float(getattr(token, "price_usd", None)) if getattr(token, "price_usd", None) is not None else None,
                int(token.pair_created_at) if token.pair_created_at is not None else None,
                float(token.liquidity) if token.liquidity is not None else None,
                float(token.volume) if token.volume is not None else None,
                int(token.buys) if token.buys is not None else 0,
                token.image_url,
                token.open_graph
            )
        )
        conn.commit()
        conn.close()

    @log_function
    def update_status(self, token: Token, status: TokenStatus) -> None:
        conn = self._connect()
        conn.execute(
            '''
            UPDATE discovered_tokens
               SET status = ?
             WHERE pair_address = ?
            ''',
            (status.value, token.pair_address)
        )
        conn.commit()
        conn.close()

    @log_function
    def update_taxes(self, token: Token) -> None:
        """
        Actualiza tasas almacenadas desde GoPlus (buy/sell/transfer).
        """
        conn = self._connect()
        conn.execute(
            '''
            UPDATE discovered_tokens SET
                buy_tax = ?,
                sell_tax = ?,
                transfer_tax = ?
            WHERE pair_address = ?
            ''',
            (
                float(token.buy_tax or 0.0),
                float(token.sell_tax or 0.0),
                float(token.transfer_tax or 0.0),
                token.pair_address
            )
        )
        conn.commit()
        conn.close()

    # --- utilidades opcionales que ayudan al pipeline ---

    @log_function
    def get_by_pair(self, pair_address: str) -> Optional[dict]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM discovered_tokens WHERE pair_address = ?", (pair_address,))
        row = cur.fetchone()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        if not row:
            return None
        return {k: v for k, v in zip(cols, row)}

    @log_function
    def get_taxes(self, pair_address: str) -> tuple[float, float, float]:
        """
        Devuelve (buy_tax, sell_tax, transfer_tax) para el par.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT buy_tax, sell_tax, transfer_tax FROM discovered_tokens WHERE pair_address = ?",
            (pair_address,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return (0.0, 0.0, 0.0)
        return (float(row[0] or 0.0), float(row[1] or 0.0), float(row[2] or 0.0))
