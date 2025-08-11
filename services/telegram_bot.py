import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from utils.log_config import logger_manager, log_function
from repositories.action_repository import ActionRepository
from repositories.monitor_repository import MonitorRepository

logger = logger_manager.setup_logger(__name__)

def _esc(s: str) -> str:
    return (s or "").replace("\\","\\\\").replace("_","\\_").replace("*","\\*").replace("`","\\`").replace("[","\\[").replace("]","\\]")

class TelegramBot:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        if not self.token:
            raise RuntimeError("Falta TELEGRAM_TOKEN")

        self.actions = ActionRepository(os.getenv("DB_PATH"))
        self.monitor = MonitorRepository(os.getenv("DB_PATH"))

        self.application = Application.builder().token(self.token).build()

        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("acciones", self.cmd_acciones))
        self.application.add_handler(CommandHandler("autorizar", self.cmd_autorizar))
        self.application.add_handler(CommandHandler("cancelar", self.cmd_cancelar))
        self.application.add_handler(CallbackQueryHandler(self.cb_action, pattern=r'^(autorizar|cancelar):'))

        # Push periódico
        interval = int(os.getenv("TELEGRAM_PUSH_INTERVAL", "15"))
        if interval > 0:
            self.application.job_queue.run_repeating(self._push_pending_actions, interval=interval, first=3, name="push_acciones")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Bot listo. Usa /acciones para ver pendientes.")

    async def cmd_acciones(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pend = self.actions.list_all(estado="pendiente", limit=50)
        if not pend:
            await update.message.reply_text("No hay acciones pendientes.")
            return
        lines = []
        for r in pend:
            token_url = f"https://bscscan.com/token/{r['token_address']}" if r.get("token_address") else "N/D"
            motivo = r.get("motivo") or "Sin detalle."
            lines.append(
                f"• `{r['pair_address']}` — {r['tipo']}\n"
                f"  Motivo: {_esc(motivo)}\n"
                f"  BscScan: {token_url}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_autorizar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /autorizar <pair_address>")
            return
        pair = context.args[0]
        self.actions.autorizar_accion(pair)
        await update.message.reply_text(f"✅ Autorizada: `{pair}`", parse_mode="Markdown")

    async def cmd_cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /cancelar <pair_address>")
            return
        pair = context.args[0]
        self.actions.cancelar_accion(pair)
        await update.message.reply_text(f"🛑 Cancelada: `{pair}`", parse_mode="Markdown")

    async def cb_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data or ""
        if data.startswith("autorizar:"):
            pair = data.split(":",1)[1]
            self.actions.autorizar_accion(pair)
            await query.edit_message_text(f"✅ Autorizada: `{pair}`", parse_mode="Markdown")
        elif data.startswith("cancelar:"):
            pair = data.split(":",1)[1]
            self.actions.cancelar_accion(pair)
            await query.edit_message_text(f"🛑 Cancelada: `{pair}`", parse_mode="Markdown")

    async def _push_pending_actions(self, context: ContextTypes.DEFAULT_TYPE):
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            logger.warning("TELEGRAM_CHAT_ID no definido; no puedo enviar push.")
            return
        try:
            rows = self.actions.list_pending_not_notified(limit=20)
            for r in rows:
                token_url = f"https://bscscan.com/token/{r['token_address']}" if r.get("token_address") else "N/D"
                motivo = r.get("motivo") or "Sin detalle."
                msg = (
                    "⚠️ *Acción pendiente*\n"
                    f"*Pair:* `{r['pair_address']}`\n"
                    f"*Tipo:* {r['tipo']}\n"
                    f"*Motivo:* {_esc(motivo)}\n"
                    f"*BscScan:* {token_url}"
                )
                kb = InlineKeyboardMarkup([[ 
                    InlineKeyboardButton("✅ Autorizar", callback_data=f"autorizar:{r['pair_address']}"),
                    InlineKeyboardButton("🛑 Rechazar",  callback_data=f"cancelar:{r['pair_address']}")
                ]])
                await context.bot.send_message(chat_id=int(chat_id), text=msg, parse_mode="Markdown", reply_markup=kb)
                self.actions.marcar_notificado(r["pair_address"])
        except Exception as e:
            logger.exception(f"[push_pending_actions] error: {e}")

    def run(self):
        logger.info("TelegramBot iniciando...")
        # main.py crea el loop en el hilo del bot; no instales signal handlers aquí
        self.application.run_polling(stop_signals=None, close_loop=False)

    def stop_running(self):
        try:
            self.application.stop()
        except Exception:
            pass
