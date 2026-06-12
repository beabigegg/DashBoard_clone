# -*- coding: utf-8 -*-
"""Tests for resource_history_duckdb_cache module (resource-history-perf).

Tests cover:
  - should_use_duckdb routing logic
  - query functions return empty DataFrame when cache not ready
  - start_duckdb_prewarm respects RESOURCE_HISTORY_PREWARM_MONTHS=0
"""
import os
import sys
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestShouldUseDuckdb:
    def test_returns_false_when_not_ready(self):
        from mes_dashboard.services.resource_history_duckdb_cache import should_use_duckdb
        assert should_use_duckdb(date.today().isoformat()) is False

    def test_returns_false_for_today_even_when_ready(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            assert m.should_use_duckdb(date.today().isoformat()) is False

    def test_returns_false_for_future_date(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            future = (date.today() + timedelta(days=1)).isoformat()
            assert m.should_use_duckdb(future) is False

    def test_returns_true_for_yesterday_when_ready(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            assert m.should_use_duckdb(yesterday) is True

    def test_returns_false_for_date_older_than_window(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True), \
             patch.object(m, "_PREWARM_MONTHS", 3):
            old_date = (date.today() - timedelta(days=3 * 31 + 10)).isoformat()
            assert m.should_use_duckdb(old_date) is False


class TestQueryFunctionsWhenNotReady:
    def test_query_base_returns_empty_when_not_ready(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_base_from_duckdb(["RES001"], "2026-01-01", "2026-03-31")
            assert df.empty

    def test_query_oee_returns_empty_when_not_ready(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_oee_from_duckdb("2026-01-01", "2026-03-31")
            assert df.empty

    def test_query_base_returns_empty_for_empty_hist_ids(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            df = m.query_base_from_duckdb([], "2026-01-01", "2026-03-31")
            assert df.empty


class TestRunPrewarmJobDisabledWhenMonthsZero:
    """Previously TestStartDuckdbPrewarm — updated for run_prewarm_job() (unify-duckdb-prewarm-rq).

    The daemon-thread wrapper start_duckdb_prewarm() has been retired.
    run_prewarm_job() is the callable used by the RQ warmup worker.
    """

    def test_disabled_when_prewarm_months_zero(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_PREWARM_MONTHS", 0), \
             patch.object(m, "_try_reuse_existing") as mock_reuse, \
             patch.object(m, "_load_and_save") as mock_load:
            m.run_prewarm_job()
            mock_reuse.assert_not_called()
            mock_load.assert_not_called()

    def test_skips_load_when_already_warm_today(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_PREWARM_MONTHS", 3), \
             patch.object(m, "_try_reuse_existing", return_value=True), \
             patch.object(m, "_load_and_save") as mock_load:
            m.run_prewarm_job()
            mock_load.assert_not_called()


# ---------------------------------------------------------------------------
# AC-4: TTL default must be 72000 (unify-duckdb-prewarm-rq)
# ---------------------------------------------------------------------------

class TestResourceSpoolTtlDefault:
    def test_spool_ttl_default_is_72000(self):
        """_CACHE_TTL in resource_dataset_cache must default to 72000 (AC-4).

        NOTE: The constant is module-level (frozen at import time).
        Do NOT override with monkeypatch.setenv — use setattr.
        This test FAILS before IP-5 is implemented.
        """
        import os
        saved = os.environ.pop("RESOURCE_HISTORY_SPOOL_TTL", None)
        try:
            from mes_dashboard.services import resource_dataset_cache
            if saved is None:
                assert resource_dataset_cache._CACHE_TTL == 72000, (
                    f"resource_dataset_cache._CACHE_TTL expected 72000, got "
                    f"{resource_dataset_cache._CACHE_TTL}. "
                    "Change default in resource_dataset_cache.py line 37 per IP-5."
                )
        finally:
            if saved is not None:
                os.environ["RESOURCE_HISTORY_SPOOL_TTL"] = saved


# ---------------------------------------------------------------------------
# AC-2: loaded_at gate — today → skip reload; yesterday → fresh load
# ---------------------------------------------------------------------------

class TestRunPrewarmJobGate:
    """AC-2: run_prewarm_job() must honour the loaded_at==today reuse gate."""

    def test_loaded_at_today_causes_refresh_skip(self):
        """When _try_reuse_existing returns True (today's cache), Oracle load must not be called."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        from unittest.mock import patch, MagicMock

        with patch.object(m, "_try_reuse_existing", return_value=True) as mock_reuse, \
             patch.object(m, "_try_lock") as mock_lock, \
             patch.object(m, "_load_and_save") as mock_load:
            m.run_prewarm_job()
            mock_reuse.assert_called_once()
            mock_load.assert_not_called()

    def test_loaded_at_yesterday_triggers_fresh_load(self):
        """When _try_reuse_existing returns False and lock is acquired, Oracle load must run."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        from unittest.mock import patch

        with patch.object(m, "_try_reuse_existing", return_value=False), \
             patch.object(m, "_try_lock", return_value=True), \
             patch.object(m, "_load_and_save") as mock_load, \
             patch.object(m, "_release_lock"):
            m.run_prewarm_job()
            mock_load.assert_called_once()

    def test_run_prewarm_job_exists_as_module_callable(self):
        """run_prewarm_job must exist as a module-level callable (IP-2)."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        assert callable(getattr(m, "run_prewarm_job", None)), (
            "resource_history_duckdb_cache.run_prewarm_job does not exist. "
            "Expose the prewarm body as a module-level callable per IP-2."
        )
