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
import mes_dashboard.services.query_tool_service as _QT_SVC


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


# ---------------------------------------------------------------------------
# TDD: add-package-detail-tables — query-tool PRODUCTLINENAME tests
# ---------------------------------------------------------------------------


class TestPartialNonkeyColsLotContainsProductlinename:
    """IP-4 guard: _PARTIAL_NONKEY_COLS_LOT must include PRODUCTLINENAME."""

    def test_partial_nonkey_cols_lot_includes_productlinename(self):
        """QT-06 strict guard: PRODUCTLINENAME must be in _PARTIAL_NONKEY_COLS_LOT."""
        assert "PRODUCTLINENAME" in _PARTIAL_NONKEY_COLS_LOT, (
            f"PRODUCTLINENAME missing from _PARTIAL_NONKEY_COLS_LOT: {_PARTIAL_NONKEY_COLS_LOT}"
        )


class TestAggregatePartialTrackoutsPreservesProductlinename:
    """aggregate_partial_trackouts must carry PRODUCTLINENAME through consistent groups."""

    def _make_partial_rows(self, productlinename="PKG-B"):
        from datetime import datetime
        T = datetime(2024, 2, 1, 8, 0, 0)
        row1 = {
            "CONTAINERID": "AAAA000000000001",
            "EQUIPMENTID": "EQ01",
            "SPECNAME": "SPEC_A",
            "TRACKINTIMESTAMP": T,
            "TRACKOUTTIMESTAMP": datetime(2024, 2, 1, 9, 0),
            "TRACKINQTY": 100,
            "TRACKOUTQTY": 60,
            "WORKCENTERNAME": "WC01",
            "EQUIPMENTNAME": "EQ_NAME_01",
            "FINISHEDRUNCARD": "RC01",
            "PJ_WORKORDER": "WO01",
            "CONTAINERNAME": "LOT_B",
            "PJ_TYPE": "TYPE_B",
            "PJ_BOP": "BOP_B",
            "WAFER_LOT_ID": "W_LOT_01",
            "PRODUCTLINENAME": productlinename,
        }
        row2 = {**row1, "TRACKINQTY": 40, "TRACKOUTQTY": 40,
                "TRACKOUTTIMESTAMP": datetime(2024, 2, 1, 10, 0)}
        return [row1, row2]

    def test_aggregate_partial_trackouts_preserves_productlinename(self):
        """Consistent PRODUCTLINENAME across partials must survive aggregation."""
        rows = self._make_partial_rows(productlinename="PKG-B")
        df = pd.DataFrame(rows)
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        assert "PRODUCTLINENAME" in result.columns, "PRODUCTLINENAME column must be preserved"
        assert result.iloc[0]["PRODUCTLINENAME"] == "PKG-B"

    def test_divergent_productlinename_emits_raw_rows(self):
        """Divergent PRODUCTLINENAME (different per partial) triggers QT-06 strict guard → raw rows."""
        from datetime import datetime
        T = datetime(2024, 2, 1, 8, 0, 0)
        row1 = {
            "CONTAINERID": "AAAA000000000002",
            "EQUIPMENTID": "EQ02",
            "SPECNAME": "SPEC_B",
            "TRACKINTIMESTAMP": T,
            "TRACKOUTTIMESTAMP": datetime(2024, 2, 1, 9, 0),
            "TRACKINQTY": 100,
            "TRACKOUTQTY": 60,
            "WORKCENTERNAME": "WC01",
            "EQUIPMENTNAME": "EQ_NAME_02",
            "FINISHEDRUNCARD": "RC02",
            "PJ_WORKORDER": "WO02",
            "CONTAINERNAME": "LOT_C",
            "PJ_TYPE": "TYPE_C",
            "PJ_BOP": "BOP_C",
            "WAFER_LOT_ID": "W_LOT_02",
            "PRODUCTLINENAME": "PKG-X",
        }
        row2 = {**row1, "TRACKINQTY": 40, "TRACKOUTQTY": 40,
                "PRODUCTLINENAME": "PKG-Y",  # divergent!
                "TRACKOUTTIMESTAMP": datetime(2024, 2, 1, 10, 0)}
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        # Strict guard: 2 raw rows emitted, each with partial_count=1
        assert len(result) == 2
        assert all(result["partial_count"] == 1)


