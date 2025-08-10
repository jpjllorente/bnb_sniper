# services/telegram_bot.py
import os
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from controllers.telegram_controller import TelegramController
from repositories.action_repository import ActionRepository
from repositories.monitor_repository import MonitorRepository
from utils.log_config import logger_manager

logger = logger_manager.setup_logger(__name__)

class TelegramBot:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        if not self.token:
            raise RuntimeError("Falta TELEGRAM_TOKEN")

        self.controller = TelegramController()
        self.actions = ActionRepository()
        self.monitor = MonitorRepository()

        self.updater = Updater(token=self.token, use_context=True)
        dp = self.updater.dispatcher

        dp.add_handler(CommandHandler("start", self.handle_start))
        dp.add_handler(CommandHandler("estado", self.handle_estado))
        dp.add_handler(CommandHandler("acciones", self.handle_acciones))
        dp.add_handler(CommandHandler("monitoreo", self.handle_monitoreo))
        dp.add_handler(CommandHandler("comprar", self.handle_comprar))
        dp.add_handler(CommandHandler("vender", self.handle_vender))
        dp.add_handler(CommandHandler("cancelar", self.handle_cancelar))
        dp.add_handler(CallbackQueryHandler(self.handle_callback))

    def handle_start(self, update: Update, _: CallbackContext) -> None:
        update.message.reply_text(
            "🤖 Bot activo.\n"
            "Comandos:\n"
            "  /acciones  → ver acciones pendientes y gestionar\n"
            "  /monitoreo → ver tokens monitorizados\n"
            "  /estado <pair>\n"
            "  /comprar <pair>\n"
            "  /vender <pair>\n"
            "  /cancelar <pair>"
        )

    def _pair_arg(self, update: Update, context: CallbackContext):
        if len(context.args) != 1:
            update.message.reply_text("⚠️ Uso: /comando <pair_address>")
            return None
        return context.args[0].strip()

    # Estado individual
    def handle_estado(self, update: Update, context: CallbackContext) -> None:
        pair = self._pair_arg(update, context)
        if not pair:
            return
        estado = self.controller.obtener_estado(pair) or "sin registro"
        tipo   = self.controller.obtener_tipo(pair) or "-"
        update.message.reply_text(f"ℹ️ {pair}\nTipo: {tipo}\nEstado: {estado}")

    # Acciones pendientes
    def handle_acciones(self, update: Update, _: CallbackContext) -> None:
        rows = self.actions.list_all(estado="pendiente", limit=50)
        if not rows:
            update.message.reply_text("✅ No hay acciones pendientes.")
            return
        for r in rows:
            pair = r["pair_address"]; tipo = r["tipo"]; estado = r["estado"]
            kb = InlineKeyboardMarkup([[  # botones inline
                InlineKeyboardButton("✅ Autorizar", callback_data=f"act|approve|{pair}"),
                InlineKeyboardButton("🚫 Cancelar",  callback_data=f"act|cancel|{pair}")
            ]])
            update.message.reply_text(
                f"⏳ *Pendiente*: {tipo}\n`{pair}`\nEstado: {estado}",
                parse_mode="Markdown", reply_markup=kb
            )

    # Monitoreo (snapshot de monitor_state)
    def handle_monitoreo(self, update: Update, _: CallbackContext) -> None:
        rows = self.monitor.list_monitored(limit=30)
        if not rows:
            update.message.reply_text("ℹ️ No hay tokens en monitorización.")
            return
        for r in rows:
            pair = r["pair_address"]; sym = r.get("symbol") or "-"
            price = r.get("price"); pnl = r.get("pnl")
            price_txt = f"{price:.8f} BNB" if isinstance(price, (int, float)) else "N/D"
            pnl_txt = f"{pnl:+.2f}%" if isinstance(pnl, (int, float)) else "N/D"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔎 Estado", callback_data=f"mon|state|{pair}")]])
            update.message.reply_text(
                f"📈 {sym} — `{pair}`\n"
                f"Precio: {price_txt} | PnL: {pnl_txt}",
                parse_mode="Markdown", reply_markup=kb
            )

    # Autorizaciones directas por comando
    def handle_comprar(self, update: Update, context: CallbackContext) -> None:
        pair = self._pair_arg(update, context)
        if not pair: return
        estado = self.controller.obtener_estado(pair); tipo = self.controller.obtener_tipo(pair)
        if estado != "pendiente" or tipo != "compra":
            update.message.reply_text(f"⚠️ No hay COMPRA pendiente para `{pair}`.", parse_mode="Markdown"); return
        self.controller.autorizar_accion(pair)
        update.message.reply_text(f"✅ Compra autorizada para `{pair}`", parse_mode="Markdown")

    def handle_vender(self, update: Update, context: CallbackContext) -> None:
        pair = self._pair_arg(update, context)
        if not pair: return
        estado = self.controller.obtener_estado(pair); tipo = self.controller.obtener_tipo(pair)
        if estado != "pendiente" or tipo != "venta":
            update.message.reply_text(f"⚠️ No hay VENTA pendiente para `{pair}`.", parse_mode="Markdown"); return
        self.controller.autorizar_accion(pair)
        update.message.reply_text(f"✅ Venta autorizada para `{pair}`", parse_mode="Markdown")

    def handle_cancelar(self, update: Update, context: CallbackContext) -> None:
        pair = self._pair_arg(update, context)
        if not pair: return
        if self.controller.obtener_estado(pair) is None:
            update.message.reply_text(f"⚠️ No hay acción registrada para `{pair}`.", parse_mode="Markdown"); return
        self.controller.cancelar_accion(pair)
        update.message.reply_text(f"🚫 Acción cancelada para `{pair}`", parse_mode="Markdown")

    # Callbacks de botones inline
    def handle_callback(self, update: Update, context: CallbackContext) -> None:
        q = update.callback_query
        if not q or not q.data:
            return
        try:
            kind, action, pair = q.data.split("|", 2)
        except ValueError:
            q.answer("Formato de callback desconocido."); return

        if kind == "act":
            if action == "approve":
                est = self.controller.obtener_estado(pair); tipo = self.controller.obtener_tipo(pair)
                if est == "pendiente":
                    self.controller.autorizar_accion(pair)
                    q.edit_message_text(f"✅ {tipo.capitalize()} autorizada para `{pair}`", parse_mode="Markdown")
                else:
                    q.answer("No está en pendiente.")
            elif action == "cancel":
                est = self.controller.obtener_estado(pair)
                if est is not None:
                    self.controller.cancelar_accion(pair)
                    q.edit_message_text(f"🚫 Acción cancelada para `{pair}`", parse_mode="Markdown")
                else:
                    q.answer("No existe acción para ese par.")

        elif kind == "mon" and action == "state":
            row = next((r for r in self.monitor.list_monitored(limit=100) if r["pair_address"] == pair), None)
            if not row:
                q.answer("No encontrado."); return
            sym = row.get("symbol") or "-"
            price = row.get("price"); pnl = row.get("pnl")
            entry = row.get("entry_price"); bpf = row.get("buy_price_with_fees")
            price_txt = f"{price:.8f} BNB" if isinstance(price, (int, float)) else "N/D"
            pnl_txt = f"{pnl:+.2f}%" if isinstance(pnl, (int, float)) else "N/D"
            entry_txt = f"{entry:.8f}" if isinstance(entry, (int, float)) else "N/D"
            bpf_txt   = f"{bpf:.8f}" if isinstance(bpf, (int, float)) else "N/D"
            q.answer()
            q.edit_message_text(
                f"🔎 *Estado*\n"
                f"{sym} — `{pair}`\n"
                f"Precio: {price_txt}\n"
                f"Entry: {entry_txt} | Con fees: {bpf_txt}\n"
                f"PnL: {pnl_txt}",
                parse_mode="Markdown"
            )

    def start(self):
        logger.info("🤖 Bot de Telegram iniciado.")
        self.updater.start_polling()
        self.updater.idle()
