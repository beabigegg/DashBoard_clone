# -*- coding: utf-8 -*-
"""Unit tests for watchdog logging helpers."""

from __future__ import annotations

import logging
from unittest.mock import patch

from mes_dashboard.core.watchdog_logging import attach_sqlite_log_handler


def _reset_logger(logger: logging.Logger) -> None:
    logger.handlers.clear()
    if hasattr(logger, "_watchdog_sqlite_handler_registered"):
        delattr(logger, "_watchdog_sqlite_handler_registered")


def test_attach_sqlite_log_handler_enabled_attaches_once():
    test_logger = logging.getLogger("mes_dashboard.watchdog.test.enabled")
    _reset_logger(test_logger)
    handler_one = logging.NullHandler()
    handler_two = logging.NullHandler()

    with patch("mes_dashboard.core.log_store.LOG_STORE_ENABLED", True), patch(
        "mes_dashboard.core.log_store.get_sqlite_log_handler",
        side_effect=[handler_one, handler_two],
    ) as handler_factory:
        first = attach_sqlite_log_handler(test_logger)
        second = attach_sqlite_log_handler(test_logger)

    assert first is True
    assert second is False
    assert handler_factory.call_count == 1
    assert handler_one in test_logger.handlers
    assert handler_two not in test_logger.handlers

    _reset_logger(test_logger)


def test_attach_sqlite_log_handler_disabled_skips_factory():
    test_logger = logging.getLogger("mes_dashboard.watchdog.test.disabled")
    _reset_logger(test_logger)

    with patch("mes_dashboard.core.log_store.LOG_STORE_ENABLED", False), patch(
        "mes_dashboard.core.log_store.get_sqlite_log_handler"
    ) as handler_factory:
        attached = attach_sqlite_log_handler(test_logger)

    assert attached is False
    handler_factory.assert_not_called()
    assert not test_logger.handlers

    _reset_logger(test_logger)


def test_attach_sqlite_log_handler_handles_handler_errors():
    test_logger = logging.getLogger("mes_dashboard.watchdog.test.error")
    _reset_logger(test_logger)

    with patch("mes_dashboard.core.log_store.LOG_STORE_ENABLED", True), patch(
        "mes_dashboard.core.log_store.get_sqlite_log_handler",
        side_effect=RuntimeError("boom"),
    ):
        attached = attach_sqlite_log_handler(test_logger)

    assert attached is False
    assert not test_logger.handlers

    _reset_logger(test_logger)
