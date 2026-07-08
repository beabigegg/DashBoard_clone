# -*- coding: utf-8 -*-
"""Tests for mes_dashboard.core.duckdb_runtime module."""

import pytest

from mes_dashboard.core.duckdb_runtime import (
    SpoolMissError,
    DuckDBRuntimeError,
    assert_spool_path,
    DUCKDB_MEMORY_LIMIT,
    DUCKDB_THREADS,
)


class TestSpoolMissError:
    def test_is_runtime_error(self):
        assert issubclass(SpoolMissError, RuntimeError)

    def test_message_without_query_id(self):
        with pytest.raises(SpoolMissError, match="not found or expired"):
            raise SpoolMissError("Spool result not found or expired")


class TestDuckDBRuntimeError:
    def test_is_runtime_error(self):
        assert issubclass(DuckDBRuntimeError, RuntimeError)


class TestAssertSpoolPath:
    def test_returns_valid_path(self):
        path = "/tmp/spool/test.parquet"
        assert assert_spool_path(path) == path

    def test_raises_on_none(self):
        with pytest.raises(SpoolMissError, match="not found or expired"):
            assert_spool_path(None)

    def test_raises_on_empty_string(self):
        with pytest.raises(SpoolMissError):
            assert_spool_path("")

    def test_includes_query_id_in_error(self):
        with pytest.raises(SpoolMissError, match="query_id=abc123"):
            assert_spool_path(None, query_id="abc123")

    def test_no_query_id_in_error_when_empty(self):
        with pytest.raises(SpoolMissError) as exc_info:
            assert_spool_path(None, query_id="")
        assert "query_id=" not in str(exc_info.value)


class TestPolicyConstants:
    def test_default_memory_limit(self):
        assert DUCKDB_MEMORY_LIMIT == "512MB"

    def test_default_threads(self):
        assert DUCKDB_THREADS == 2


class TestCreateHeavyQueryConnection:
    """Test connection factory with real duckdb if available."""

    @pytest.fixture(autouse=True)
    def _check_duckdb(self):
        try:
            import duckdb  # noqa: F401
        except ImportError:
            pytest.skip("duckdb not installed")

    def test_connection_returns_and_closes(self):
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
        conn = create_heavy_query_connection()
        try:
            result = conn.execute("SELECT 1 AS n").fetchone()
            assert result[0] == 1
        finally:
            conn.close()

    def test_memory_limit_applied(self):
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
        conn = create_heavy_query_connection()
        try:
            row = conn.execute("SELECT current_setting('memory_limit')").fetchone()
            assert row is not None
            # DuckDB normalises the limit string; just verify it's been set
            assert row[0] is not None
        finally:
            conn.close()

    def test_threads_applied(self):
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
        conn = create_heavy_query_connection()
        try:
            row = conn.execute("SELECT current_setting('threads')").fetchone()
            assert row is not None
            assert int(row[0]) == DUCKDB_THREADS
        finally:
            conn.close()

    def test_can_read_parquet(self, tmp_path):
        """Verify the connection can read a Parquet file (end-to-end sanity)."""
        import pandas as pd
        parquet_file = tmp_path / "test.parquet"
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        df.to_parquet(str(parquet_file))

        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
        conn = create_heavy_query_connection()
        try:
            result = conn.execute(
                f"SELECT COUNT(*) FROM read_parquet('{parquet_file}')"
            ).fetchone()
            assert result[0] == 3
        finally:
            conn.close()


class TestGetDuckDBTelemetry:
    """Regression: temp_dir_bytes must be a real number (never the old N/A),
    resolved from the connection's actual temp_directory, not the (usually
    empty) DUCKDB_TEMP_DIR env var."""

    def test_temp_dir_bytes_is_numeric_not_none(self):
        from mes_dashboard.core.duckdb_runtime import get_duckdb_telemetry

        telemetry = get_duckdb_telemetry()
        # The connection probe always resolves a temp directory (e.g. ".tmp"),
        # so bytes is measurable (0 when no spill has occurred) — never None.
        assert telemetry["temp_dir_bytes"] is not None
        assert isinstance(telemetry["temp_dir_bytes"], int)
        assert telemetry["temp_dir_bytes"] >= 0

    def test_memory_limit_state_reported(self):
        from mes_dashboard.core.duckdb_runtime import (
            get_duckdb_telemetry,
            DUCKDB_MEMORY_LIMIT,
        )

        assert get_duckdb_telemetry()["memory_limit_state"] == DUCKDB_MEMORY_LIMIT

    def test_resolve_temp_dir_returns_absolute_path(self):
        from mes_dashboard.core.duckdb_runtime import _resolve_temp_dir
        import os

        temp_dir = _resolve_temp_dir()
        assert temp_dir is not None
        assert os.path.isabs(temp_dir)

    def test_dir_size_bytes_sums_files_recursively(self, tmp_path):
        from mes_dashboard.core.duckdb_runtime import _dir_size_bytes

        (tmp_path / "a.tmp").write_bytes(b"x" * 100)
        nested = tmp_path / "sub"
        nested.mkdir()
        (nested / "b.tmp").write_bytes(b"y" * 250)

        assert _dir_size_bytes(str(tmp_path)) == 350

    def test_dir_size_bytes_missing_dir_returns_zero(self, tmp_path):
        from mes_dashboard.core.duckdb_runtime import _dir_size_bytes

        assert _dir_size_bytes(str(tmp_path / "does-not-exist")) == 0
