import os
from telegram import Bot
from telegram.error import TelegramError
from models.token import Token
from controllers.telegram_controller import TelegramController
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

class TelegramService:
    def __init__(self):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            raise RuntimeError("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el entorno")
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.chat_id = TELEGRAM_CHAT_ID
        self.controller = TelegramController()

    @log_function
    def solicitar_accion(self, tipo: str, token: Token, contexto: str) -> None:
        """
        Envía al usuario una solicitud para autorizar una compra o venta.
        Registra la acción como 'pendiente' SOLO si el mensaje se envía correctamente.
        """
        pair = token.pair_address
        tipo_limpio = (tipo or "").strip().lower()
        if tipo_limpio == "compra":
            comandos = f"`/comprar {pair}`\n`/cancelar {pair}`"
            titulo = "COMPRA"
        elif tipo_limpio == "venta":
            comandos = f"`/vender {pair}`\n`/cancelar {pair}`"
            titulo = "VENTA"
        else:
            comandos = f"`/cancelar {pair}`"
            titulo = tipo.upper() if tipo else "ACCIÓN"

        price_txt = f"{float(token.price_native):.8f}" if token.price_native is not None else "N/D"
        mensaje = (
            f"📢 *Confirmación requerida: {titulo}*\n\n"
            f"Token: {token.symbol}\n"
            f"Pair: `{pair}`\n"
            f"Precio actual: {price_txt} BNB\n\n"
            f"*Motivo:* {contexto}\n\n"
            f"👉 Responde con:\n{comandos}"
        )

        try:
            self.bot.send_message(chat_id=self.chat_id, text=mensaje, parse_mode="Markdown")
            # Solo si enviamos bien, registramos la acción
            self.controller.registrar_accion(token, tipo_limpio)
        except TelegramError as e:
            logger.error(f"❌ Error al enviar solicitud de {tipo}: {e}")

    @log_function
    def notificar_info(self, mensaje: str) -> None:
        try:
            self.bot.send_message(chat_id=self.chat_id, text=f"ℹ️ {mensaje}")
        except TelegramError as e:
            logger.error(f"❌ Error al enviar notificación info: {e}")

    @log_function
    def notificar_error(self, mensaje: str) -> None:
        try:
            self.bot.send_message(chat_id=self.chat_id, text=f"🚨 *ERROR*: {mensaje}", parse_mode="Markdown")
        except TelegramError as e:
            logger.error(f"❌ Error al enviar notificación de error: {e}")
