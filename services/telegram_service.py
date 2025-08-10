from __future__ import annotations
import os, requests
from models.token import Token
from utils.log_config import logger_manager, log_function
from repositories.action_repository import ActionRepository

logger = logger_manager.setup_logger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[","\\[").replace("]","\\]")

class TelegramService:
    def __init__(self):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            raise RuntimeError("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
        self.chat_id = TELEGRAM_CHAT_ID
        self.actions = ActionRepository(os.getenv("DB_PATH"))

    def _send_md(self, text: str):
        try:
            r = requests.post(f"{API_BASE}/sendMessage", json={
                "chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"
            }, timeout=10)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"❌ Error Telegram: {e}")

    @log_function
    def solicitar_accion(self, tipo: str, token: Token, contexto: str) -> None:
        """
        Llamar SOLO cuando el token NO pasa tus parámetros normales.
        Guarda en DB el motivo y la token_address para que el push lo muestre.
        """
        pair = token.pair_address
        token_addr = getattr(token, "address", None) or getattr(token, "token_address", None)
        symbol = getattr(token, "symbol", "") or "N/D"
        price_txt = f"{float(token.price_native):.8f}" if getattr(token, "price_native", None) is not None else "N/D"
        motivo_txt = (contexto or "").strip() or "Sin detalle."
        tipo_up = (tipo or "BUY").upper()

        token_url = f"https://bscscan.com/token/{token_addr}" if token_addr else "N/D"

        msg = (
            f"📢 *Confirmación requerida: {tipo_up}*\n\n"
            f"*Token:* {_esc(symbol)}\n"
            f"*Token URL:* {token_url}\n"
            f"*Pair:* `{pair}`\n"
            f"*Precio actual:* {price_txt} BNB\n\n"
            f"*Motivo:*\n{_esc(motivo_txt)}\n\n"
            f"*Responde:*\n`/autorizar {pair}`\n`/cancelar {pair}`"
        )
        try:
            r = requests.post(f"{API_BASE}/sendMessage", json={
                "chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"
            }, timeout=10)
            r.raise_for_status()
            # ⬇️ Queda persistido con motivo + token_address (para el push automático)
            self.actions.registrar_accion(pair, tipo_up, token_address=token_addr, motivo=motivo_txt)
        except Exception as e:
            logger.error(f"❌ Error al enviar solicitud de {tipo_up}: {e}")

    @log_function
    def notificar_info(self, mensaje: str): self._send_md(f"ℹ️ {mensaje}")

    @log_function
    def notificar_error(self, mensaje: str): self._send_md(f"🚨 *ERROR*: {mensaje}")
