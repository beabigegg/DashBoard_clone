# -*- coding: utf-8 -*-
"""AC-7 resilience tests: RQ absent → Oracle fallback; parquet readable past metadata TTL.

Tests confirm that if the RQ warmup worker is absent (never runs run_prewarm_job),
or if Redis spool metadata has expired but the DuckDB / parquet file still exists,
the system falls back gracefully — no crash, no silent empty result.

All tests use mocks; no Oracle or Redis connection required.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# AC-7a: RQ unavailable → Oracle fallback for resource history
# ---------------------------------------------------------------------------

class TestResourceHistoryRqFallback:
    """If run_prewarm_job was never called (RQ absent), should_use_duckdb returns False
    and callers fall back to Oracle.  No crash must occur.
    """

    def test_should_use_duckdb_returns_false_when_cache_not_ready(self):
        """When DuckDB is not warm, should_use_duckdb must return False (Oracle fallback)."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with patch.object(m, "_duckdb_ready", False), \
             patch.object(m, "_DUCKDB_PATH", Path("/nonexistent/resource_history.duckdb")):
            result = m.should_use_duckdb(yesterday)
        assert result is False, (
            "should_use_duckdb must return False when cache is not warm "
            "(RQ worker has not run run_prewarm_job yet)"
        )

    def test_query_base_returns_empty_df_when_not_warm(self):
        """query_base_from_duckdb must return empty DataFrame when not warm (no crash)."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_base_from_duckdb(["RES001"], "2026-01-01", "2026-03-31")
        assert df is not None
        assert df.empty

    def test_query_oee_returns_empty_df_when_not_warm(self):
        """query_oee_from_duckdb must return empty DataFrame when not warm (no crash)."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_oee_from_duckdb("2026-01-01", "2026-03-31")
        assert df is not None
        assert df.empty

    def test_run_prewarm_job_does_not_crash_on_lock_failure(self):
        """run_prewarm_job must not raise even when _try_lock returns False (another worker holds lock)."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_try_reuse_existing", return_value=False), \
             patch.object(m, "_try_lock", return_value=False), \
             patch.object(m, "_load_and_save") as mock_load:
            # Should not raise, should not call load
            m.run_prewarm_job()
            mock_load.assert_not_called()

    def test_run_prewarm_job_does_not_crash_on_load_exception(self):
        """run_prewarm_job must not propagate exceptions from _load_and_save."""
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_try_reuse_existing", return_value=False), \
             patch.object(m, "_try_lock", return_value=True), \
             patch.object(m, "_load_and_save", side_effect=RuntimeError("Oracle down")), \
             patch.object(m, "_release_lock"):
            # Must not raise
            m.run_prewarm_job()


# ---------------------------------------------------------------------------
# AC-7b: RQ unavailable → Oracle fallback for downtime analysis
# ---------------------------------------------------------------------------

class TestDowntimeAnalysisRqFallback:
    """If run_prewarm_job was never called (RQ absent), downtime should_use_duckdb
    returns False and callers fall back to Oracle.  No crash must occur.
    """

    def test_should_use_duckdb_returns_false_when_cache_not_ready(self):
        """When DuckDB is not warm, should_use_duckdb must return False (Oracle fallback)."""
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with patch.object(m, "_duckdb_ready", False), \
             patch.object(m, "_DUCKDB_PATH", Path("/nonexistent/downtime_analysis.duckdb")):
            result = m.should_use_duckdb(yesterday)
        assert result is False

    def test_query_base_returns_empty_df_when_not_warm(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_base_from_duckdb("2026-01-01", "2026-03-31")
        assert df is not None
        assert df.empty

    def test_query_job_returns_empty_df_when_not_warm(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_job_from_duckdb("2026-01-01", "2026-03-31")
        assert df is not None
        assert df.empty

    def test_run_prewarm_job_does_not_crash_on_lock_failure(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_try_reuse_existing", return_value=False), \
             patch.object(m, "_try_lock", return_value=False), \
             patch.object(m, "_load_and_save") as mock_load:
            m.run_prewarm_job()
            mock_load.assert_not_called()

    def test_run_prewarm_job_does_not_crash_on_load_exception(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_try_reuse_existing", return_value=False), \
             patch.object(m, "_try_lock", return_value=True), \
             patch.object(m, "_load_and_save", side_effect=RuntimeError("Oracle down")), \
             patch.object(m, "_release_lock"):
            m.run_prewarm_job()


# ---------------------------------------------------------------------------
# AC-7c: Parquet/DuckDB file readable when Redis metadata has expired
# (simulates TTL expiry: in-process cache expired but file still on disk)
# ---------------------------------------------------------------------------

class TestParquetReadableAfterMetadataTtlExpiry:
    """When Redis spool metadata has expired but the DuckDB file exists on disk,
    the lazy-init path in should_use_duckdb must still make the file readable.
    """

    def test_resource_history_lazy_init_discovers_existing_file(self):
        """should_use_duckdb triggers _try_reuse_existing when file exists but _duckdb_ready is False.

        This simulates the case where TTL expired in-process but file was not invalidated.
        """
        from mes_dashboard.services import resource_history_duckdb_cache as m
        from datetime import date, timedelta

        yesterday = (date.today() - timedelta(days=1)).isoformat()

        with patch.object(m, "_duckdb_ready", False), \
             patch.object(m, "_DUCKDB_PATH") as mock_path, \
             patch.object(m, "_try_reuse_existing", return_value=True) as mock_reuse:
            mock_path.exists.return_value = True
            # Call should_use_duckdb — it should call _try_reuse_existing
            # because the file "exists" but _duckdb_ready is False.
            m.should_use_duckdb(yesterday)
            mock_reuse.assert_called_once()

    def test_downtime_analysis_lazy_init_discovers_existing_file(self):
        """should_use_duckdb for downtime triggers _try_reuse_existing when file exists but not ready."""
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        from datetime import date, timedelta

        yesterday = (date.today() - timedelta(days=1)).isoformat()

        with patch.object(m, "_duckdb_ready", False), \
             patch.object(m, "_DUCKDB_PATH") as mock_path, \
             patch.object(m, "_try_reuse_existing", return_value=True) as mock_reuse:
            mock_path.exists.return_value = True
            m.should_use_duckdb(yesterday)
            mock_reuse.assert_called_once()
