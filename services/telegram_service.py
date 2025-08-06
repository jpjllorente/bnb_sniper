"""
Service for interacting with the user via Telegram.

This skeleton simply simulates user confirmation by always returning True.
Replace the stubbed methods with calls to the Telegram Bot API to send
messages and wait for user replies.
"""

from __future__ import annotations

from models.token import Token
from utils.logger import log_function

class TelegramService:
    """Interact with the user via Telegram."""

    @log_function
    def confirm_high_fee(self, token: Token, fee_percent: float) -> bool:
        # TODO: conectar al bot real de Telegram
        print(f"🚨 Alta comisión estimada para {token.symbol}: {fee_percent}%")
        print("¿Deseas continuar con la compra? (S/N)")
        respuesta = input().strip().lower()
        return respuesta == "s"