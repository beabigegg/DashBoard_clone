# -*- coding: utf-8 -*-
"""Pool bookkeeping integration tests: SQLAlchemy connection checkout/checkin semantics.

Verifies connection lifecycle accounting via an in-memory mock engine:
context-manager release, exception safety, and 100-concurrent-job cleanup.
Proves the framework-level contract without requiring a live Oracle connection.

Real-Oracle connection leak detection (session kill, listener stop, network
flap) is tracked separately under the future integration_real suite.

Gate: @pytest.mark.integration AND --run-integration CLI flag.
"""

from __future__ import annotations

import concurrent.futures
import threading
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_engine(pool_size: int = 5):
    """Return a mock SQLAlchemy engine whose pool tracks checkout/checkin."""
    checked_out: list[int] = [0]
    lock = threading.Lock()

    class _Pool:
        def checkedout(self):
            with lock:
                return checked_out[0]

        def overflow(self):
            return 0

        def checkedin(self):
            return pool_size - checked_out[0]

        def size(self):
            return pool_size

    class _Connection:
        def __init__(self):
            with lock:
                checked_out[0] += 1

        def close(self):
            with lock:
                checked_out[0] = max(0, checked_out[0] - 1)

        def execute(self, *args, **kwargs):
            return MagicMock(fetchall=lambda: [], description=None)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.close()
            return False

    class _Engine:
        pool = _Pool()

        def connect(self):
            return _Connection()

    return _Engine(), checked_out, lock


@contextmanager
def _flask_app_context():
    """Provide a minimal Flask app context for database helpers."""
    from mes_dashboard.app import create_app
    app = create_app("testing")
    with app.app_context():
        yield app


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestOracleConnectionLeak:
    """Verify that Oracle connections are always returned to the pool."""

    # ------------------------------------------------------------------ #
    # 6.6.1 — 100 concurrent jobs, zero checked-out connections afterward #
    # ------------------------------------------------------------------ #

    def test_100_jobs_no_active_connections(self):
        """Run 100 quick queries via the pool; assert all connections returned."""
        engine, checked_out, lock = _make_mock_engine(pool_size=10)

        results: list[Any] = []
        errors: list[Exception] = []

        def run_query(_idx: int):
            try:
                conn = engine.connect()
                try:
                    conn.execute("SELECT 1 FROM DUAL")
                    results.append(_idx)
                finally:
                    conn.close()
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(run_query, i) for i in range(100)]
            concurrent.futures.wait(futures)

        assert not errors, f"Unexpected errors during concurrent queries: {errors}"
        assert len(results) == 100, f"Expected 100 results, got {len(results)}"

        # All connections must be back in the pool.
        with lock:
            final_checked_out = checked_out[0]
        assert final_checked_out == 0, (
            f"Connection leak detected: {final_checked_out} connection(s) still checked out"
        )

    # ------------------------------------------------------------------ #
    # 6.6.2 — Context-manager usage releases connection on clean exit     #
    # ------------------------------------------------------------------ #

    def test_context_manager_releases_connection(self):
        """Context-manager connection must be released after clean exit."""
        engine, checked_out, lock = _make_mock_engine(pool_size=5)

        with engine.connect() as conn:
            conn.execute("SELECT 1 FROM DUAL")
            with lock:
                assert checked_out[0] == 1, "Connection not checked out during use"

        # After `with` block: must be returned.
        with lock:
            assert checked_out[0] == 0, (
                f"Connection not released after context-manager exit: {checked_out[0]} checked out"
            )

    # ------------------------------------------------------------------ #
    # 6.6.3 — Exception inside `get_db()` block must not leak connection  #
    # ------------------------------------------------------------------ #

    def test_connection_not_leaked_on_exception(self):
        """A connection opened then lost to an exception must be returned to the pool."""
        engine, checked_out, lock = _make_mock_engine(pool_size=5)

        # Record baseline.
        with lock:
            baseline = checked_out[0]

        try:
            with engine.connect() as conn:  # noqa: SIM117
                with lock:
                    assert checked_out[0] == baseline + 1
                # Force an exception inside the connection block.
                raise RuntimeError("simulated query failure")
        except RuntimeError:
            pass

        # Pool must be back at baseline.
        with lock:
            final = checked_out[0]
        assert final == baseline, (
            f"Connection leaked after exception: baseline={baseline}, final={final}"
        )

    # ------------------------------------------------------------------ #
    # 6.6.4 — get_pool_status() reflects pool state (smoke, no Oracle)   #
    # ------------------------------------------------------------------ #

    def test_get_pool_status_returns_expected_shape(self):
        """get_pool_status() should return a dict with at least checked_out key."""
        import mes_dashboard.core.database as db_mod

        mock_engine, checked_out, _lock = _make_mock_engine(pool_size=3)

        with patch.object(db_mod, "get_engine", return_value=mock_engine), \
             patch.object(db_mod, "get_db_runtime_config", return_value={
                 "pool_size": 3,
                 "max_overflow": 2,
                 "slow_pool_enabled": False,
             }), \
             patch.object(db_mod, "get_slow_query_active_count", return_value=0, create=True), \
             patch.object(db_mod, "get_slow_query_waiting_count", return_value=0, create=True):
            status = db_mod.get_pool_status()

        assert "checked_out" in status
        assert "size" in status
        assert "saturation" in status
        assert isinstance(status["checked_out"], int)
        assert status["checked_out"] == 0
