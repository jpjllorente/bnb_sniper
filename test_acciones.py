import os, sqlite3
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

def resolve_db():
    env = os.getenv("DB_PATH", "./data/memecoins.db")
    here = Path(__file__).resolve().parent
    base = here if (here / "data").exists() else here.parent
    p = Path(env)
    return p if p.is_absolute() else (base / p).resolve()

db_path = resolve_db()
print(f"[tests_acciones] DB => {db_path} | exists={db_path.exists()}")

con = sqlite3.connect(db_path)
cur = con.cursor()

for row in cur.execute("SELECT LOWER(estado), COUNT(*) FROM acciones GROUP BY LOWER(estado)"):
    print(" -", row)

rows = cur.execute("""
    SELECT rowid AS id, pair_address, tipo, estado, timestamp
    FROM acciones
    WHERE LOWER(estado) IN ('pendiente','pending')
    ORDER BY timestamp ASC
    LIMIT 10
""").fetchall()

print(f"[tests_acciones] pendientes={len(rows)}")
for r in rows:
    print("  ", r)

con.close()
