# tests.py
import os
import sys
import requests
from dotenv import load_dotenv, find_dotenv

# Cargar .env del proyecto
dotenv_path = find_dotenv()
load_dotenv(dotenv_path=dotenv_path, override=False)

def die(msg: str, code: int = 1):
    print(f"[tests] {msg}")
    sys.exit(code)

token = os.getenv("TELEGRAM_TOKEN")
chat_id_raw = os.getenv("TELEGRAM_CHAT_ID")

if not token:
    die("Falta TELEGRAM_TOKEN en el entorno/.env")
if not chat_id_raw:
    die("Falta TELEGRAM_CHAT_ID en el entorno/.env (sin comillas)")

try:
    chat_id = int(chat_id_raw)
except ValueError:
    die(f"TELEGRAM_CHAT_ID debe ser numérico. Valor actual: {chat_id_raw!r}")

text = "Ping de prueba ✅ desde backend"
resp = requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": text},
    timeout=15,
)
print(resp.status_code, resp.text)
if resp.status_code == 403:
    print("[tests] El bot no puede escribirte (abre un chat con él y /start).")
