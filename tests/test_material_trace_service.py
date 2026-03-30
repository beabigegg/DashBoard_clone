# -*- coding: utf-8 -*-
"""Unit tests for material_trace_service.

Tests cover forward/reverse query logic, CONTAINERID resolution,
workcenter group enrichment/filtering, CSV export,
safeguards (memory guard, batched queries), and wildcard support.
"""

import pytest
from unittest.mock import patch, MagicMock, call

import pandas as pd

from mes_dashboard.services.material_trace_service import (
    _add_exact_or_pattern_condition,
    _check_memory_guard,
    _compute_cache_key,
    _enrich_workcenter_group,
    _IN_BATCH_SIZE,
    _is_pattern_token,
    _resolve_container_ids,
    _resolve_workcenter_names,
    execute_to_spool,
    export_csv,
    forward_query,
    reverse_query,
)
from mes_dashboard.sql import QueryBuilder

# Common patch targets for spool cache / GC
_PATCH_REDIS_LOAD = "mes_dashboard.services.material_trace_service.load_spooled_df"
_PATCH_REDIS_STORE = "mes_dashboard.services.material_trace_service.store_spooled_df"
_PATCH_GC = "mes_dashboard.services.material_trace_service.maybe_gc_collect"


# ============================================================
# Fixtures
# ============================================================

MOCK_WORKCENTER_MAPPING = {
    "WC_DB_1": {"group": "焊接_DB", "sequence": 1},
    "WC_DB_2": {"group": "焊接_DB", "sequence": 1},
    "WC_WB_1": {"group": "焊線_WB", "sequence": 2},
    "WC_MOLD_1": {"group": "封膠_Mold", "sequence": 3},
}


def _make_material_df(n=3, workcenter="WC_DB_1"):
    """Create a sample material consumption DataFrame."""
    return pd.DataFrame(
        {
            "CONTAINERID": [f"CID{i:016d}" for i in range(n)],
            "CONTAINERNAME": [f"LOT-{i:04d}" for i in range(n)],
            "PJ_WORKORDER": [f"WO-{i}" for i in range(n)],
            "WORKCENTERNAME": [workcenter] * n,
            "MATERIALPARTNAME": [f"MAT-{i}" for i in range(n)],
            "MATERIALLOTNAME": [f"MLOT-{i}" for i in range(n)],
            "VENDORLOTNUMBER": [f"VL-{i}" for i in range(n)],
            "QTYREQUIRED": [10.0] * n,
            "QTYCONSUMED": [9.5] * n,
            "EQUIPMENTNAME": [f"EQ-{i}" for i in range(n)],
            "TXNDATE": ["2025-06-01"] * n,
            "PRIMARY_CATEGORY": ["CAT_A"] * n,
            "SECONDARY_CATEGORY": ["SUB_1"] * n,
        }
    )


def _make_resolve_df(lot_names):
    """Create a DataFrame simulating DW_MES_CONTAINER resolve result."""
    rows = []
    for name in lot_names:
        rows.append({"CONTAINERID": f"CID_{name}", "CONTAINERNAME": name})
    return pd.DataFrame(rows)


# ============================================================
# 7.1 Forward LOT mode — resolve + enrichment
# ============================================================


