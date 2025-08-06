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
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from typing import Callable, Any


def setup_logger(name: str, log_file: str | None = None, level: int = logging.DEBUG) -> logging.Logger:
    """Configure and return a named logger.

    :param name: Name of the logger (typically ``__name__``).
    :param log_file: Optional override for the log file name. If not provided,
        defaults to ``bsc_sniper.log``.
    :param level: Logging level; defaults to ``logging.DEBUG`` for verbose
        output. In production this could be raised to ``INFO`` or ``WARNING``.
    :returns: A configured ``logging.Logger`` instance.
    """
    # Determine the logs directory relative to this file: ``.../bsc_sniper/utils/logger.py``
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    # Use the provided filename or default
    log_filename = log_file or "bsc_sniper.log"
    log_path = os.path.join(logs_dir, log_filename)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid adding multiple handlers in case of repeated setup calls
    if not logger.handlers:
        handler = TimedRotatingFileHandler(log_path, when="midnight", backupCount=7)
        formatter = logging.Formatter(
            "% (asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def log_function(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that logs entry to and exit from a function.

    The decorated function will log its arguments on entry and its return
    value on exit. This is particularly useful when debugging or tracing the
    behaviour of services and controllers.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger(func.__module__)
        logger.debug("Entering %s with args=%s kwargs=%s", func.__name__, args, kwargs)
        result = func(*args, **kwargs)
        logger.debug("Exiting %s with result=%s", func.__name__, result)
        return result

    return wrapper
