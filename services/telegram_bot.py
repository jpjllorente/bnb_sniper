import os
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update
from controllers.telegram_controller import TelegramController
from utils.log_config import logger_manager, log_function

logger = logger_manager.setup_logger(__name__)


class TelegramBot:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        if not self.token:
            raise RuntimeError("Falta TELEGRAM_TOKEN en el entorno")

        self.controller = TelegramController()
        self.updater = Updater(token=self.token, use_context=True)
        self.dispatcher = self.updater.dispatcher

        self.dispatcher.add_handler(CommandHandler("start", self.handle_start))
        self.dispatcher.add_handler(CommandHandler("comprar", self.handle_comprar))
        self.dispatcher.add_handler(CommandHandler("vender", self.handle_vender))
        self.dispatcher.add_handler(CommandHandler("cancelar", self.handle_cancelar))

    def handle_start(self, update: Update, context: CallbackContext) -> None:
        update.message.reply_text("🤖 Bot activo. Usa /comprar, /vender o /cancelar <pair_address>.")

    def _extraer_pair_address(self, update: Update, context: CallbackContext) -> str | None:
        if len(context.args) != 1:
            update.message.reply_text("⚠️ Uso correcto: /comando <pair_address>")
            return None
        return context.args[0]

    def handle_comprar(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return

        estado = self.controller.obtener_estado(pair)
        if not estado:
            update.message.reply_text(f"⚠️ No hay solicitud de COMPRA pendiente para {pair}")
            return

        self.controller.autorizar_accion(pair)
        update.message.reply_text(f"✅ Compra autorizada para {pair}")
        logger.info(f"Telegram: COMPRA autorizada para {pair}")

    def handle_vender(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return

        estado = self.controller.obtener_estado(pair)
        if not estado:
            update.message.reply_text(f"⚠️ No hay solicitud de VENTA pendiente para {pair}")
            return

        self.controller.autorizar_accion(pair)
        update.message.reply_text(f"✅ Venta autorizada para {pair}")
        logger.info(f"Telegram: VENTA autorizada para {pair}")

    def handle_cancelar(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return

        estado = self.controller.obtener_estado(pair)
        if not estado:
            update.message.reply_text(f"⚠️ No hay ninguna acción pendiente para {pair}")
            return

        self.controller.cancelar_accion(pair)
        update.message.reply_text(f"🚫 Acción cancelada para {pair}")
        logger.info(f"Telegram: ACCIÓN cancelada para {pair}")

    def start(self):
        logger.info("🤖 Bot de Telegram iniciado.")
        self.updater.start_polling()
        self.updater.idle()