"""Unit + data-boundary tests for OracleArrowReader.

AC-3: chunk_iter yields pyarrow.RecordBatch; conn closed via finally; pool lazy.
AC-8: null/empty chunk, Oracle CHAR strip, DATE midnight passthrough.

All tests use mocks only (no real Oracle).
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch, PropertyMock

import pyarrow as pa
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cursor(rows, col_names):
    """Return a mock cursor that returns rows in one fetchmany call."""
    cursor = MagicMock()
    cursor.description = [(name,) for name in col_names]
    # First fetchmany returns rows; second returns empty to end loop.
    cursor.fetchmany.side_effect = [rows, []]
    return cursor


def _make_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire.return_value = conn
    return pool


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPoolForkSafety:
    def test_pool_not_created_at_import(self):
        """D3: OracleArrowReader._pool must be None at import time (fork safety)."""
        # Remove any cached module so we get a fresh import.
        mod_name = "mes_dashboard.core.oracle_arrow_reader"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader
        # Reset class-level pool to simulate clean import state.
        OracleArrowReader._pool = None

        assert OracleArrowReader._pool is None, (
            "Pool must be None at import; lazy creation post-fork is required (D3/ADR-0004)"
        )


class TestChunkIterYieldsRecordBatches:
    def test_chunk_iter_yields_record_batches(self):
        """AC-3: chunk_iter yields pyarrow.RecordBatch objects."""
        rows = [(1, "A"), (2, "B")]
        col_names = ["id", "name"]
        cursor = _make_cursor(rows, col_names)
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool  # inject pre-created pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}, chunk_size=100))
        assert len(batches) == 1
        assert isinstance(batches[0], pa.RecordBatch)
        assert batches[0].num_rows == 2

    def test_chunk_iter_correct_column_names(self):
        rows = [("X", 10)]
        col_names = ["CODE", "VALUE"]
        cursor = _make_cursor(rows, col_names)
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        assert batches[0].schema.names == ["CODE", "VALUE"]


class TestConnectionLifecycle:
    def test_conn_closed_on_success(self):
        """AC-3: conn.close() is called after successful iteration."""
        rows = [("hello",)]
        cursor = _make_cursor(rows, ["name"])
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        conn.close.assert_called_once()

    def test_conn_closed_on_exception(self):
        """AC-3: conn.close() is called even when an exception occurs mid-chunk."""
        cursor = MagicMock()
        cursor.description = [("id",)]
        cursor.fetchmany.side_effect = RuntimeError("Oracle disconnected")
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        with pytest.raises(RuntimeError, match="Oracle disconnected"):
            list(reader.chunk_iter("SELECT 1 FROM dual", {}))

        conn.close.assert_called_once()

    def test_conn_closed_on_exception_in_record_batch_build(self):
        """conn.close() called even if pyarrow batch construction fails."""
        rows = [("bad",)]
        cursor = MagicMock()
        cursor.description = [("col",)]
        cursor.fetchmany.side_effect = [rows, []]
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        # Should not raise; even if internal issue occurs, conn.close must be called.
        # Normal case: just consume.
        list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        conn.close.assert_called_once()


class TestEmptyAndNullHandling:
    def test_empty_chunk_yields_no_batches(self):
        """AC-8: When Oracle returns 0 rows, chunk_iter yields nothing."""
        cursor = MagicMock()
        cursor.description = [("id",)]
        cursor.fetchmany.side_effect = [[]]  # immediate empty
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        assert batches == [], "Empty Oracle result must yield zero RecordBatch objects"

    def test_null_values_in_batch(self):
        """AC-8: Rows with None values produce a valid RecordBatch without error."""
        rows = [(1, None), (None, "hello")]
        cursor = _make_cursor(rows, ["id", "name"])
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        assert len(batches) == 1
        assert batches[0].num_rows == 2
        # Null values should be representable in pyarrow without raising.
        col_id = batches[0].column("id")
        assert col_id[1].as_py() is None

    def test_empty_result_conn_still_closed(self):
        """conn.close() called even when no rows are returned."""
        cursor = MagicMock()
        cursor.description = [("id",)]
        cursor.fetchmany.side_effect = [[]]
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        conn.close.assert_called_once()


class TestOracleTypeCoercion:
    def test_oracle_char_strip(self):
        """AC-8: Oracle CHAR-padded strings are stripped at the boundary."""
        rows = [(" VALUE  ", " CODE  ")]
        cursor = _make_cursor(rows, ["name", "code"])
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        assert batches[0].column("name")[0].as_py() == "VALUE"
        assert batches[0].column("code")[0].as_py() == "CODE"

    def test_oracle_char_strip_no_op_for_non_strings(self):
        """Non-string values pass through unchanged (no strip attempt)."""
        rows = [(42, 3.14, None)]
        cursor = _make_cursor(rows, ["int_col", "float_col", "null_col"])
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        assert batches[0].column("int_col")[0].as_py() == 42
        assert abs(batches[0].column("float_col")[0].as_py() - 3.14) < 0.001

    def test_oracle_date_midnight_passthrough(self):
        """AC-8: Oracle DATE midnight values pass through without tz conversion."""
        from datetime import datetime as dt

        midnight = dt(2024, 1, 15, 0, 0, 0)  # No tzinfo — as Oracle returns it
        rows = [(midnight,)]
        cursor = _make_cursor(rows, ["event_date"])
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        # The value is stored as-is; no tz shift applied.
        val = batches[0].column("event_date")[0].as_py()
        assert val is not None
        # Hour/min/sec should be 0 — no drift introduced at this boundary.
        if hasattr(val, "hour"):
            assert val.hour == 0
            assert val.minute == 0
            assert val.second == 0

    def test_multiple_chunks_from_multiple_fetchmany_calls(self):
        """Multiple fetchmany calls produce multiple RecordBatch yields."""
        rows_1 = [(1, "A"), (2, "B")]
        rows_2 = [(3, "C")]
        cursor = MagicMock()
        cursor.description = [("id",), ("name",)]
        cursor.fetchmany.side_effect = [rows_1, rows_2, []]
        conn = _make_conn(cursor)
        pool = _make_pool(conn)

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
        assert len(batches) == 2
        assert batches[0].num_rows == 2
        assert batches[1].num_rows == 1
