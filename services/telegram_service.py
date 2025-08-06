"""
Service for interacting with the user via Telegram.

This skeleton simply simulates user confirmation by always returning True.
Replace the stubbed methods with calls to the Telegram Bot API to send
messages and wait for user replies.
"""

from __future__ import annotations

from utils.logger import log_function


class TelegramService:
    """Interact with the user via Telegram."""

    @log_function
    def confirm_action(self, message: str) -> bool:
        """Ask the user to confirm an action and return their response.

        The current implementation always returns ``True`` to simulate
        affirmative user input. In a full application this method would
        send a message via the Telegram bot and block until a response is
        received.
        """
        # TODO: send message via Telegram API and wait for reply
        return True
