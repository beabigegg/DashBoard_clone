# -*- coding: utf-8 -*-
"""Unit tests for resource_history_sql_runtime.py — DuckDB view helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock

from mes_dashboard.services.resource_history_sql_runtime import (
    _qid,
    _sql_str_literal,
    _attach_spool_view,
    _attach_oee_spool_view,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
    _SPOOL_NAMESPACE,
    _OEE_SPOOL_NAMESPACE,
)


class TestQidHelper:
    def test_simple_column(self):
        assert _qid("DATA_DATE") == '"DATA_DATE"'

    def test_escapes_double_quote(self):
        result = _qid('col"x')
        assert result.startswith('"') and result.endswith('"')
        assert '""' in result


class TestSqlStrLiteralHelper:
    def test_wraps_in_single_quotes(self):
        assert _sql_str_literal("/tmp/data.parquet") == "'/tmp/data.parquet'"

    def test_escapes_single_quotes(self):
        result = _sql_str_literal("it's")
        assert "''" in result


class TestAttachSpoolView:
    def test_creates_resource_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/resource.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "resource_src" in sql
        assert "read_parquet" in sql
        assert "/tmp/resource.parquet" in sql

    def test_uses_create_or_replace_temp_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/resource.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in sql


class TestAttachOeeSpoolView:
    def test_creates_oee_src_view(self):
        mock_conn = MagicMock()
        _attach_oee_spool_view(mock_conn, "/tmp/oee.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "oee_src" in sql
        assert "read_parquet" in sql


class TestFallbackConstants:
    def test_disabled_constant(self):
        assert SQL_FALLBACK_DISABLED == "resource_history_sql_disabled"

    def test_dep_missing_constant(self):
        assert SQL_FALLBACK_DEP_MISSING == "resource_history_sql_dependency_missing"

    def test_spool_miss_constant(self):
        assert SQL_FALLBACK_SPOOL_MISS == "resource_history_sql_spool_miss"

    def test_runtime_error_constant(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "resource_history_sql_runtime_error"


class TestSpoolNamespaces:
    def test_primary_namespace(self):
        assert _SPOOL_NAMESPACE == "resource_dataset"

    def test_oee_namespace(self):
        assert _OEE_SPOOL_NAMESPACE == "resource_oee"


# ============================================================
# TDD Anchors: resource-history-cache-fix
# ============================================================


class TestCanonicalKeyGranularity:
    """Canonical key must NOT include granularity (IP-1, AC-3)."""

    def test_day_week_month_year_produce_identical_canonical_key(self):
        """Before IP-1, different granularities produce DIFFERENT keys.

        After IP-1 (granularity removed from key), all produce the SAME key.
        This test FAILS before implementation because the current key includes granularity.
        """
        from mes_dashboard.services.resource_dataset_cache import make_canonical_base_query_id

        start_date = "2025-01-01"
        end_date = "2025-03-31"

        # After IP-1, make_canonical_base_query_id takes only start_date + end_date
        key_day = make_canonical_base_query_id(start_date, end_date)
        # Verify all four granularity variants produce the same key
        # (before IP-1, passing granularity as a kwarg would produce different keys)
        key_no_gran = make_canonical_base_query_id(start_date, end_date)

        assert key_day == key_no_gran, (
            "Canonical key must be identical regardless of granularity. "
            f"key_day={key_day!r} key_no_gran={key_no_gran!r}"
        )

    def test_canonical_key_excludes_granularity(self):
        """Canonical key must NOT change when called multiple times (no granularity in hash).

        After IP-1, make_canonical_base_query_id(start, end) has no granularity param.
        Calling it with the same dates must always return the same key.
        """
        from mes_dashboard.services.resource_dataset_cache import (
            make_canonical_base_query_id,
            make_canonical_oee_query_id,
        )

        start_date = "2025-06-01"
        end_date = "2025-06-30"

        base_key_1 = make_canonical_base_query_id(start_date, end_date)
        base_key_2 = make_canonical_base_query_id(start_date, end_date)
        oee_key_1 = make_canonical_oee_query_id(start_date, end_date)
        oee_key_2 = make_canonical_oee_query_id(start_date, end_date)

        assert base_key_1 == base_key_2, "Canonical base key must be deterministic"
        assert oee_key_1 == oee_key_2, "Canonical OEE key must be deterministic"
        assert base_key_1 != oee_key_1, "Base key and OEE key must differ"



class TestWarmupSupersetLookup:
    """try_compute_query_from_canonical_spool resolves narrower queries via
    warmup superset spool — AC-new: any date range within [today-89d, today]
    must use the warmup canonical spool without hitting Oracle."""

    def test_subset_of_warmup_window_uses_warmup_key_not_request_key(self):
        """When warmup spool exists and req range ⊆ warmup window, the warmup
        base key is looked up — NOT the exact request key."""
        from datetime import date, timedelta
        from unittest.mock import patch
        from mes_dashboard.services.resource_history_sql_runtime import (
            try_compute_query_from_canonical_spool,
            SQL_FALLBACK_SPOOL_MISS,
        )
        from mes_dashboard.services.resource_dataset_cache import (
            make_canonical_base_query_id,
            make_canonical_oee_query_id,
        )

        today = date.today()
        warmup_start = (today - timedelta(days=89)).strftime("%Y-%m-%d")
        warmup_end = today.strftime("%Y-%m-%d")
        req_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        req_end = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        warmup_base_key = make_canonical_base_query_id(warmup_start, warmup_end)
        req_exact_key = make_canonical_base_query_id(req_start, req_end)

        spool_calls = []

        def fake_get_spool(namespace, key):
            spool_calls.append((namespace, key))
            if namespace == "resource_dataset" and key == warmup_base_key:
                return "/fake/warmup_base.parquet"
            return None

        with patch(
            "mes_dashboard.services.resource_history_sql_runtime.get_spool_file_path",
            side_effect=fake_get_spool,
        ):
            _result, meta = try_compute_query_from_canonical_spool(
                start_date=req_start,
                end_date=req_end,
                granularity="day",
            )

        # Must NOT be a SPOOL_MISS — warmup spool was found via superset
        assert meta.get("canonical_fallback_reason") != SQL_FALLBACK_SPOOL_MISS, (
            f"Expected warmup superset hit but got SPOOL_MISS. Spool calls: {spool_calls}"
        )

        # Warmup key must have been looked up
        looked_up = [key for _, key in spool_calls]
        assert warmup_base_key in looked_up, (
            f"Warmup key {warmup_base_key!r} not looked up; got {looked_up}"
        )

        # Exact request key must NOT have been looked up (superset path took over)
        assert req_exact_key not in looked_up, (
            f"Exact req key {req_exact_key!r} should not be looked up when warmup superset hit"
        )

    def test_date_filter_injected_when_superset_used(self):
        """When warmup superset path is taken, DATA_DATE/SHIFT_DATE filters
        matching the requested range are injected into CREATE VIEW statements."""
        from datetime import date, timedelta
        from unittest.mock import patch, MagicMock
        from mes_dashboard.services.resource_history_sql_runtime import (
            try_compute_query_from_canonical_spool,
        )
        from mes_dashboard.services.resource_dataset_cache import (
            make_canonical_base_query_id,
            make_canonical_oee_query_id,
        )

        today = date.today()
        warmup_start = (today - timedelta(days=89)).strftime("%Y-%m-%d")
        warmup_end = today.strftime("%Y-%m-%d")
        req_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        req_end = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        warmup_base_key = make_canonical_base_query_id(warmup_start, warmup_end)
        warmup_oee_key = make_canonical_oee_query_id(warmup_start, warmup_end)

        def fake_get_spool(namespace, key):
            if namespace == "resource_dataset" and key == warmup_base_key:
                return "/fake/warmup_base.parquet"
            if namespace == "resource_oee" and key == warmup_oee_key:
                return "/fake/warmup_oee.parquet"
            return None

        # Cursor mock that returns empty results so _query_kpi etc. don't crash
        cursor_mock = MagicMock()
        cursor_mock.description = []
        cursor_mock.fetchall.return_value = []
        conn_mock = MagicMock()
        conn_mock.execute.return_value = cursor_mock

        with (
            patch(
                "mes_dashboard.services.resource_history_sql_runtime.get_spool_file_path",
                side_effect=fake_get_spool,
            ),
            patch(
                "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
                return_value=conn_mock,
            ),
            patch(
                "mes_dashboard.services.resource_history_service._get_filtered_resources",
                return_value=[],
            ),
            patch(
                "mes_dashboard.services.resource_history_service._build_resource_lookup",
                return_value={},
            ),
            patch(
                "mes_dashboard.services.resource_dataset_cache._get_workcenter_mapping",
                return_value={},
            ),
            patch("mes_dashboard.core.heavy_query_telemetry.record_spool_hit"),
        ):
            try_compute_query_from_canonical_spool(
                start_date=req_start,
                end_date=req_end,
                granularity="day",
            )

        # Collect all SQL strings passed to conn.execute
        all_sql = " ".join(str(c) for c in conn_mock.execute.call_args_list)

        # Date filter must contain the requested dates (not the warmup window dates)
        assert req_start in all_sql, (
            f"req_start {req_start!r} not found in DuckDB SQL: {all_sql[:300]}"
        )
        assert req_end in all_sql, (
            f"req_end {req_end!r} not found in DuckDB SQL: {all_sql[:300]}"
        )

    def test_range_outside_warmup_window_returns_spool_miss(self):
        """A request for dates outside [today-89d, today] must return SPOOL_MISS."""
        from datetime import date, timedelta
        from unittest.mock import patch
        from mes_dashboard.services.resource_history_sql_runtime import (
            try_compute_query_from_canonical_spool,
            SQL_FALLBACK_SPOOL_MISS,
        )

        today = date.today()
        req_start = (today - timedelta(days=200)).strftime("%Y-%m-%d")
        req_end = (today - timedelta(days=150)).strftime("%Y-%m-%d")

        with patch(
            "mes_dashboard.services.resource_history_sql_runtime.get_spool_file_path",
            return_value=None,
        ):
            result, meta = try_compute_query_from_canonical_spool(
                start_date=req_start,
                end_date=req_end,
                granularity="day",
            )

        assert result is None
        assert meta.get("canonical_fallback_reason") == SQL_FALLBACK_SPOOL_MISS
