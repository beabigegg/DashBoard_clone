# -*- coding: utf-8 -*-
"""Logging helpers shared by watchdog runtime."""

from __future__ import annotations

import logging

_SQLITE_HANDLER_FLAG = "_watchdog_sqlite_handler_registered"


def attach_sqlite_log_handler(target_logger: logging.Logger) -> bool:
    """Attach SQLite log handler to watchdog logger when enabled.

    Returns:
        True if a new handler was attached; otherwise False.
    """
    if getattr(target_logger, _SQLITE_HANDLER_FLAG, False):
        return False

    try:
        from mes_dashboard.core.log_store import LOG_STORE_ENABLED, get_sqlite_log_handler
    except Exception as exc:
        target_logger.warning("Failed to import SQLite log store: %s", exc)
        return False

    if not LOG_STORE_ENABLED:
        return False

    try:
        sqlite_handler = get_sqlite_log_handler()
        sqlite_handler.setLevel(logging.INFO)
        target_logger.addHandler(sqlite_handler)
        setattr(target_logger, _SQLITE_HANDLER_FLAG, True)
        return True
    except Exception as exc:
        target_logger.warning("Failed to initialize SQLite log handler: %s", exc)
        return False
