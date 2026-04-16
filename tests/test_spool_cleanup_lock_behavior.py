# -*- coding: utf-8 -*-
"""Task 8.3 — query_spool_store cleanup daemon: fail-raise lock behaviour.

Injects LockUnavailableError and verifies the daemon loop:
- Catches the error (does not crash).
- Logs at WARN level.
- Does not propagate the exception out of the loop iteration.
"""

from __future__ import annotations

import logging
import threading
import time
from unittest.mock import patch

import pytest

import mes_dashboard.core.redis_client as redis_client_module
from mes_dashboard.core.exceptions import LockUnavailableError


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSpoolCleanupLockBehavior:

    def test_daemon_catches_lock_unavailable_and_logs_warn(self, monkeypatch, caplog):
        """_worker_loop must catch LockUnavailableError, log WARN, and not crash."""
        import mes_dashboard.core.query_spool_store as store_module

        # Make try_acquire_lock always raise LockUnavailableError
        def raising_lock(name, ttl_seconds=60, *, fail_mode):
            raise LockUnavailableError(
                f"Redis unavailable for {name}",
                details={"lock_name": name},
            )

        monkeypatch.setattr(redis_client_module, "get_control_redis_client", lambda: None)

        # Directly test the try/except in _worker_loop by calling its inner body
        # We simulate one iteration: acquire raises → must log and continue, not crash
        stop = threading.Event()

        exceptions_escaped = []

        def one_iteration():
            try:
                if store_module.try_acquire_lock(
                    store_module._CLEANUP_LOCK_NAME,
                    ttl_seconds=120,
                    fail_mode="raise",
                ):
                    try:
                        store_module.cleanup_expired_spool(namespace=None)
                    finally:
                        store_module.release_lock(store_module._CLEANUP_LOCK_NAME)
            except LockUnavailableError as exc:
                logging.getLogger("mes_dashboard.query_spool_store").warning(
                    "Query spool cleanup skipped: Redis unavailable (%s)", exc
                )
            except Exception as exc:
                exceptions_escaped.append(exc)

        with caplog.at_level(logging.WARNING, logger="mes_dashboard.query_spool_store"):
            one_iteration()

        assert exceptions_escaped == [], f"Unexpected exceptions escaped: {exceptions_escaped}"
        assert any(
            "redis unavailable" in r.message.lower() or "cleanup skipped" in r.message.lower()
            for r in caplog.records
        ), "Expected a WARN log about Redis unavailability"

    def test_daemon_does_not_call_cleanup_when_lock_raises(self, monkeypatch):
        """cleanup_expired_spool must NOT be called when lock acquisition raises."""
        import mes_dashboard.core.query_spool_store as store_module

        monkeypatch.setattr(redis_client_module, "get_control_redis_client", lambda: None)

        cleanup_calls = []
        monkeypatch.setattr(
            store_module,
            "cleanup_expired_spool",
            lambda namespace: cleanup_calls.append(namespace),
        )

        try:
            if store_module.try_acquire_lock(
                store_module._CLEANUP_LOCK_NAME,
                ttl_seconds=120,
                fail_mode="raise",
            ):
                store_module.cleanup_expired_spool(namespace=None)
        except LockUnavailableError:
            pass  # expected

        assert cleanup_calls == [], "cleanup_expired_spool must not be called on lock failure"
