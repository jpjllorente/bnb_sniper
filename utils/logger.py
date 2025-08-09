"""
Centralized logging utilities for the bsc_sniper project.

This module exposes a ``setup_logger`` function to configure loggers with a
daily rotating file handler, and a ``log_function`` decorator to trace
function entry and exit. By default, logs are written into a ``logs``
directory one level above the package root with a filename of
``bsc_sniper.log`` and at the DEBUG level.
"""

from __future__ import annotations

import logging, os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional
from services.telegram_service import TelegramService

LOG_DIR = os.getenv("LOG_DIR", "./logs")

class TelegramErrorHandler(logging.Handler):
    def __init__(self, telegram_service: TelegramService):
        super().__init__(level=logging.ERROR)
        self.telegram_service = telegram_service or TelegramService()
    def emit(self, record):
        try:
            msg = self.format(record)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.telegram_service.notificar_error(f"🛑 *Error crítico*\n\n`{timestamp}`\n{msg}")
        except Exception:
            pass

class LoggerManager:
    def __init__(self, enable_telegram: bool = False):
        self.enable_telegram = enable_telegram
        self._loggers = {}
        os.makedirs(LOG_DIR, exist_ok=True)

    def setup_logger(self, name: str) -> logging.Logger:
        if name in self._loggers:
            return self._loggers[name]
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            fh = RotatingFileHandler(os.path.join(LOG_DIR, f"{name.replace('.', '_')}.log"),
                                     maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
            fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
            logger.addHandler(fh)
            logger.addHandler(ch)
            if self.enable_telegram:
                logger.addHandler(TelegramErrorHandler())
            logger.propagate = False
        self._loggers[name] = logger
        return logger

    def log_function(self, func):
        def wrapper(*args, **kwargs):
            logger = self.setup_logger(func.__module__)
            logger.debug(f"→ {func.__name__} args={args} kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"← {func.__name__} result={result}")
                return result
            except Exception as e:
                logger.exception(f"🔥 Excepción en {func.__name__}: {e}")
                raise
        return wrapper

logger_manager = LoggerManager(enable_telegram=False)
log_function = logger_manager.log_function
