"""
Centralized logging utilities for the bsc_sniper project.

This module exposes a ``setup_logger`` function to configure loggers with a
daily rotating file handler, and a ``log_function`` decorator to trace
function entry and exit. By default, logs are written into a ``logs``
directory one level above the package root with a filename of
``bsc_sniper.log`` and at the DEBUG level.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from services.telegram_service import TelegramService

LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_TELEGRAM_ERRORS = os.getenv("LOG_TELEGRAM_ERRORS", "False") == "True"
telegram_service = TelegramService() if LOG_TELEGRAM_ERRORS else None


class TelegramErrorHandler(logging.Handler):
    def __init__(self, telegram_service: TelegramService):
        super().__init__(level=logging.ERROR)
        self.telegram_service = telegram_service

    def emit(self, record):
        try:
            msg = self.format(record)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            mensaje = f"🛑 *Error crítico*\n\n`{timestamp}`\n{msg}"
            self.telegram_service.notificar_error(mensaje)
        except Exception:
            pass  # No debe romper el sistema

class LoggerManager:
    def __init__(self, log_level=logging.DEBUG, enable_telegram: bool = False):
        self.log_level = log_level
        self.enable_telegram = enable_telegram
        self.telegram_service = TelegramService() if enable_telegram else None
        self._loggers = {}

    def setup_logger(self, name: str) -> logging.Logger:
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)

        if not logger.handlers:
            # File handler
            file_handler = logging.FileHandler(f"{LOG_DIR}/{name.replace('.', '_')}.log")
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)

            # Console handler
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
            logger.addHandler(stream_handler)

            # Telegram handler
            if self.enable_telegram and self.telegram_service:
                tg_handler = TelegramErrorHandler(self.telegram_service)
                tg_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
                logger.addHandler(tg_handler)

        self._loggers[name] = logger
        return logger

    def log_function(self, func):
        """
        Decorador para registrar entrada y salida de funciones.
        """
        def wrapper(*args, **kwargs):
            logger = self.setup_logger(func.__module__)
            logger.debug(f"→ {func.__name__}() args={args} kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"← {func.__name__}() result={result}")
                return result
            except Exception as e:
                logger.exception(f"🔥 Excepción en {func.__name__}: {e}")
                raise
        return wrapper