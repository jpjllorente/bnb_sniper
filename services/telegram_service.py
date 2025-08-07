"""
Service for interacting with the user via Telegram.

This skeleton simply simulates user confirmation by always returning True.
Replace the stubbed methods with calls to the Telegram Bot API to send
messages and wait for user replies.
"""
import os
from telegram import Bot
from telegram.error import TelegramError
from models.token import Token
from controllers.telegram_controller import TelegramController
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # define esto en tu .env
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # usuario o grupo que recibe

class TelegramService:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.chat_id = TELEGRAM_CHAT_ID
        self.controller = TelegramController()
        
        
    @log_function
    def solicitar_accion(self, tipo: str, token: Token, contexto: str) -> None:
        """
        Envía al usuario una solicitud para autorizar una compra o venta.
        """
        pair = token.pair_address
        if tipo == "compra":
            comandos = f"`/comprar {pair}`\n`/cancelar {pair}`"
        elif tipo == "venta":
            comandos = f"`/vender {pair}`\n`/cancelar {pair}`"
        else:
            comandos = f"`/cancelar {pair}`"

        mensaje = (
            f"📢 *Confirmación requerida: {tipo.upper()}*\n\n"
            f"Token: {token.symbol}\n"
            f"Pair: `{pair}`\n"
            f"Precio actual: {token.price_native:.8f} BNB\n\n"
            f"*Motivo:* {contexto}\n\n"
            f"👉 Responde con:\n{comandos}"
        )

        try:
            self.bot.send_message(chat_id=self.chat_id, text=mensaje, parse_mode="Markdown")
            self.controller.registrar_accion(token, tipo)
        except TelegramError as e:
            logger.error(f"❌ Error al enviar solicitud de {tipo}: {e}")

    @log_function
    def notificar_info(self, mensaje: str) -> None:
        """
        Envía una notificación informativa al usuario.
        """
        try:
            self.bot.send_message(chat_id=self.chat_id, text=f"ℹ️ {mensaje}")
        except TelegramError as e:
            logger.error(f"❌ Error al enviar notificación info: {e}")

    @log_function
    def notificar_error(self, mensaje: str) -> None:
        """
        Envía una notificación de error al usuario.
        """
        try:
            self.bot.send_message(chat_id=self.chat_id, text=f"🚨 *ERROR*: {mensaje}", parse_mode="Markdown")
        except TelegramError as e:
            logger.error(f"❌ Error al enviar notificación de error: {e}")