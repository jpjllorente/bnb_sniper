from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
import os, functools, time

_DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
_LOG_FILE = os.getenv("LOG_FILE", "./logs/app.log")
_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "1048576"))
_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

class _LoggerManager:
    def __init__(self) -> None:
        self._configured = False

    def _ensure(self) -> None:
        if self._configured:
            return
        level = getattr(logging, _DEFAULT_LEVEL, logging.DEBUG)
        root = logging.getLogger()
        root.setLevel(level)

        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")

        sh = logging.StreamHandler()
        sh.setLevel(level); sh.setFormatter(fmt)
        root.addHandler(sh)

        try:
            fh = RotatingFileHandler(_LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
            fh.setLevel(level); fh.setFormatter(fmt)
            root.addHandler(fh)
        except Exception:
            pass

        self._configured = True

    def setup_logger(self, name: str) -> logging.Logger:
        self._ensure()
        return logging.getLogger(name)

logger_manager = _LoggerManager()

def log_function(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logger_manager.setup_logger(func.__module__)
        logger.debug(f"→ {func.__name__} args={args} kwargs={kwargs}")
        t0 = time.time()
        try:
            result = func(*args, **kwargs)
            logger.debug(f"← {func.__name__} ({(time.time()-t0)*1000:.1f} ms)")
            return result
        except Exception as e:
            logger.exception(f"✗ {func.__name__}: {e}")
            raise
    return wrapper
