# -*- coding: utf-8 -*-
"""Tests for DB secret redaction logging filter."""

from __future__ import annotations

import logging

from mes_dashboard.core.database import (
    SecretRedactionFilter,
    install_log_redaction_filter,
    redact_connection_secrets,
)


def test_redact_connection_secrets_masks_oracle_url_password():
    raw = "connect failed: oracle+oracledb://user:super-secret@db-host:1521/service"
    masked = redact_connection_secrets(raw)

    assert "super-secret" not in masked
    assert "user:***@" in masked


def test_redact_connection_secrets_masks_db_password_env_pattern():
    raw = "Runtime config error DB_PASSWORD=myPassword123"
    masked = redact_connection_secrets(raw)

    assert "myPassword123" not in masked
    assert "DB_PASSWORD=***" in masked


def test_install_log_redaction_filter_attaches_to_logger_handlers():
    logger = logging.getLogger("mes_dashboard.test_redaction")
    logger.handlers = []
    logger.filters = []
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    logger.addHandler(handler)

    install_log_redaction_filter(logger)

    assert any(isinstance(f, SecretRedactionFilter) for f in handler.filters)