class TestForwardLotQuery:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_lot_resolves_and_enriches(self, mock_mapping, mock_sql, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql.return_value = _make_resolve_df(["LOT-A", "LOT-B"])
        mock_sql_slow.return_value = _make_material_df(5)

        result = forward_query("lot", ["LOT-A", "LOT-B"], page=1, per_page=50)

        assert result["pagination"]["total"] == 5
        assert len(result["rows"]) == 5
        assert result["rows"][0]["WORKCENTER_GROUP"] == "焊接_DB"
        assert result["meta"] == {}
        assert result["quality_meta"]["status"] == "complete"
        assert mock_sql.call_count == 1
        assert mock_sql_slow.call_count == 1

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_lot_all_unresolved_returns_empty(self, mock_mapping, mock_sql, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql.return_value = pd.DataFrame()

        result = forward_query("lot", ["UNKNOWN-LOT"], page=1, per_page=50)

        assert result["rows"] == []
        assert result["pagination"]["total"] == 0
        assert result["meta"]["unresolved"] == ["UNKNOWN-LOT"]
        assert result["quality_meta"]["status"] == "complete"
        mock_sql_slow.assert_not_called()


# ============================================================
# 7.2 Forward work order mode
# ============================================================


class TestForwardWorkorderQuery:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_workorder_queries_directly(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        result = forward_query("workorder", ["WO-2025-001"], page=1, per_page=50)

        assert result["pagination"]["total"] == 3
        assert len(result["rows"]) == 3
        assert mock_sql_slow.call_count == 1


# ============================================================
# 7.3 Reverse query
# ============================================================


class TestReverseQuery:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_reverse_large_result_keeps_full_total(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(10001)

        result = reverse_query(["MLOT-A"], page=1, per_page=50)

        assert "truncated" not in result["meta"]
        assert result["quality_meta"]["status"] == "complete"
        assert result["pagination"]["total"] == 10001

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_reverse_no_truncation_under_limit(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(500)

        result = reverse_query(["MLOT-A"], page=1, per_page=50)

        assert "truncated" not in result["meta"]
        assert result["quality_meta"]["status"] == "complete"
        assert result["pagination"]["total"] == 500


# ============================================================
# 7.4 Workcenter group filtering
# ============================================================


class TestWorkcenterGroupFilter:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenters_for_groups")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_workcenter_group_resolves_to_names(self, mock_mapping, mock_for_groups, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_for_groups.return_value = ["WC_DB_1", "WC_DB_2"]
        mock_sql_slow.return_value = _make_material_df(3)

        result = forward_query(
            "workorder", ["WO-001"], workcenter_groups=["焊接_DB"], page=1, per_page=50
        )

        mock_for_groups.assert_called_once_with(["焊接_DB"])
        sql_call = mock_sql_slow.call_args
        sql_text = sql_call[0][0]
        assert "WORKCENTERNAME IN" in sql_text
        assert result["pagination"]["total"] == 3


# ============================================================
# 7.5 Unresolved LOT IDs
# ============================================================


class TestUnresolvedLots:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_partial_resolve_reports_unresolved(self, mock_mapping, mock_sql, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        resolve_df = pd.DataFrame(
            [{"CONTAINERID": "CID_LOT_A", "CONTAINERNAME": "LOT-A"}]
        )
        mock_sql.return_value = resolve_df
        mock_sql_slow.return_value = _make_material_df(2)

        result = forward_query("lot", ["LOT-A", "LOT-B"], page=1, per_page=50)

        assert result["meta"]["unresolved"] == ["LOT-B"]
        assert result["pagination"]["total"] == 2


# ============================================================
# Enrichment helper
# ============================================================


class TestEnrichWorkcenterGroup:
    def test_enrich_maps_correctly(self):
        df = pd.DataFrame({"WORKCENTERNAME": ["WC_DB_1", "WC_WB_1", "UNKNOWN"]})
        with patch(
            "mes_dashboard.services.material_trace_service.get_workcenter_mapping"
        ) as mock:
            mock.return_value = MOCK_WORKCENTER_MAPPING
            result = _enrich_workcenter_group(df)

        assert list(result["WORKCENTER_GROUP"]) == ["焊接_DB", "焊線_WB", ""]


# ============================================================
# CSV export
# ============================================================


class TestExportCsv:
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_export_returns_utf8_bom_csv(self, mock_mapping, mock_sql_slow, _rl, _rs):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        csv_stream, export_meta = export_csv("workorder", ["WO-001"])
        assert not isinstance(csv_stream, (bytes, bytearray))
        csv_bytes = b"".join(csv_stream)

        assert csv_bytes[:3] == b"\xef\xbb\xbf"
        csv_text = csv_bytes.decode("utf-8-sig")
        assert "LOT ID" in csv_text
        assert "料號" in csv_text
        lines = csv_text.strip().split("\n")
        assert len(lines) == 4
        assert export_meta["quality_meta"]["status"] == "complete"

    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_export_empty_result_keeps_header_contract(self, mock_mapping, mock_sql_slow, _rl, _rs):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = pd.DataFrame()

        csv_stream, export_meta = export_csv("workorder", ["WO-001"])
        csv_text = b"".join(csv_stream).decode("utf-8-sig")

        header = csv_text.splitlines()[0]
        assert "LOT ID" in header
        assert "工單" in header
        assert export_meta["quality_meta"]["status"] == "complete"


# ============================================================
# Safeguards: memory guard
# ============================================================


class TestMemoryGuard:
    def test_memory_guard_raises_on_large_df(self):
        """_check_memory_guard delegates to enforce_dataset_memory_guard; test via low limit."""
        with patch("mes_dashboard.services.material_trace_service._MAX_RESULT_MB", 0):
            df = _make_material_df(10)
            with pytest.raises(MemoryError, match="超過.*上限"):
                _check_memory_guard(df)

    def test_memory_guard_passes_small_df(self):
        df = _make_material_df(5)
        _check_memory_guard(df)

    def test_memory_guard_rss_projection(self):
        """Fence 2: reject when projected RSS exceeds limit (1100 MB).

        With a 5-row DF (~0.003 MB), projected = RSS + 0.003*1.8 ≈ RSS+0.006.
        Set RSS high enough that projected > 1100 MB.
        """
        df = _make_material_df(5)
        with patch("mes_dashboard.core.interactive_memory_guard.process_rss_mb", return_value=1100.0):
            with pytest.raises(MemoryError, match="記憶體負載"):
                _check_memory_guard(df)


# ============================================================
# Safeguards: IN-clause batching
# ============================================================


class TestInClauseBatching:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_large_input_is_batched(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        values = [f"WO-{i}" for i in range(1500)]
        result = forward_query("workorder", values, page=1, per_page=50)

        assert mock_sql_slow.call_count == 2
        assert result["pagination"]["total"] > 0


# ============================================================
# Wildcard support
# ============================================================


class TestWildcardHelpers:
    def test_is_pattern_token_with_star(self):
        assert _is_pattern_token("GA250605*") is True

    def test_is_pattern_token_with_percent(self):
        assert _is_pattern_token("GA250605%") is True

    def test_is_pattern_token_exact(self):
        assert _is_pattern_token("GA25060001-A01") is False

    def test_add_exact_or_pattern_mixed(self):
        """Mixed exact + wildcard values produce IN + LIKE conditions."""
        builder = QueryBuilder(base_sql="SELECT 1 FROM t {{ WHERE_CLAUSE }}")
        _add_exact_or_pattern_condition(builder, "col", ["EXACT-1", "WILD*"])
        sql, params = builder.build()
        assert "IN" in sql
        assert "LIKE" in sql
        # Wildcard normalized: * → %
        like_params = [v for v in params.values() if "%" in str(v)]
        assert len(like_params) == 1
        assert like_params[0] == "WILD%"


class TestWildcardResolve:
    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    def test_wildcard_resolve_generates_like(self, mock_sql):
        """Wildcard LOT names produce LIKE clause in resolve SQL."""
        mock_sql.return_value = _make_resolve_df(["LOT-A001"])

        _resolve_container_ids(["LOT-A*"])

        sql_text = mock_sql.call_args[0][0]
        assert "LIKE" in sql_text

    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    def test_wildcard_not_reported_as_unresolved(self, mock_sql):
        """Wildcard tokens that match 0 rows should NOT appear in unresolved."""
        mock_sql.return_value = pd.DataFrame()

        _, _, unresolved = _resolve_container_ids(["WILD*"])

        # Wildcard tokens are not counted as unresolved
        assert unresolved == []

    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    def test_exact_unresolved_still_reported(self, mock_sql):
        """Exact tokens that don't resolve ARE reported as unresolved."""
        mock_sql.return_value = pd.DataFrame()

        _, _, unresolved = _resolve_container_ids(["EXACT-MISSING"])

        assert unresolved == ["EXACT-MISSING"]


class TestWildcardWorkorder:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_workorder_wildcard_generates_like(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        """Wildcard work orders produce LIKE clause in query SQL."""
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        forward_query("workorder", ["WO-2025*"], page=1, per_page=50)

        sql_text = mock_sql_slow.call_args[0][0]
        assert "LIKE" in sql_text


# ============================================================
# Redis cache tests
# ============================================================


class TestRedisCache:
    def test_compute_cache_key_deterministic(self):
        """Same params produce the same cache key."""
        k1 = _compute_cache_key("workorder", ["WO-B", "WO-A"], ["G2", "G1"])
        k2 = _compute_cache_key("workorder", ["WO-A", "WO-B"], ["G1", "G2"])
        assert k1 == k2
        assert k1.startswith("mt:result:")

    def test_compute_cache_key_differs_by_mode(self):
        k1 = _compute_cache_key("lot", ["V1"])
        k2 = _compute_cache_key("workorder", ["V1"])
        assert k1 != k2

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD)
    @patch("mes_dashboard.services.material_trace_service._try_load_cached_meta")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_cache_hit_skips_oracle(self, mock_mapping, mock_meta_load, mock_redis_load, mock_redis_store, _gc):
        """When Redis has cached data, Oracle is never queried."""
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        cached = _make_material_df(5)
        cached = cached.copy()
        cached["WORKCENTER_GROUP"] = "焊接_DB"
        mock_redis_load.return_value = cached
        mock_meta_load.return_value = {
            "meta": {"truncated": True, "max_rows": 50000},
            "quality_meta": {"status": "truncated", "scope": "query", "reasons": ["row_guard_truncated"], "max_rows": 50000},
        }

        result = forward_query("workorder", ["WO-001"], page=1, per_page=50)

        assert result["pagination"]["total"] == 5
        assert len(result["rows"]) == 5
        assert result["meta"]["truncated"] is True
        assert result["quality_meta"]["status"] == "truncated"
        # redis_store should NOT be called on cache hit
        mock_redis_store.assert_not_called()

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD)
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_reverse_cache_hit_skips_oracle(self, mock_mapping, mock_redis_load, mock_redis_store, _gc):
        """Reverse query also uses Redis cache."""
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        cached = _make_material_df(3)
        cached = cached.copy()
        cached["WORKCENTER_GROUP"] = "焊接_DB"
        mock_redis_load.return_value = cached

        result = reverse_query(["MLOT-A"], page=1, per_page=50)

        assert result["pagination"]["total"] == 3
        mock_redis_store.assert_not_called()

    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD)
    @patch("mes_dashboard.services.material_trace_service._try_load_cached_meta")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_export_cache_hit_skips_oracle(self, mock_mapping, mock_meta_load, mock_redis_load, mock_redis_store):
        """Export uses cached data when available."""
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        cached = _make_material_df(3)
        cached = cached.copy()
        cached["WORKCENTER_GROUP"] = "焊接_DB"
        mock_redis_load.return_value = cached
        mock_meta_load.return_value = {
            "meta": {},
            "quality_meta": {"status": "complete", "scope": "query", "reasons": []},
        }

        csv_stream, export_meta = export_csv("workorder", ["WO-001"])
        csv_bytes = b"".join(csv_stream)

        assert csv_bytes[:3] == b"\xef\xbb\xbf"
        csv_text = csv_bytes.decode("utf-8-sig")
        assert "LOT ID" in csv_text
        assert export_meta["quality_meta"]["status"] == "complete"
        # Should NOT re-store already cached data
        mock_redis_store.assert_not_called()

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_cache_miss_stores_result(self, mock_mapping, mock_sql_slow, _rl, mock_redis_store, _gc):
        """On cache miss, result is stored in Redis after query."""
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        forward_query("workorder", ["WO-001"], page=1, per_page=50)

        mock_redis_store.assert_called_once()
        call_args = mock_redis_store.call_args
        # store_spooled_df(namespace, spool_id, df, ttl_seconds=...)
        assert call_args[0][0] == "material_trace"
        assert call_args[0][1].startswith("mt.result.")
        assert call_args[1]["ttl_seconds"] == 300


# ============================================================
# Forward large-result behavior (MT4)
# ============================================================


class TestForwardLargeResult:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_large_result_keeps_full_total(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(50001)

        result = forward_query("workorder", ["WO-001"], page=1, per_page=50)

        assert "truncated" not in result["meta"]
        assert result["quality_meta"]["status"] == "complete"
        assert result["pagination"]["total"] == 50001

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_no_truncation_under_limit(self, mock_mapping, mock_sql_slow, _rl, _rs, _gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(500)

        result = forward_query("workorder", ["WO-001"], page=1, per_page=50)

        assert "truncated" not in result["meta"]
        assert result["quality_meta"]["status"] == "complete"
        assert result["pagination"]["total"] == 500


# ============================================================
# GC collect tests (MT5)
# ============================================================


class TestGcCollect:
    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_forward_query_calls_gc(self, mock_mapping, mock_sql_slow, _rl, _rs, mock_gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        forward_query("workorder", ["WO-001"], page=1, per_page=50)

        mock_gc.assert_called_once()

    @patch(_PATCH_GC)
    @patch(_PATCH_REDIS_STORE)
    @patch(_PATCH_REDIS_LOAD, return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_reverse_query_calls_gc(self, mock_mapping, mock_sql_slow, _rl, _rs, mock_gc):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql_slow.return_value = _make_material_df(3)

        reverse_query(["MLOT-A"], page=1, per_page=50)

        mock_gc.assert_called_once()


# ---------------------------------------------------------------------------
# execute_to_spool streaming path tests (task 5.1)
# ---------------------------------------------------------------------------

class TestExecuteToSpoolStreaming:
    """execute_to_spool() must use the streaming path and NOT call _check_memory_guard."""

    @patch("mes_dashboard.services.material_trace_service._check_memory_guard")
    @patch("mes_dashboard.core.query_spool_store.register_spool_file", return_value=True)
    @patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow_iter")
    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_execute_to_spool_workorder_does_not_call_memory_guard(
        self, mock_mapping, mock_sql, mock_iter, _gsfp, _rsf, mock_guard, tmp_path
    ):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        mock_sql.return_value = None  # not used for spool path

        # Simulate iterator returning one batch of rows
        def _iter_side(sql, params, **kwargs):
            yield ["CONTAINERID", "CONTAINERNAME", "PJ_WORKORDER", "WORKCENTERNAME",
                   "MATERIALPARTNAME", "MATERIALLOTNAME", "VENDORLOTNUMBER",
                   "QTYREQUIRED", "QTYCONSUMED", "EQUIPMENTNAME", "TXNDATE",
                   "PRIMARY_CATEGORY", "SECONDARY_CATEGORY"], [
                (f"CID{i:016d}", f"LOT-{i}", "WO-1", "WC_DB_1", "MAT-1", f"MLOT-{i}",
                 f"VL-{i}", 10.0, 9.5, "EQ-1", "2025-01-01", "CAT_A", "SUB_1")
                for i in range(5)
            ]

        mock_iter.side_effect = _iter_side

        with patch("mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR", tmp_path):
            query_hash, row_count = execute_to_spool("workorder", ["WO-001"])

        assert row_count == 5
        mock_guard.assert_not_called()

    @patch("mes_dashboard.services.material_trace_service._check_memory_guard")
    @patch("mes_dashboard.core.query_spool_store.register_spool_file", return_value=True)
    @patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_trace_service.read_sql_df_slow_iter")
    @patch("mes_dashboard.services.material_trace_service.read_sql_df")
    @patch("mes_dashboard.services.material_trace_service.get_workcenter_mapping")
    def test_execute_to_spool_lot_does_not_call_memory_guard(
        self, mock_mapping, mock_sql, mock_iter, _gsfp, _rsf, mock_guard, tmp_path
    ):
        mock_mapping.return_value = MOCK_WORKCENTER_MAPPING
        # Resolve container IDs
        mock_sql.return_value = _make_resolve_df(["LOT-A"])

        def _iter_side(sql, params, **kwargs):
            yield ["CONTAINERID", "CONTAINERNAME", "PJ_WORKORDER", "WORKCENTERNAME",
                   "MATERIALPARTNAME", "MATERIALLOTNAME", "VENDORLOTNUMBER",
                   "QTYREQUIRED", "QTYCONSUMED", "EQUIPMENTNAME", "TXNDATE",
                   "PRIMARY_CATEGORY", "SECONDARY_CATEGORY"], [
                ("CID_LOT-A", "LOT-A", "WO-1", "WC_DB_1", "MAT-1", "MLOT-1",
                 "VL-1", 10.0, 9.5, "EQ-1", "2025-01-01", "CAT_A", "SUB_1"),
            ]

        mock_iter.side_effect = _iter_side

        with patch("mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR", tmp_path):
            query_hash, row_count = execute_to_spool("lot", ["LOT-A"])

        assert row_count == 1
        mock_guard.assert_not_called()
