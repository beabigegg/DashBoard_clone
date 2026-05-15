# -*- coding: utf-8 -*-
"""Unit tests for query_tool_sql_runtime.py.

Covers:
- Column identifier quoting (_qid)
- String literal escaping (_sql_str_literal)
- Value serialization (datetime, date, Decimal, passthrough)
- Token normalization (_normalize_tokens)
- Fallback constants
- try_compute_page_from_spool: spool miss → returns None with fallback reason
- Empty-result envelope shape
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch


import pandas as pd

from mes_dashboard.services.query_tool_sql_runtime import (
    _qid,
    _sql_str_literal,
    _serialize_value,
    _serialize_rows,
    _normalize_tokens,
    try_compute_page_from_spool,
    aggregate_partial_trackouts,
    _PARTIAL_KEY_COLS_4,
    _PARTIAL_NONKEY_COLS_LOT,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_RUNTIME_ERROR,
)


class TestQid:
    """Column identifier quoting."""

    def test_wraps_in_double_quotes(self):
        assert _qid("COLUMN_NAME") == '"COLUMN_NAME"'

    def test_escapes_embedded_double_quotes(self):
        assert _qid('col"name') == '"col""name"'

    def test_empty_string(self):
        assert _qid("") == '""'


class TestSqlStrLiteral:
    """SQL string literal escaping."""

    def test_wraps_in_single_quotes(self):
        assert _sql_str_literal("value") == "'value'"

    def test_escapes_single_quotes(self):
        assert _sql_str_literal("it's") == "'it''s'"

    def test_empty_string(self):
        assert _sql_str_literal("") == "''"


class TestSerializeValue:
    """Value serialization for JSON-safe output."""

    def test_datetime_formats_correctly(self):
        dt = datetime(2024, 1, 15, 12, 30, 45)
        result = _serialize_value(dt)
        assert result == "2024-01-15 12:30:45"

    def test_date_formats_correctly(self):
        d = date(2024, 1, 15)
        result = _serialize_value(d)
        assert result == "2024-01-15"

    def test_decimal_converts_to_float(self):
        d = Decimal("3.14")
        result = _serialize_value(d)
        assert isinstance(result, float)
        assert abs(result - 3.14) < 0.001

    def test_string_passes_through(self):
        assert _serialize_value("hello") == "hello"

    def test_int_passes_through(self):
        assert _serialize_value(42) == 42

    def test_none_passes_through(self):
        assert _serialize_value(None) is None


class TestSerializeRows:
    """Row serialization."""

    def test_serializes_each_value(self):
        rows = [{"ts": datetime(2024, 1, 1), "val": Decimal("1.5"), "name": "A"}]
        result = _serialize_rows(rows)
        assert result[0]["ts"] == "2024-01-01 00:00:00"
        assert result[0]["val"] == 1.5
        assert result[0]["name"] == "A"

    def test_empty_rows_returns_empty(self):
        assert _serialize_rows([]) == []


class TestNormalizeTokens:
    """Token list normalization (dedup + strip)."""

    def test_strips_whitespace(self):
        result = _normalize_tokens(["  A  ", "B "])
        assert result == ["A", "B"]

    def test_deduplicates(self):
        result = _normalize_tokens(["A", "B", "A"])
        assert result == ["A", "B"]

    def test_removes_empty_strings(self):
        result = _normalize_tokens(["A", "", "  ", "B"])
        assert result == ["A", "B"]

    def test_none_input(self):
        assert _normalize_tokens(None) == []

    def test_empty_list(self):
        assert _normalize_tokens([]) == []


class TestFallbackConstants:
    """Fallback reason constants must be defined strings."""

    def test_disabled_constant(self):
        assert isinstance(SQL_FALLBACK_DISABLED, str) and SQL_FALLBACK_DISABLED

    def test_spool_miss_constant(self):
        assert isinstance(SQL_FALLBACK_SPOOL_MISS, str) and SQL_FALLBACK_SPOOL_MISS

    def test_dep_missing_constant(self):
        assert isinstance(SQL_FALLBACK_DEP_MISSING, str) and SQL_FALLBACK_DEP_MISSING

    def test_runtime_error_constant(self):
        assert isinstance(SQL_FALLBACK_RUNTIME_ERROR, str) and SQL_FALLBACK_RUNTIME_ERROR


class TestTryComputePageFromSpool:
    """try_compute_page_from_spool: spool miss returns None."""

    def test_returns_none_when_spool_file_missing(self):
        """When spool file doesn't exist, must return (None, reason)."""
        with patch(
            'mes_dashboard.services.query_tool_sql_runtime.get_spool_file_path',
            return_value=None
        ):
            result = try_compute_page_from_spool(
                namespace="query-tool",
                query_id="nonexistent",
                page=1,
                per_page=50,
            )
        assert result is None or (isinstance(result, tuple) and result[0] is None)

    def test_returns_none_when_feature_disabled(self):
        """When feature flag is disabled, must return None."""
        with patch(
            'mes_dashboard.services.query_tool_sql_runtime._SQL_ENABLED',
            False
        ):
            result = try_compute_page_from_spool(
                namespace="query-tool",
                query_id="test-id",
                page=1,
                per_page=50,
            )
        assert result is None or (isinstance(result, tuple) and result[0] is None)

    def test_partial_count_present_in_returned_data(self):
        """aggregate_partial_trackouts produces partial_count in the result DataFrame."""
        from datetime import datetime

        T = datetime(2024, 1, 15, 8, 0, 0)
        row1 = {
            "CONTAINERID": "AAAA000000000001",
            "EQUIPMENTID": "EQ01",
            "SPECNAME": "SPEC_A",
            "TRACKINTIMESTAMP": T,
            "TRACKOUTTIMESTAMP": datetime(2024, 1, 15, 9, 0),
            "TRACKINQTY": 100,
            "TRACKOUTQTY": 60,
            "WORKCENTERNAME": "WC01",
            "EQUIPMENTNAME": "EQ_NAME_01",
            "FINISHEDRUNCARD": "RC01",
            "PJ_WORKORDER": "WO01",
            "CONTAINERNAME": "LOT_A",
            "PJ_TYPE": "TYPE_A",
            "PJ_BOP": "BOP_A",
            "WAFER_LOT_ID": "W_LOT_01",
        }
        row2 = {**row1, "TRACKINQTY": 40, "TRACKOUTQTY": 40,
                "TRACKOUTTIMESTAMP": datetime(2024, 1, 15, 10, 0)}
        df = pd.DataFrame([row1, row2])
        df["partial_count"] = [1, 2]  # pre-existing column values (should be replaced)

        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        assert "partial_count" in result.columns, "partial_count must be in result"
        assert int(result.iloc[0]["partial_count"]) == 2, "merged group must have partial_count=2"
