# -*- coding: utf-8 -*-
"""Unit tests for hold_history_sql_runtime.py — DuckDB hold-history view helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock

from mes_dashboard.services.hold_history_sql_runtime import (
    _qid,
    _sql_str_literal,
    _attach_spool_view,
    _fetch_dict_rows,
    _sf,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
    _SPOOL_NAMESPACE,
)


class TestQidHelper:
    def test_quotes_identifier(self):
        assert _qid("HOLDDATE") == '"HOLDDATE"'

    def test_escapes_embedded_double_quote(self):
        result = _qid('bad"col')
        assert '""' in result


class TestSqlStrLiteralHelper:
    def test_wraps_string(self):
        assert _sql_str_literal("abc") == "'abc'"

    def test_escapes_single_quote(self):
        result = _sql_str_literal("O'clock")
        assert "''" in result


class TestAttachSpoolView:
    def test_creates_hold_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/hold.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "hold_src" in sql
        assert "read_parquet" in sql
        assert "/tmp/hold.parquet" in sql

    def test_create_or_replace_temp_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/hold.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in sql


class TestFetchDictRows:
    def test_returns_list_of_dicts(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("col_a",), ("col_b",)]
        mock_cursor.fetchall.return_value = [("val1", "val2"), ("val3", "val4")]
        mock_conn.execute.return_value = mock_cursor
        result = _fetch_dict_rows(mock_conn, "SELECT col_a, col_b FROM hold_src")
        assert result == [
            {"col_a": "val1", "col_b": "val2"},
            {"col_a": "val3", "col_b": "val4"},
        ]

    def test_empty_result_returns_empty_list(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("col_a",)]
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        result = _fetch_dict_rows(mock_conn, "SELECT col_a FROM hold_src")
        assert result == []


class TestSfHelper:
    def test_numeric_value(self):
        assert _sf(5.5) == 5.5

    def test_none_default(self):
        assert _sf(None) == 0.0

    def test_custom_default(self):
        assert _sf(None, default=-1.0) == -1.0

    def test_invalid_value(self):
        assert _sf("nope") == 0.0


class TestFallbackConstants:
    def test_disabled(self):
        assert SQL_FALLBACK_DISABLED == "hold_history_sql_disabled"

    def test_dep_missing(self):
        assert SQL_FALLBACK_DEP_MISSING == "hold_history_sql_dependency_missing"

    def test_spool_miss(self):
        assert SQL_FALLBACK_SPOOL_MISS == "hold_history_sql_spool_miss"

    def test_runtime_error(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "hold_history_sql_runtime_error"


class TestSpoolNamespace:
    def test_hold_dataset_namespace(self):
        assert _SPOOL_NAMESPACE == "hold_dataset"


class TestQueryDurationNewFields:
    """_query_duration() returns avgReleasedHours / avgOnHoldHours / maxReleasedHours / maxOnHoldHours."""

    def _make_conn(self, bucket_rows, released_rows, on_hold_rows):
        mock_conn = MagicMock()
        call_count = [0]

        def execute_side_effect(sql, params=None):
            call_count[0] += 1
            cursor = MagicMock()
            if call_count[0] == 1:  # bucket query
                cursor.description = [("bucket",), ("cnt",), ("qty",)]
                cursor.fetchall.return_value = bucket_rows
            elif call_count[0] == 2:  # released AVG/MAX
                cursor.description = [("avg_released_hours",), ("max_released_hours",)]
                cursor.fetchall.return_value = released_rows
            else:  # on-hold AVG/MAX
                cursor.description = [("avg_on_hold_hours",), ("max_on_hold_hours",)]
                cursor.fetchall.return_value = on_hold_rows
            return cursor

        mock_conn.execute.side_effect = execute_side_effect
        return mock_conn

    def test_returns_avg_max_fields(self):
        from mes_dashboard.services.hold_history_sql_runtime import _query_duration
        conn = self._make_conn(
            bucket_rows=[("<4h", 5, 500)],
            released_rows=[(3.5, 8.0)],
            on_hold_rows=[(96.0, 200.0)],
        )
        result = _query_duration(conn, hold_type="quality", record_type="new")
        assert "avgReleasedHours" in result
        assert "maxReleasedHours" in result
        assert "avgOnHoldHours" in result
        assert "maxOnHoldHours" in result
        assert result["avgReleasedHours"] == 3.5
        assert result["maxReleasedHours"] == 8.0
        assert result["avgOnHoldHours"] == 96.0
        assert result["maxOnHoldHours"] == 200.0

    def test_empty_spool_returns_zero(self):
        from mes_dashboard.services.hold_history_sql_runtime import _query_duration
        conn = self._make_conn(
            bucket_rows=[],
            released_rows=[(None, None)],
            on_hold_rows=[(None, None)],
        )
        result = _query_duration(conn, hold_type="quality", record_type="new")
        assert result["avgReleasedHours"] == 0.0
        assert result["maxReleasedHours"] == 0.0
        assert result["avgOnHoldHours"] == 0.0
        assert result["maxOnHoldHours"] == 0.0
        assert result["items"] == [
            {"range": "<4h",  "count": 0, "qty": 0, "pct": 0},
            {"range": "4-24h", "count": 0, "qty": 0, "pct": 0},
            {"range": "1-3d",  "count": 0, "qty": 0, "pct": 0},
            {"range": ">3d",   "count": 0, "qty": 0, "pct": 0},
        ]


class TestQueryTrendRepeatQuality:
    """_query_trend() includes repeatQualityHoldQty in each day."""

    def _make_trend_conn(self, dates, repeat_rows=None):
        from datetime import date, timedelta
        mock_conn = MagicMock()
        call_count = [0]

        def execute_side_effect(sql, params=None):
            call_count[0] += 1
            cursor = MagicMock()
            if call_count[0] == 1:  # dates series
                cursor.description = [("d",)]
                cursor.fetchall.return_value = [(d,) for d in dates]
            elif call_count[0] == 2:  # holdQty batch
                cursor.description = [("day_str",), ("ht",), ("v",)]
                cursor.fetchall.return_value = []
            elif call_count[0] == 3:  # newHoldQty batch
                cursor.description = [("day_str",), ("ht",), ("v",)]
                cursor.fetchall.return_value = []
            elif call_count[0] == 4:  # releaseQty batch
                cursor.description = [("day_str",), ("ht",), ("v",)]
                cursor.fetchall.return_value = []
            elif call_count[0] == 5:  # futureHoldQty batch
                cursor.description = [("day_str",), ("ht",), ("v",)]
                cursor.fetchall.return_value = []
            else:  # repeatQualityHoldQty batch
                cursor.description = [("day_str",), ("v",)]
                cursor.fetchall.return_value = repeat_rows or []
            return cursor

        mock_conn.execute.side_effect = execute_side_effect
        return mock_conn

    def test_day_map_initialized_with_repeat_quality(self):
        from mes_dashboard.services.hold_history_sql_runtime import _query_trend
        conn = self._make_trend_conn(["2026-02-01", "2026-02-02"])
        result = _query_trend(conn, start_date="2026-02-01", end_date="2026-02-02")
        day = result["days"][0]
        assert "repeatQualityHoldQty" in day["quality"]
        assert "repeatQualityHoldQty" in day["non_quality"]
        assert "repeatQualityHoldQty" in day["all"]

    def test_repeat_quality_accumulates_from_batch(self):
        from mes_dashboard.services.hold_history_sql_runtime import _query_trend
        conn = self._make_trend_conn(
            ["2026-02-01", "2026-02-02"],
            repeat_rows=[("2026-02-01", 8)],
        )
        result = _query_trend(conn, start_date="2026-02-01", end_date="2026-02-02")
        assert result["days"][0]["quality"]["repeatQualityHoldQty"] == 8
        assert result["days"][0]["all"]["repeatQualityHoldQty"] == 8
        assert result["days"][1]["quality"]["repeatQualityHoldQty"] == 0
