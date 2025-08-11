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
    # escapado mínimo para Markdown
    return (s or "").replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[","\\[").replace("]","\\]")

class TelegramService:
    def __init__(self, token: str | None = None, chat_id: str | None = None,
                 actions: ActionRepository | None = None) -> None:
        self.token = token or TELEGRAM_TOKEN
        self.chat_id = int(chat_id or TELEGRAM_CHAT_ID) if (chat_id or TELEGRAM_CHAT_ID) else None
        self.actions = actions or ActionRepository()
        if not self.token or not self.chat_id:
            logger.warning("TelegramService sin TOKEN o CHAT_ID; se desactivan envíos.")

    def _send(self, text: str, reply_markup: dict | None = None) -> None:
        if not API_BASE or not self.chat_id:
            return
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10).raise_for_status()
        except Exception as e:
            logger.error(f"❌ Error enviando Telegram: {e}")

    @log_function
    def solicitar_autorizacion(self, token: Token, tipo: str = "compra", contexto: str | None = None) -> None:
        """
        Enviar solicitud de autorización SOLO cuando no pasan filtros
        o cuando el módulo de compra devuelve PENDING_USER (pnl/fees).
        """
        pair = token.pair_address
        token_addr = getattr(token, "address", None) or getattr(token, "token_address", None)
        symbol = (getattr(token, "symbol", "") or "N/D").strip()
        name = (getattr(token, "name", "") or "").strip()
        price_txt = f"{float(getattr(token, 'price_native', 0.0) or 0.0):.8f}"
        motivo_txt = (contexto or "").strip() or "Sin detalle."
        tipo_norm = "compra" if str(tipo).lower() in ("buy","compra") else "venta"
        token_url = f"https://bscscan.com/token/{token_addr}" if token_addr else "N/D"

        msg = (
            f"📢 *Confirmación requerida: {tipo_norm.upper()}*\n\n"
            f"*Token:* {_esc(name)} ({_esc(symbol)})\n"
            f"*Token URL:* {token_url}\n"
            f"*Pair:* `{pair}`\n"
            f"*Precio actual:* {price_txt} BNB\n\n"
            f"*Motivo:* {_esc(motivo_txt)}"
        )
        kb = {
            "inline_keyboard": [[
                {"text": "✅ Autorizar", "callback_data": f"autorizar:{pair}"},
                {"text": "🛑 Rechazar",  "callback_data": f"cancelar:{pair}"}
            ]]
        }
        self._send(msg, reply_markup=kb)
        # Persistir acto pendiente
        self.actions.registrar_accion(pair, tipo_norm, token_address=token_addr, motivo=motivo_txt)

    @log_function
    def notificar_autorizado_info(self, token: Token) -> None:
        """Mensaje informativo para tokens que pasaron filtros (SIN botones)."""
        pair = token.pair_address
        token_addr = getattr(token, "address", None) or getattr(token, "token_address", None)
        symbol = (getattr(token, "symbol", "") or "N/D").strip()
        name = (getattr(token, "name", "") or "").strip()
        price_txt = f"{float(getattr(token, 'price_native', 0.0) or 0.0):.8f}"
        token_url = f"https://bscscan.com/token/{token_addr}" if token_addr else "N/D"
        msg = (
            f"✅ *Autorizado por filtros*\n\n"
            f"*Token:* {_esc(name)} ({_esc(symbol)})\n"
            f"*Token URL:* {token_url}\n"
            f"*Pair:* `{pair}`\n"
            f"*Precio actual:* {price_txt} BNB"
        )
        self._send(msg)

    @log_function
    def notificar_info(self, mensaje: str): 
        self._send(f"ℹ️ {mensaje}")

    @log_function
    def notificar_error(self, mensaje: str): 
        self._send(f"🚨 *ERROR*: {mensaje}")
