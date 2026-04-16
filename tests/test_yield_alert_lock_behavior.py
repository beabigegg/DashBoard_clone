# -*- coding: utf-8 -*-
"""Task 8.2 — yield_alert_dataset_cache: fail-closed lock behaviour.

Injects lock failure mid-query and verifies the user-facing error envelope
contains a "retry shortly" message rather than a raw 500.
"""

from __future__ import annotations

import pytest

import mes_dashboard.core.redis_client as redis_client_module
from mes_dashboard.services.yield_alert_dataset_cache import (
    SpoolWriteError,
    execute_primary_query,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def redis_unavailable_for_lock(monkeypatch):
    """Make try_acquire_lock return False (fail-closed) by removing Redis client."""
    monkeypatch.setattr(redis_client_module, "get_control_redis_client", lambda: None)


@pytest.fixture()
def streaming_enabled(monkeypatch):
    """Force the streaming spool path so the lock is exercised."""
    import mes_dashboard.services.yield_alert_dataset_cache as module
    monkeypatch.setattr(module, "_STREAMING_SPOOL_ENABLED", True)


@pytest.fixture()
def cache_miss(monkeypatch):
    """Ensure _get_cached_payload returns None so query proceeds past cache hit."""
    import mes_dashboard.services.yield_alert_dataset_cache as module
    monkeypatch.setattr(module, "_get_cached_payload", lambda *a, **kw: None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestYieldAlertLockFailClosed:

    def test_lock_failure_raises_spool_write_error_with_retry_message(
        self,
        redis_unavailable_for_lock,
        streaming_enabled,
        cache_miss,
        monkeypatch,
    ):
        """When the single-flight lock fails, a retry-prompt error must be raised.

        The error should surface a human-readable "retry shortly" message,
        not a raw 500 or unhandled exception.
        """
        import mes_dashboard.services.yield_alert_dataset_cache as module

        # Make the single-flight wait loop exhaust immediately (no real sleep)
        monkeypatch.setattr(module.time, "sleep", lambda _: None)

        # Keep get_cached_payload returning None so the wait loop doesn't resolve
        # (already patched by cache_miss fixture)

        with pytest.raises(SpoolWriteError) as exc_info:
            execute_primary_query(start_date="2025-01-01", end_date="2025-01-31")

        msg = str(exc_info.value).lower()
        # Must contain a retry-friendly message, not a raw stack trace keyword
        assert "retry" in msg or "稍後" in msg or "single_flight_timeout" in msg, (
            f"Expected retry message, got: {exc_info.value}"
        )
