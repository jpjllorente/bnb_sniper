# repositories/history_repository.py
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class HistoryRepository:
    """
    Solo persistencia de ciclos compra-venta.
    NO gestiona estado (eso vive en repository_token).
    NO modifica rutas: el llamador proporciona db_path existente.
    """
    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- Identificación del activo/par
                    pair_address         TEXT    NOT NULL,
                    token_address        TEXT    NOT NULL,
                    symbol               TEXT,
                    name                 TEXT,

                    -- Compra
                    buy_entry_price      REAL,     -- price_native al iniciar compra
                    buy_price_with_fees  REAL,     -- price_native + gas + buy_fee + transfer_fee (estimado)
                    buy_real_price       REAL,     -- (precio total / buy_amount) tras TX
                    buy_amount           REAL,     -- unidades reales compradas
                    buy_date             INTEGER,  -- timestamp (segundos)

                    -- Venta
                    sell_entry_price     REAL,     -- price_native al iniciar venta
                    sell_price_with_fees REAL,     -- price_native + gas + sell_fee + transfer_fee (estimado)
                    sell_real_price      REAL,     -- (precio total / sell_amount) tras TX
                    sell_amount          REAL,     -- unidades reales vendidas

                    -- Resultados
                    pnl                  REAL,     -- (((sell_real_price - buy_real_price)/buy_real_price)*sell_amount * 100)
                    bnb_amount           REAL      -- beneficios en BNB
                );
            """)
            # Índices útiles; no cambian tu lógica de estado
            c.execute("CREATE INDEX IF NOT EXISTS idx_history_pair  ON history(pair_address);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_history_token ON history(token_address);")

    # ---------- CRUD específico de tus fases ----------
    def create_buy(self,
                   pair_address: str,
                   token_address: str,
                   symbol: Optional[str],
                   name: Optional[str],
                   buy_entry_price: Optional[float],
                   buy_price_with_fees: Optional[float],
                   buy_date_ts: int) -> int:
        """
        Inserta al iniciar la compra (no conocemos aún buy_real_price/buy_amount).
        Devuelve history_id.
        """
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO history (
                    pair_address, token_address, symbol, name,
                    buy_entry_price, buy_price_with_fees, buy_real_price, buy_amount, buy_date,
                    sell_entry_price, sell_price_with_fees, sell_real_price, sell_amount,
                    pnl, bnb_amount
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, NULL, NULL, NULL)
            """, (
                pair_address, token_address, symbol, name,
                buy_entry_price, buy_price_with_fees, buy_date_ts
            ))
            return int(cur.lastrowid)

    def set_buy_final_result(self, history_id: int, buy_real_price: float, buy_amount: float) -> None:
        """
        Actualiza con los datos reales tras la TX de compra.
        """
        with self._conn() as c:
            c.execute("""
                UPDATE history
                   SET buy_real_price = ?, buy_amount = ?
                 WHERE id = ?
            """, (buy_real_price, buy_amount, history_id))

    def finalize_sell(self,
                      history_id: int,
                      sell_entry_price: Optional[float],
                      sell_price_with_fees: Optional[float],
                      sell_real_price: float,
                      sell_amount: float,
                      pnl: float,
                      bnb_amount: float) -> None:
        """
        Actualiza con los datos reales de venta y resultados (pnl, bnb_amount).
        """
        with self._conn() as c:
            c.execute("""
                UPDATE history
                   SET sell_entry_price     = ?,
                       sell_price_with_fees = ?,
                       sell_real_price      = ?,
                       sell_amount          = ?,
                       pnl                  = ?,
                       bnb_amount           = ?
                 WHERE id = ?
            """, (
                sell_entry_price, sell_price_with_fees,
                sell_real_price, sell_amount,
                pnl, bnb_amount, history_id
            ))

    # ---------- Consultas de apoyo ----------
    def get_by_id(self, history_id: int) -> Optional[dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
            return dict(row) if row else None

    def get_last_by_pair(self, pair_address: str) -> Optional[dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("""
                SELECT * FROM history
                 WHERE pair_address = ?
                 ORDER BY id DESC
                 LIMIT 1
            """, (pair_address,)).fetchone()
            return dict(row) if row else None

    def list_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
