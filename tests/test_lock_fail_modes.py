# -*- coding: utf-8 -*-
"""Unit tests for try_acquire_lock fail_mode semantics.

Fault-injects Redis unavailability via monkeypatch and verifies each
fail_mode value (closed, raise, open) behaves correctly.  Tests also
cover the with_distributed_lock context manager.

No real Redis connection is needed — all tests use deterministic fixtures.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import redis.exceptions

from mes_dashboard.core.exceptions import LockUnavailableError
import mes_dashboard.core.redis_client as redis_client_module
from mes_dashboard.core.redis_client import try_acquire_lock, with_distributed_lock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def redis_none(monkeypatch):
    """Simulate Redis unavailable: get_control_redis_client returns None."""
    monkeypatch.setattr(
        redis_client_module,
        "get_control_redis_client",
        lambda: None,
    )


@pytest.fixture()
def redis_conn_error(monkeypatch):
    """Simulate Redis connection error: client.set raises ConnectionError."""
    mock_client = MagicMock()
    mock_client.set.side_effect = redis.exceptions.ConnectionError("refused")
    monkeypatch.setattr(
        redis_client_module,
        "get_control_redis_client",
        lambda: mock_client,
    )
    return mock_client


@pytest.fixture()
def redis_healthy(monkeypatch):
    """Simulate healthy Redis: client.set returns truthy (lock acquired)."""
    mock_client = MagicMock()
    mock_client.set.return_value = True
    monkeypatch.setattr(
        redis_client_module,
        "get_control_redis_client",
        lambda: mock_client,
    )
    return mock_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_telemetry():
    """Clear lock telemetry counters between tests."""
    from mes_dashboard.core.heavy_query_telemetry import reset_heavy_query_telemetry
    reset_heavy_query_telemetry()


def _get_lock_telemetry():
    from mes_dashboard.core.heavy_query_telemetry import get_heavy_query_telemetry
    data = get_heavy_query_telemetry()
    return data["lock_fail_mode_triggered_total"], data["lock_fail_mode_triggered"]


# ---------------------------------------------------------------------------
# Tests: client is None (Redis disabled / unreachable)
# ---------------------------------------------------------------------------

class TestFailModeClientNone:
    """Verify fail_mode behaviour when get_control_redis_client() returns None."""

    def setup_method(self):
        _reset_telemetry()

    def test_closed_returns_false(self, redis_none):
        result = try_acquire_lock("test_lock", fail_mode="closed")
        assert result is False

    def test_closed_increments_counter(self, redis_none):
        try_acquire_lock("my_lock", fail_mode="closed")
        total, rows = _get_lock_telemetry()
        assert total == 1
        assert any(r["lock_mode"] == "my_lock:closed" for r in rows)

    def test_raise_raises_lock_unavailable_error(self, redis_none):
        with pytest.raises(LockUnavailableError) as exc_info:
            try_acquire_lock("test_lock", fail_mode="raise")
        assert exc_info.value.details["lock_name"] == "test_lock"

    def test_raise_increments_counter(self, redis_none):
        with pytest.raises(LockUnavailableError):
            try_acquire_lock("my_lock", fail_mode="raise")
        total, rows = _get_lock_telemetry()
        assert total == 1
        assert any(r["lock_mode"] == "my_lock:raise" for r in rows)

    def test_open_returns_true(self, redis_none):
        result = try_acquire_lock("test_lock", fail_mode="open")
        assert result is True

    def test_open_increments_counter(self, redis_none):
        try_acquire_lock("my_lock", fail_mode="open")
        total, rows = _get_lock_telemetry()
        assert total == 1
        assert any(r["lock_mode"] == "my_lock:open" for r in rows)

    def test_open_logs_warn(self, redis_none, caplog):
        with caplog.at_level(logging.WARNING, logger="mes_dashboard.redis"):
            try_acquire_lock("test_lock", fail_mode="open")
        assert any("fail-open" in r.message for r in caplog.records)

    def test_missing_fail_mode_raises_type_error(self, redis_none):
        with pytest.raises(TypeError):
            try_acquire_lock("test_lock")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Tests: client.set raises ConnectionError
# ---------------------------------------------------------------------------

class TestFailModeConnectionError:
    """Verify fail_mode behaviour when client.set raises ConnectionError."""

    def setup_method(self):
        _reset_telemetry()

    def test_closed_returns_false(self, redis_conn_error):
        result = try_acquire_lock("test_lock", fail_mode="closed")
        assert result is False

    def test_closed_increments_counter(self, redis_conn_error):
        try_acquire_lock("my_lock", fail_mode="closed")
        total, _ = _get_lock_telemetry()
        assert total == 1

    def test_raise_raises_lock_unavailable_error(self, redis_conn_error):
        with pytest.raises(LockUnavailableError) as exc_info:
            try_acquire_lock("test_lock", fail_mode="raise")
        assert exc_info.value.details["lock_name"] == "test_lock"
        # cause is the original ConnectionError
        assert isinstance(exc_info.value.cause, redis.exceptions.ConnectionError)

    def test_raise_increments_counter(self, redis_conn_error):
        with pytest.raises(LockUnavailableError):
            try_acquire_lock("my_lock", fail_mode="raise")
        total, rows = _get_lock_telemetry()
        assert total == 1
        assert any(r["lock_mode"] == "my_lock:raise" for r in rows)

    def test_open_returns_true(self, redis_conn_error):
        result = try_acquire_lock("test_lock", fail_mode="open")
        assert result is True

    def test_open_increments_counter(self, redis_conn_error):
        try_acquire_lock("my_lock", fail_mode="open")
        total, _ = _get_lock_telemetry()
        assert total == 1


# ---------------------------------------------------------------------------
# Tests: with_distributed_lock context manager
# ---------------------------------------------------------------------------

class TestWithDistributedLock:
    """Verify with_distributed_lock context manager behaviour."""

    def setup_method(self):
        _reset_telemetry()

    def test_happy_path_lock_acquired_and_released(self, redis_healthy, monkeypatch):
        release_calls = []
        monkeypatch.setattr(
            redis_client_module,
            "release_lock",
            lambda name: release_calls.append(name),
        )

        ran = []
        with with_distributed_lock("happy_lock", ttl_seconds=60, fail_mode="closed") as acquired:
            assert acquired is True
            ran.append(True)

        assert ran == [True], "block body must execute"
        assert release_calls == ["happy_lock"], "release_lock must be called once"

    def test_fail_closed_block_sees_false_no_release(self, redis_none, monkeypatch):
        release_calls = []
        monkeypatch.setattr(
            redis_client_module,
            "release_lock",
            lambda name: release_calls.append(name),
        )

        seen = []
        with with_distributed_lock("skip_lock", fail_mode="closed") as acquired:
            seen.append(acquired)

        assert seen == [False], "block must see False when lock unavailable"
        assert release_calls == [], "release_lock must NOT be called"

    def test_fail_raise_propagates_lock_unavailable_error(self, redis_none):
        with pytest.raises(LockUnavailableError):
            with with_distributed_lock("raise_lock", fail_mode="raise"):
                pass  # should not reach here
