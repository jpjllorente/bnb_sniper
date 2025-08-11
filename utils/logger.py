from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
import os, functools, time
from pathlib import Path

_DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "1048576"))
_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

class _LoggerManager:
    def __init__(self) -> None:
        self._configured = False
        self._module_handlers: dict[str, logging.Handler] = {}
        self._log_dir = os.getenv("LOG_DIR", "./logs")

    def _ensure(self) -> None:
        if self._configured:
            return

        level = getattr(logging, _DEFAULT_LEVEL, logging.DEBUG)
        fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        root = logging.getLogger()
        root.setLevel(level)
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            sh = logging.StreamHandler()
            sh.setLevel(level); sh.setFormatter(fmt)
            root.addHandler(sh)

        Path(self._log_dir).mkdir(parents=True, exist_ok=True)
        self._configured = True

    def setup_logger(self, name: str) -> logging.Logger:
        self._ensure()
        logger = logging.getLogger(name)

        if name not in self._module_handlers:
            safe_name = name.replace(".", "_").replace("/", "_")
            file_path = os.path.join(self._log_dir, f"{safe_name}.log")
            try:
                fh = RotatingFileHandler(file_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
                fh.setLevel(getattr(logging, _DEFAULT_LEVEL, logging.DEBUG))
                fh.setFormatter(logging.Formatter(
                    fmt="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                ))
                self._module_handlers[name] = fh
                logger.addHandler(fh)
                logger.propagate = True  # conserva salida a consola
            except Exception:
                pass

        return logger

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