class TestProductlinenameTrimmedInSerialization:
    """IP-8: _serialize_rows must trim CHAR-padded PRODUCTLINENAME (AC-6)."""

    def test_productlinename_trailing_space_trimmed_in_serialization(self):
        """_serialize_rows with PRODUCTLINENAME='PKG-C  ' → stripped value."""
        rows = [{"PRODUCTLINENAME": "PKG-C  ", "CONTAINERID": "AAAA"}]
        result = _serialize_rows(rows)
        assert result[0]["PRODUCTLINENAME"] == "PKG-C", (
            f"Expected 'PKG-C', got {result[0]['PRODUCTLINENAME']!r}"
        )

    def test_productlinename_none_safe_in_serialization(self):
        """_serialize_rows with PRODUCTLINENAME=None must not crash."""
        rows = [{"PRODUCTLINENAME": None, "CONTAINERID": "BBBB"}]
        result = _serialize_rows(rows)
        assert result[0]["PRODUCTLINENAME"] is None


class TestLotHistoryResponseIncludesProductlinename:
    """lot_history query path returns PRODUCTLINENAME in response rows."""

    def test_lot_history_response_includes_productlinename(self):
        """Mock EventFetcher returning rows with PRODUCTLINENAME; response contains the field."""
        from datetime import datetime
        from unittest.mock import patch, MagicMock
        from mes_dashboard.core.query_quality_contract import build_event_fetch_result, build_quality_meta

        T = datetime(2024, 2, 1, 8, 0, 0)
        mock_rows = [{
            "CONTAINERID": "AAAA000000000001",
            "WORKCENTERNAME": "WC01",
            "EQUIPMENTID": "EQ01",
            "EQUIPMENTNAME": "EQ_NAME_01",
            "SPECNAME": "SPEC_A",
            "TRACKINTIMESTAMP": T,
            "TRACKOUTTIMESTAMP": datetime(2024, 2, 1, 9, 0),
            "TRACKINQTY": 100,
            "TRACKOUTQTY": 100,
            "FINISHEDRUNCARD": "RC01",
            "PJ_WORKORDER": "WO01",
            "CONTAINERNAME": "LOT_A",
            "PJ_TYPE": "TYPE_A",
            "PJ_BOP": "BOP_A",
            "WAFER_LOT_ID": "W_LOT_01",
            "PRODUCTLINENAME": "PKG-LOT",
        }]

        quality_meta = build_quality_meta(
            status="complete", scope="domain", domain="history", observed_rows=1
        )
        mock_fetch_result = build_event_fetch_result(
            {"AAAA000000000001": mock_rows}, quality_meta
        )

        with patch("mes_dashboard.services.event_fetcher.EventFetcher.fetch_events",
                   return_value=mock_fetch_result):
            result = _QT_SVC.get_lot_history(container_id="AAAA000000000001")

        assert result is not None
        data = result.get("data", [])
        assert len(data) > 0, "Expected at least one row in response"
        assert "PRODUCTLINENAME" in data[0], (
            f"PRODUCTLINENAME missing from lot_history response row. Keys: {list(data[0].keys())}"
        )


