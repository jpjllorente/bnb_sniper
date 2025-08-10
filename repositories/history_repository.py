# repositories/history_repository.py
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class HistoryRepository:
    """
    Persistencia de ciclos compra-venta (UNA fila por ciclo).
    - Todos los precios en BNB/token (unitarios).
    - bnb_amount = beneficio en BNB del ciclo (venta - compra).
    - pnl = ((sell_real_price - buy_real_price)/buy_real_price) * sell_amount * 100
    """
    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_table()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        with self._conn() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_address   TEXT NOT NULL,
                token_address  TEXT NOT NULL,
                symbol         TEXT,
                name           TEXT,
                -- COMPRA (campos de entrada y resultado real)
                buy_entry_price     REAL,
                buy_price_with_fees REAL,
                buy_real_price      REAL,
                buy_amount          REAL,
                buy_date            INTEGER,
                -- VENTA (campos de entrada y resultado real)
                sell_entry_price     REAL,
                sell_price_with_fees REAL,
                sell_real_price      REAL,
                sell_amount          REAL,
                sell_date            INTEGER,
                -- RESULTADO
                pnl         REAL,
                bnb_amount  REAL
            )
            """)
            c.commit()

    # -------------------- COMPRAS --------------------

    def create_buy(
        self,
        pair_address: str,
        token_address: str,
        symbol: Optional[str],
        name: Optional[str],
        buy_entry_price: Optional[float],
        buy_price_with_fees: Optional[float],
        buy_date_ts: int
    ) -> int:
        """Crea registro de compra (sin resultado real aún). Devuelve history_id."""
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO history (
                    pair_address, token_address, symbol, name,
                    buy_entry_price, buy_price_with_fees, buy_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pair_address, token_address, symbol, name,
                buy_entry_price, buy_price_with_fees, buy_date_ts
            ))
            c.commit()
            return int(cur.lastrowid)

    def set_buy_final_result(self, history_id: int, buy_real_price: float, buy_amount: float) -> None:
        """Rellena precio y unidades reales tras el receipt de compra."""
        with self._conn() as c:
            c.execute("""
                UPDATE history
                   SET buy_real_price = ?, buy_amount = ?
                 WHERE id = ?
            """, (buy_real_price, buy_amount, history_id))
            c.commit()

    # -------------------- VENTAS --------------------

    def finalize_sell(
        self,
        history_id: int,
        sell_entry_price: Optional[float],
        sell_price_with_fees: Optional[float],
        sell_real_price: float,
        sell_amount: float,
        pnl: float,
        bnb_amount: float,
        sell_date_ts: Optional[int] = None
    ) -> None:
        """Completa el ciclo con los datos reales de venta, pnl y bnb_amount."""
        with self._conn() as c:
            c.execute("""
                UPDATE history
                   SET sell_entry_price = ?,
                       sell_price_with_fees = ?,
                       sell_real_price = ?,
                       sell_amount = ?,
                       sell_date = COALESCE(?, strftime('%s','now')),
                       pnl = ?,
                       bnb_amount = ?
                 WHERE id = ?
            """, (
                sell_entry_price, sell_price_with_fees,
                sell_real_price, sell_amount, sell_date_ts,
                pnl, bnb_amount, history_id
            ))
            c.commit()

    # -------------------- CONSULTAS --------------------

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

    def summary(self) -> dict[str, Any]:
        """
        Resumen rápido: nº de ciclos cerrados (con sell_real_price no nulo),
        suma de bnb_amount y PnL medio ponderado por tokens vendidos.
        """
        with self._conn() as c:
            rows = c.execute("""
                SELECT sell_real_price, buy_real_price, sell_amount, bnb_amount
                  FROM history
                 WHERE sell_real_price IS NOT NULL
            """).fetchall()
            total_cycles = 0
            total_bnb = 0.0
            total_weight = 0.0
            sum_weighted_pnl = 0.0
            for r in rows:
                sell_r = r[0]; buy_r = r[1]; amt = r[2] or 0.0; bnb = r[3] or 0.0
                if sell_r is None or buy_r is None or amt <= 0: 
                    continue
                total_cycles += 1
                total_bnb += float(bnb)
                # PnL% * tokens (coherente con tu definición)
                pnl_percent_tokens = ((sell_r - buy_r) / max(buy_r, 1e-18)) * amt * 100.0
                sum_weighted_pnl += pnl_percent_tokens
                total_weight += amt
            avg_pnl_percent = (sum_weighted_pnl / total_weight) if total_weight > 0 else 0.0
            return {
                "closed_cycles": total_cycles,
                "bnb_profit_total": total_bnb,
                "avg_pnl_percent_tokens": avg_pnl_percent
            }
