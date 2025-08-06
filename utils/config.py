"""
Configuration loading for bsc_sniper.

This module provides a simple helper to load YAML configuration files from the
project root. The file ``config.yaml`` is expected to reside alongside
``main.py``. If the file is missing, an empty dictionary is returned.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import yaml  # type: ignore


def load_config() -> Dict[str, Any]:
    """Load application configuration from ``config.yaml``.

    :returns: A dictionary representing the configuration. Missing files
        quietly yield an empty dictionary.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    config_path = os.path.join(base_dir, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}
