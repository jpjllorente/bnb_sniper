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
        self.dispatcher.add_handler(CommandHandler("estado", self.handle_estado))
        self.dispatcher.add_handler(CommandHandler("comprar", self.handle_comprar))
        self.dispatcher.add_handler(CommandHandler("vender", self.handle_vender))
        self.dispatcher.add_handler(CommandHandler("cancelar", self.handle_cancelar))

    def handle_start(self, update: Update, context: CallbackContext) -> None:
        update.message.reply_text(
            "🤖 Bot activo.\n"
            "Comandos:\n"
            "  /estado <pair>\n"
            "  /comprar <pair>\n"
            "  /vender <pair>\n"
            "  /cancelar <pair>"
        )

    def _extraer_pair_address(self, update: Update, context: CallbackContext) -> str | None:
        if len(context.args) != 1:
            update.message.reply_text("⚠️ Uso correcto: /comando <pair_address>")
            return None
        return context.args[0].strip()

    def handle_estado(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return
        estado = self.controller.obtener_estado(pair) or "sin registro"
        tipo = self.controller.obtener_tipo(pair) or "-"
        update.message.reply_text(f"ℹ️ {pair}\nTipo: {tipo}\nEstado: {estado}")

    def handle_comprar(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return

        estado = self.controller.obtener_estado(pair)
        tipo   = self.controller.obtener_tipo(pair)
        if estado != "pendiente" or tipo != "compra":
            update.message.reply_text(f"⚠️ No hay *COMPRA pendiente* para {pair}. (estado={estado or '-'}, tipo={tipo or '-'})", parse_mode="Markdown")
            return

        self.controller.autorizar_accion(pair)
        update.message.reply_text(f"✅ Compra autorizada para {pair}")
        logger.info(f"Telegram: COMPRA autorizada para {pair}")

    def handle_vender(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return

        estado = self.controller.obtener_estado(pair)
        tipo   = self.controller.obtener_tipo(pair)
        if estado != "pendiente" or tipo != "venta":
            update.message.reply_text(f"⚠️ No hay *VENTA pendiente* para {pair}. (estado={estado or '-'}, tipo={tipo or '-'})", parse_mode="Markdown")
            return

        self.controller.autorizar_accion(pair)
        update.message.reply_text(f"✅ Venta autorizada para {pair}")
        logger.info(f"Telegram: VENTA autorizada para {pair}")

    def handle_cancelar(self, update: Update, context: CallbackContext) -> None:
        pair = self._extraer_pair_address(update, context)
        if not pair:
            return

        estado = self.controller.obtener_estado(pair)
        if estado is None:
            update.message.reply_text(f"⚠️ No hay ninguna acción registrada para {pair}")
            return

        self.controller.cancelar_accion(pair)
        update.message.reply_text(f"🚫 Acción cancelada para {pair}")
        logger.info(f"Telegram: ACCIÓN cancelada para {pair}")

    def start(self):
        logger.info("🤖 Bot de Telegram iniciado.")
        self.updater.start_polling()
        self.updater.idle()
