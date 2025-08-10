# services/telegram_service.py
from __future__ import annotations
import os
import requests
from models.token import Token
from controllers.telegram_controller import TelegramController
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

def _escape_md(text: str) -> str:
    # Escapado sencillo para Markdown de Telegram (formato "Markdown")
    # Evita problemas con _,*,`,[ y ] en símbolos/addresses.
    return (
        text.replace("\\", "\\\\")
            .replace("_", "\\_")
            .replace("*", "\\*")
            .replace("`", "\\`")
            .replace("[", "\\[")
            .replace("]", "\\]")
    )

class TelegramService:
    def __init__(self):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            raise RuntimeError("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el entorno")
        self.chat_id = TELEGRAM_CHAT_ID
        self.controller = TelegramController()

    def _send_markdown(self, text: str) -> None:
        try:
            r = requests.post(f"{API_BASE}/sendMessage", json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }, timeout=10)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"❌ Error al enviar mensaje a Telegram: {e}")

    @log_function
    def solicitar_accion(self, tipo: str, token: Token, contexto: str) -> None:
        """
        Envía al usuario una solicitud para autorizar una compra o venta.
        Registra la acción como 'pendiente' SOLO si el mensaje se envía correctamente.
        Además, incluye URL de BscScan del token y el motivo (contexto).
        """
        pair = token.pair_address
        token_addr = getattr(token, "address", None) or getattr(token, "token_address", None)
        token_symbol = getattr(token, "symbol", "") or "N/D"

        tipo_limpio = (tipo or "").strip().lower()
        if tipo_limpio == "compra":
            comandos = f"`/autorizar {pair}`\n`/cancelar {pair}`"
            titulo = "COMPRA"
        elif tipo_limpio == "venta":
            comandos = f"`/autorizar {pair}`\n`/cancelar {pair}`"
            titulo = "VENTA"
        else:
            comandos = f"`/cancelar {pair}`"
            titulo = (tipo or "ACCIÓN").upper()

        price_txt = f"{float(token.price_native):.8f}" if getattr(token, "price_native", None) is not None else "N/D"

        # URL de BscScan para el TOKEN (no el pair)
        token_url = f"https://bscscan.com/token/{token_addr}" if token_addr else "N/D"

        motivo_txt = contexto if isinstance(contexto, str) else str(contexto)
        motivo_txt = motivo_txt.strip() or "Sin detalle."

        mensaje = (
            f"📢 *Confirmación requerida: {titulo}*\n\n"
            f"*Token:* {_escape_md(token_symbol)}\n"
            f"*Token URL:* {token_url}\n"
            f"*Pair:* `{pair}`\n"
            f"*Precio actual:* {price_txt} BNB\n\n"
            f"*Motivo (no pasó filtros o requiere revisión):*\n"
            f"{_escape_md(motivo_txt)}\n\n"
            f"*Responde con:*\n{comandos}"
        )

        try:
            r = requests.post(f"{API_BASE}/sendMessage", json={
                "chat_id": self.chat_id,
                "text": mensaje,
                "parse_mode": "Markdown"
            }, timeout=10)
            r.raise_for_status()
            # Registrar solo si se envió bien
            self.controller.registrar_accion(token, tipo_limpio)
        except Exception as e:
            logger.error(f"❌ Error al enviar solicitud de {tipo}: {e}")

    @log_function
    def notificar_info(self, mensaje: str) -> None:
        self._send_markdown(f"ℹ️ {mensaje}")

    @log_function
    def notificar_error(self, mensaje: str) -> None:
        self._send_markdown(f"🚨 *ERROR*: {mensaje}")
