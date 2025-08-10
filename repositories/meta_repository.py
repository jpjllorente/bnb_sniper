import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "./data/memecoins.db")

class MetaRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _ensure(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    k TEXT PRIMARY KEY,
                    v TEXT
                )
            """)

    def get(self, key: str, default: str | None = None) -> str | None:
        with self._conn() as c:
            r = c.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
            return r[0] if r else default

    def set(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?,?)", (key, value))
