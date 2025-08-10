# services/telegram_bot.py  (python-telegram-bot v20+)
from __future__ import annotations
import os
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from controllers.telegram_controller import TelegramController
from repositories.action_repository import ActionRepository
from repositories.monitor_repository import MonitorRepository
from utils.log_config import logger_manager

logger = logger_manager.setup_logger(__name__)

class TelegramBot:
    """
    Bot v20+: Application + async handlers.
    Exponer:
      - run_polling()  -> bloquea el hilo actual
      - stop_running() -> parar desde fuera
    """
    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        if not self.token:
            raise RuntimeError("Falta TELEGRAM_TOKEN")

        self.controller = TelegramController()
        self.actions = ActionRepository()
        self.monitor = MonitorRepository()

        self.application = Application.builder().token(self.token).build()

        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("estado", self.handle_estado))
        self.application.add_handler(CommandHandler("acciones", self.handle_acciones))
        self.application.add_handler(CommandHandler("monitoreo", self.handle_monitoreo))
        self.application.add_handler(CommandHandler("comprar", self.handle_comprar))
        self.application.add_handler(CommandHandler("vender", self.handle_vender))
        self.application.add_handler(CommandHandler("cancelar", self.handle_cancelar))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

    # ---------- utils ----------
    def _pair_from_args(self, args: list[str]) -> Optional[str]:
        if len(args) != 1:
            return None
        return args[0].strip()

    # ---------- commands ----------
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "🤖 Bot activo.\n"
            "Comandos:\n"
            "  /acciones  → ver acciones pendientes y gestionar\n"
            "  /monitoreo → ver tokens monitorizados\n"
            "  /estado <pair>\n"
            "  /comprar <pair>\n"
            "  /vender <pair>\n"
            "  /cancelar <pair>"
        )

    async def handle_estado(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pair = self._pair_from_args(context.args)
        if not pair:
            await update.message.reply_text("⚠️ Uso: /estado <pair_address>")
            return
        estado = self.controller.obtener_estado(pair) or "sin registro"
        tipo   = self.controller.obtener_tipo(pair) or "-"
        await update.message.reply_text(f"ℹ️ {pair}\nTipo: {tipo}\nEstado: {estado}")

    async def handle_acciones(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        rows = self.actions.list_all(estado="pendiente", limit=50)
        if not rows:
            await update.message.reply_text("✅ No hay acciones pendientes.")
            return
        for r in rows:
            pair = r["pair_address"]; tipo = r["tipo"]; estado = r["estado"]
            kb = InlineKeyboardMarkup([[  # botones inline
                InlineKeyboardButton("✅ Autorizar", callback_data=f"act|approve|{pair}"),
                InlineKeyboardButton("🚫 Cancelar",  callback_data=f"act|cancel|{pair}")
            ]])
            await update.message.reply_text(
                f"⏳ *Pendiente*: {tipo}\n`{pair}`\nEstado: {estado}",
                parse_mode="Markdown", reply_markup=kb
            )

    async def handle_monitoreo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        rows = self.monitor.list_monitored(limit=30)
        if not rows:
            await update.message.reply_text("ℹ️ No hay tokens en monitorización.")
            return
        for r in rows:
            pair = r["pair_address"]; sym = r.get("symbol") or "-"
            price = r.get("price"); pnl = r.get("pnl")
            price_txt = f"{price:.8f} BNB" if isinstance(price, (int, float)) else "N/D"
            pnl_txt = f"{pnl:+.2f}%" if isinstance(pnl, (int, float)) else "N/D"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔎 Estado", callback_data=f"mon|state|{pair}")]])
            await update.message.reply_text(
                f"📈 {sym} — `{pair}`\n"
                f"Precio: {price_txt} | PnL: {pnl_txt}",
                parse_mode="Markdown", reply_markup=kb
            )

    async def handle_comprar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pair = self._pair_from_args(context.args)
        if not pair:
            await update.message.reply_text("⚠️ Uso: /comprar <pair>")
            return
        estado = self.controller.obtener_estado(pair); tipo = self.controller.obtener_tipo(pair)
        if estado != "pendiente" or tipo != "compra":
            await update.message.reply_text(f"⚠️ No hay COMPRA pendiente para `{pair}`.", parse_mode="Markdown"); return
        self.controller.autorizar_accion(pair)
        await update.message.reply_text(f"✅ Compra autorizada para `{pair}`", parse_mode="Markdown")

    async def handle_vender(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pair = self._pair_from_args(context.args)
        if not pair:
            await update.message.reply_text("⚠️ Uso: /vender <pair>")
            return
        estado = self.controller.obtener_estado(pair); tipo = self.controller.obtener_tipo(pair)
        if estado != "pendiente" or tipo != "venta":
            await update.message.reply_text(f"⚠️ No hay VENTA pendiente para `{pair}`.", parse_mode="Markdown"); return
        self.controller.autorizar_accion(pair)
        await update.message.reply_text(f"✅ Venta autorizada para `{pair}`", parse_mode="Markdown")

    async def handle_cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pair = self._pair_from_args(context.args)
        if not pair:
            await update.message.reply_text("⚠️ Uso: /cancelar <pair>")
            return
        if self.controller.obtener_estado(pair) is None:
            await update.message.reply_text(f"⚠️ No hay acción registrada para `{pair}`.", parse_mode="Markdown"); return
        self.controller.cancelar_accion(pair)
        await update.message.reply_text(f"🚫 Acción cancelada para `{pair}`", parse_mode="Markdown")

    # ---------- callbacks ----------
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        if not q or not q.data:
            return
        try:
            kind, action, pair = q.data.split("|", 2)
        except ValueError:
            await q.answer("Formato de callback desconocido.")
            return

        if kind == "act":
            if action == "approve":
                est = self.controller.obtener_estado(pair); tipo = self.controller.obtener_tipo(pair)
                if est == "pendiente":
                    self.controller.autorizar_accion(pair)
                    await q.edit_message_text(f"✅ {tipo.capitalize()} autorizada para `{pair}`", parse_mode="Markdown")
                else:
                    await q.answer("No está en pendiente.")
            elif action == "cancel":
                est = self.controller.obtener_estado(pair)
                if est is not None:
                    self.controller.cancelar_accion(pair)
                    await q.edit_message_text(f"🚫 Acción cancelada para `{pair}`", parse_mode="Markdown")
                else:
                    await q.answer("No existe acción para ese par.")

        elif kind == "mon" and action == "state":
            row = next((r for r in self.monitor.list_monitored(limit=100) if r["pair_address"] == pair), None)
            if not row:
                await q.answer("No encontrado.")
                return
            sym = row.get("symbol") or "-"
            price = row.get("price"); pnl = row.get("pnl")
            entry = row.get("entry_price"); bpf = row.get("buy_price_with_fees")
            price_txt = f"{price:.8f} BNB" if isinstance(price, (int, float)) else "N/D"
            pnl_txt = f"{pnl:+.2f}%" if isinstance(pnl, (int, float)) else "N/D"
            entry_txt = f"{entry:.8f}" if isinstance(entry, (int, float)) else "N/D"
            bpf_txt   = f"{bpf:.8f}" if isinstance(bpf, (int, float)) else "N/D"
            await q.answer()
            await q.edit_message_text(
                f"🔎 *Estado*\n"
                f"{sym} — `{pair}`\n"
                f"Precio: {price_txt}\n"
                f"Entry: {entry_txt} | Con fees: {bpf_txt}\n"
                f"PnL: {pnl_txt}",
                parse_mode="Markdown"
            )

    # ---------- ciclo de vida ----------
    def run_polling(self) -> None:
        logger.info("🤖 Bot de Telegram iniciado (v20+).")
        self.application.run_polling()

    def stop_running(self) -> None:
        # usable desde hilos externos
        try:
            self.application.stop_running()
        except Exception as e:
            logger.error(f"Error al parar TelegramBot: {e}")