class TestEquipmentLotsResponseIncludesProductlinename:
    """equipment_lots query path returns PRODUCTLINENAME in response rows."""

    def test_equipment_lots_response_includes_productlinename(self):
        """Mock read_sql_df_slow returning DataFrame with PRODUCTLINENAME; response rows contain it."""
        from datetime import datetime
        from unittest.mock import patch

        mock_df = pd.DataFrame([{
            "CONTAINERID": "BBBB000000000001",
            "WORKCENTERNAME": "WC02",
            "EQUIPMENTID": "EQ02",
            "EQUIPMENTNAME": "EQ_NAME_02",
            "SPECNAME": "SPEC_B",
            "TRACKINTIMESTAMP": datetime(2024, 2, 1, 8, 0),
            "TRACKOUTTIMESTAMP": datetime(2024, 2, 1, 9, 0),
            "TRACKINQTY": 200,
            "TRACKOUTQTY": 200,
            "FINISHEDRUNCARD": "RC02",
            "PJ_WORKORDER": "WO02",
            "CONTAINERNAME": "LOT_B",
            "PJ_TYPE": "TYPE_B",
            "PJ_BOP": "BOP_B",
            "WAFER_LOT_ID": "W_LOT_02",
            "PRODUCTLINENAME": "PKG-EQ",
        }])

        with patch("mes_dashboard.services.query_tool_service.read_sql_df_slow", return_value=mock_df):
            result = _QT_SVC.get_equipment_lots(
                equipment_ids=["EQ02"],
                start_date="2024-02-01",
                end_date="2024-02-07",
            )

        assert result is not None
        data = result.get("data", [])
        assert len(data) > 0, "Expected at least one row in response"
        assert "PRODUCTLINENAME" in data[0], (
            f"PRODUCTLINENAME missing from equipment_lots response row. Keys: {list(data[0].keys())}"
        )

    def test_equipment_lots_export_csv_includes_productlinename(self):
        """_format_equipment_lots_export_rows must include PRODUCTLINENAME in output dict."""
        from mes_dashboard.routes.query_tool_routes import _format_equipment_lots_export_rows

        rows = [{
            "CONTAINERNAME": "LOT_X",
            "CONTAINERID": "XXXX000000000001",
            "WAFER_LOT_ID": "W_LOT_X",
            "PJ_TYPE": "TYPE_X",
            "PJ_BOP": "BOP_X",
            "SPECNAME": "SPEC_X",
            "PJ_WORKORDER": "WO_X",
            "TRACKINTIMESTAMP": "2024-02-01 08:00:00",
            "TRACKOUTTIMESTAMP": "2024-02-01 09:00:00",
            "TRACKINQTY": 100,
            "TRACKOUTQTY": 100,
            "EQUIPMENTNAME": "EQ_X",
            "WORKCENTERNAME": "WC_X",
            "PRODUCTLINENAME": "PKG-CSV",
        }]
        result = _format_equipment_lots_export_rows(rows)
        assert len(result) == 1
        assert "PRODUCTLINENAME" in result[0], (
            f"PRODUCTLINENAME missing from equipment_lots export row. Keys: {list(result[0].keys())}"
        )
        assert result[0]["PRODUCTLINENAME"] == "PKG-CSV"


class TestEquipmentRejectsResponseIncludesProductlinename:
    """equipment_rejects response must not drop PRODUCTLINENAME (already in SQL)."""

    def _make_rejects_df(self, productlinename="PKG-REJ"):
        return pd.DataFrame([{
            "CONTAINERID": "CCCC000000000001",
            "CONTAINERNAME": "LOT_C",
            "WORKCENTERNAME": "WC03",
            "WORKCENTER_GROUP": "WC_GRP",
            "WORKCENTERSEQUENCE_GROUP": 1,
            "PRODUCTLINENAME": productlinename,
            "PJ_FUNCTION": "FUNC_C",
            "PJ_TYPE": "TYPE_C",
            "PRODUCTNAME": "PROD_C",
            "SPECNAME": "SPEC_C",
            "LOSSREASONNAME": "REASON_C",
            "EQUIPMENTNAME": "EQ_C",
            "REJECTCOMMENT": None,
            "REJECT_QTY": 5,
            "STANDBY_QTY": 0,
            "QTYTOPROCESS_QTY": 100,
            "INPROCESS_QTY": 0,
            "PROCESSED_QTY": 95,
        }])

    def test_equipment_rejects_response_includes_productlinename(self):
        """Mock read_sql_df_slow returning PRODUCTLINENAME; _df_to_records pass-through keeps it."""
        from unittest.mock import patch

        mock_df = self._make_rejects_df()

        with patch("mes_dashboard.services.query_tool_service.read_sql_df_slow", return_value=mock_df):
            result = _QT_SVC.get_equipment_rejects(
                equipment_ids=["EQ_C"],
                start_date="2024-02-01",
                end_date="2024-02-07",
            )

        assert result is not None
        data = result.get("data", [])
        assert len(data) > 0, "Expected at least one row in response"
        assert "PRODUCTLINENAME" in data[0], (
            f"PRODUCTLINENAME missing from equipment_rejects response. Keys: {list(data[0].keys())}"
        )

    def test_equipment_rejects_export_csv_includes_productlinename(self):
        """Equipment rejects export uses _df_to_records pass-through → PRODUCTLINENAME present."""
        from unittest.mock import patch

        mock_df = self._make_rejects_df(productlinename="PKG-EXP")

        with patch("mes_dashboard.services.query_tool_service.read_sql_df_slow", return_value=mock_df):
            result = _QT_SVC.get_equipment_rejects(
                equipment_ids=["EQ_D"],
                start_date="2024-02-01",
                end_date="2024-02-07",
            )

        # The export path calls get_equipment_rejects and uses its data directly.
        data = result.get("data", [])
        assert len(data) > 0
        assert "PRODUCTLINENAME" in data[0], (
            f"PRODUCTLINENAME must survive for export. Keys: {list(data[0].keys())}"
        )
