from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "../../memecoins.db")

class HistoryRepository:
    def __init__(self, db_path: str = DB_PATH)->None:
        self.db_path=db_path; self._ensure_table()

    @contextmanager
    def _conn(self):
        conn=sqlite3.connect(self.db_path); conn.row_factory=sqlite3.Row
        try: yield conn
        finally: conn.close()

    def _ensure_table(self)->None:
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_address TEXT NOT NULL, token_address TEXT NOT NULL,
                symbol TEXT, name TEXT,
                buy_entry_price REAL, buy_price_with_fees REAL, buy_real_price REAL,
                buy_amount REAL, buy_date INTEGER,
                sell_entry_price REAL, sell_price_with_fees REAL, sell_real_price REAL,
                sell_amount REAL, sell_date INTEGER,
                pnl REAL, bnb_amount REAL)""")
            c.commit()

    def create_buy(self, pair_address:str, token_address:str, symbol:str|None, name:str|None,
                   buy_entry_price:float|None, buy_price_with_fees:float|None, buy_date_ts:int)->int:
        with self._conn() as c:
            cur=c.execute("""INSERT INTO history(
                pair_address,token_address,symbol,name,buy_entry_price,buy_price_with_fees,buy_date)
                VALUES(?,?,?,?,?,?,?)""",
                (pair_address,token_address,symbol,name,buy_entry_price,buy_price_with_fees,buy_date_ts))
            c.commit(); return int(cur.lastrowid)

    def set_buy_final_result(self, history_id:int, buy_real_price:float, buy_amount:float)->None:
        with self._conn() as c:
            c.execute("UPDATE history SET buy_real_price=?, buy_amount=? WHERE id=?",
                      (buy_real_price,buy_amount,history_id)); c.commit()

    def finalize_sell(self, history_id:int, sell_entry_price:float|None, sell_price_with_fees:float|None,
                      sell_real_price:float, sell_amount:float, pnl:float, bnb_amount:float,
                      sell_date_ts:int|None=None)->None:
        with self._conn() as c:
            c.execute("""UPDATE history SET
                sell_entry_price=?, sell_price_with_fees=?, sell_real_price=?, sell_amount=?,
                sell_date=COALESCE(?, strftime('%s','now')), pnl=?, bnb_amount=? WHERE id=?""",
                (sell_entry_price,sell_price_with_fees,sell_real_price,sell_amount,
                 sell_date_ts,pnl,bnb_amount,history_id))
            c.commit()

    def get_by_id(self, history_id:int)->Optional[dict[str,Any]]:
        with self._conn() as c:
            r=c.execute("SELECT * FROM history WHERE id=?", (history_id,)).fetchone()
            return dict(r) if r else None

    def list_recent(self, limit:int=200)->list[dict[str,Any]]:
        with self._conn() as c:
            rs=c.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rs]

    def summary(self)->dict[str,Any]:
        with self._conn() as c:
            rs=c.execute("""SELECT sell_real_price,buy_real_price,sell_amount,bnb_amount
                            FROM history WHERE sell_real_price IS NOT NULL""").fetchall()
            closed=0; total_bnb=0.0; w=0.0; acc=0.0
            for r in rs:
                sr=r[0]; br=r[1]; amt=r[2] or 0.0; bnb=r[3] or 0.0
                if sr is None or br is None or amt<=0: continue
                closed+=1; total_bnb+=float(bnb)
                acc += ((sr-br)/max(br,1e-18))*amt*100.0; w += amt
            return {"closed_cycles":closed, "bnb_profit_total":total_bnb,
                    "avg_pnl_percent_tokens": (acc/w if w>0 else 0.0)}
