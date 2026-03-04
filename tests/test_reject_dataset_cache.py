# -*- coding: utf-8 -*-
"""Unit tests for reject_dataset_cache helpers."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from mes_dashboard.services import reject_dataset_cache as cache_svc


def test_compute_dimension_pareto_applies_policy_filters_before_grouping(monkeypatch):
    """Cached pareto should honor the same policy toggles as view/query paths."""
    df = pd.DataFrame(
        [
            {
                "CONTAINERID": "C1",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "MATERIAL",
                "PRODUCTLINENAME": "(NA)",
                "WORKCENTER_GROUP": "WB",
                "REJECT_TOTAL_QTY": 100,
                "DEFECT_QTY": 0,
                "MOVEIN_QTY": 1000,
            },
            {
                "CONTAINERID": "C2",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "LOT",
                "PRODUCTLINENAME": "PKG-A",
                "WORKCENTER_GROUP": "WB",
                "REJECT_TOTAL_QTY": 50,
                "DEFECT_QTY": 0,
                "MOVEIN_QTY": 900,
            },
        ]
    )

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    excluded_material = cache_svc.compute_dimension_pareto(
        query_id="qid-1",
        dimension="package",
        pareto_scope="all",
        include_excluded_scrap=False,
        exclude_material_scrap=True,
        exclude_pb_diode=True,
    )
    kept_all = cache_svc.compute_dimension_pareto(
        query_id="qid-1",
        dimension="package",
        pareto_scope="all",
        include_excluded_scrap=False,
        exclude_material_scrap=False,
        exclude_pb_diode=True,
    )

    excluded_labels = {item.get("reason") for item in excluded_material.get("items", [])}
    all_labels = {item.get("reason") for item in kept_all.get("items", [])}

    assert "PKG-A" in excluded_labels
    assert "(NA)" not in excluded_labels
    assert "(NA)" in all_labels


def _build_detail_filter_df():
    return pd.DataFrame(
        [
            {
                "CONTAINERID": "C1",
                "CONTAINERNAME": "LOT-001",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "TXN_TIME": pd.Timestamp("2026-02-01 08:00:00"),
                "WORKCENTERSEQUENCE_GROUP": 1,
                "WORKCENTER_GROUP": "WB",
                "WORKCENTERNAME": "WB-A",
                "SPECNAME": "SPEC-A",
                "WORKFLOWNAME": "WF-A",
                "PRIMARY_EQUIPMENTNAME": "EQ-1",
                "EQUIPMENTNAME": "EQ-1",
                "PRODUCTLINENAME": "PKG-A",
                "PJ_TYPE": "TYPE-A",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "LOT",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 30,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C2",
                "CONTAINERNAME": "LOT-002",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "TXN_TIME": pd.Timestamp("2026-02-01 09:00:00"),
                "WORKCENTERSEQUENCE_GROUP": 1,
                "WORKCENTER_GROUP": "WB",
                "WORKCENTERNAME": "WB-B",
                "SPECNAME": "SPEC-B",
                "WORKFLOWNAME": "WF-B",
                "PRIMARY_EQUIPMENTNAME": "EQ-2",
                "EQUIPMENTNAME": "EQ-2",
                "PRODUCTLINENAME": "PKG-B",
                "PJ_TYPE": "TYPE-B",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "LOT",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 20,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C3",
                "CONTAINERNAME": "LOT-003",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "TXN_TIME": pd.Timestamp("2026-02-01 10:00:00"),
                "WORKCENTERSEQUENCE_GROUP": 1,
                "WORKCENTER_GROUP": "WB",
                "WORKCENTERNAME": "WB-C",
                "SPECNAME": "SPEC-C",
                "WORKFLOWNAME": "WF-C",
                "PRIMARY_EQUIPMENTNAME": "EQ-3",
                "EQUIPMENTNAME": "EQ-3",
                "PRODUCTLINENAME": "PKG-C",
                "PJ_TYPE": "TYPE-C",
                "LOSSREASONNAME": "002_B",
                "LOSSREASON_CODE": "002_B",
                "SCRAP_OBJECTTYPE": "LOT",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 10,
                "DEFECT_QTY": 0,
            },
        ]
    )


def test_apply_view_and_export_share_same_pareto_multi_select_filter(monkeypatch):
    df = _build_detail_filter_df()

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    view_result = cache_svc.apply_view(
        query_id="qid-2",
        pareto_dimension="type",
        pareto_values=["TYPE-A", "TYPE-C"],
    )
    export_rows = cache_svc.export_csv_from_cache(
        query_id="qid-2",
        pareto_dimension="type",
        pareto_values=["TYPE-A", "TYPE-C"],
    )

    detail_items = view_result["detail"]["items"]
    detail_types = {item["PJ_TYPE"] for item in detail_items}
    exported_types = {row["TYPE"] for row in export_rows}

    assert view_result["detail"]["pagination"]["total"] == 2
    assert detail_types == {"TYPE-A", "TYPE-C"}
    assert exported_types == {"TYPE-A", "TYPE-C"}
    assert len(export_rows) == 2


def test_apply_view_prefers_cache_sql_before_legacy(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    sql_payload = {
        "analytics_raw": [{"bucket_date": "2026-02-01", "reason": "001_A"}],
        "summary": {"MOVEIN_QTY": 100},
        "detail": {
            "items": [{"CONTAINERNAME": "LOT-001"}],
            "pagination": {"page": 1, "perPage": 50, "total": 1, "totalPages": 1},
        },
    }
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **kwargs: (dict(sql_payload), {"view_source": "cache_sql"}),
    )

    def _fail_if_legacy(*_args, **_kwargs):
        raise AssertionError("legacy DataFrame fallback should not be used")

    monkeypatch.setattr(cache_svc, "_get_cached_df", _fail_if_legacy)

    result = cache_svc.apply_view(query_id="qid-view-sql-first")
    assert result["detail"]["pagination"]["total"] == 1
    assert result["detail"]["items"][0]["CONTAINERNAME"] == "LOT-001"


def test_apply_view_fail_fast_when_cache_sql_unavailable_and_legacy_disabled(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **kwargs: (None, {"view_sql_fallback_reason": "cache_sql_spool_miss"}),
    )
    monkeypatch.setattr(
        cache_svc,
        "_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED",
        False,
    )

    with pytest.raises(RuntimeError, match="cache-sql view unavailable"):
        cache_svc.apply_view(query_id="qid-view-fail-fast")


def test_export_csv_from_cache_prefers_cache_sql_stream_before_legacy(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    sql_rows = iter([
        {"LOT": "LOT-001", "TYPE": "TYPE-A"},
        {"LOT": "LOT-002", "TYPE": "TYPE-B"},
    ])
    monkeypatch.setattr(
        sql_runtime,
        "try_iter_export_rows_from_spool",
        lambda **kwargs: (sql_rows, {"export_source": "cache_sql"}),
    )

    def _fail_if_legacy(*_args, **_kwargs):
        raise AssertionError("legacy DataFrame fallback should not be used")

    monkeypatch.setattr(cache_svc, "_get_cached_df", _fail_if_legacy)

    rows = list(cache_svc.export_csv_from_cache(query_id="qid-export-sql-first") or [])
    assert len(rows) == 2
    assert rows[0]["LOT"] == "LOT-001"


def test_export_csv_from_cache_fail_fast_when_cache_sql_unavailable_and_legacy_disabled(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    monkeypatch.setattr(
        sql_runtime,
        "try_iter_export_rows_from_spool",
        lambda **kwargs: (None, {"export_sql_fallback_reason": "cache_sql_spool_miss"}),
    )
    monkeypatch.setattr(
        cache_svc,
        "_REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED",
        False,
    )

    with pytest.raises(RuntimeError, match="cache-sql export unavailable"):
        cache_svc.export_csv_from_cache(query_id="qid-export-fail-fast")


def test_apply_view_rejects_invalid_pareto_dimension(monkeypatch):
    df = _build_detail_filter_df()
    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)

    with pytest.raises(ValueError, match="不支援的 pareto_dimension"):
        cache_svc.apply_view(
            query_id="qid-3",
            pareto_dimension="invalid-dimension",
            pareto_values=["X"],
        )

    with pytest.raises(ValueError, match="不支援的 pareto_dimension"):
        cache_svc.export_csv_from_cache(
            query_id="qid-3",
            pareto_dimension="invalid-dimension",
            pareto_values=["X"],
        )


def test_compute_batch_pareto_applies_cross_filter_exclude_self(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "CONTAINERID": "C1",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "LOSSREASONNAME": "R-A",
                "PRODUCTLINENAME": "PKG-1",
                "PJ_TYPE": "TYPE-1",
                "WORKFLOWNAME": "WF-1",
                "WORKCENTER_GROUP": "WB-1",
                "PRIMARY_EQUIPMENTNAME": "EQ-1",
                "SCRAP_OBJECTTYPE": "LOT",
                "LOSSREASON_CODE": "001_A",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 100,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C2",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "LOSSREASONNAME": "R-A",
                "PRODUCTLINENAME": "PKG-2",
                "PJ_TYPE": "TYPE-2",
                "WORKFLOWNAME": "WF-2",
                "WORKCENTER_GROUP": "WB-2",
                "PRIMARY_EQUIPMENTNAME": "EQ-2",
                "SCRAP_OBJECTTYPE": "LOT",
                "LOSSREASON_CODE": "001_A",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 50,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C3",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "LOSSREASONNAME": "R-B",
                "PRODUCTLINENAME": "PKG-1",
                "PJ_TYPE": "TYPE-2",
                "WORKFLOWNAME": "WF-2",
                "WORKCENTER_GROUP": "WB-1",
                "PRIMARY_EQUIPMENTNAME": "EQ-1",
                "SCRAP_OBJECTTYPE": "LOT",
                "LOSSREASON_CODE": "002_B",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 40,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C4",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "LOSSREASONNAME": "R-B",
                "PRODUCTLINENAME": "PKG-3",
                "PJ_TYPE": "TYPE-3",
                "WORKFLOWNAME": "WF-3",
                "WORKCENTER_GROUP": "WB-3",
                "PRIMARY_EQUIPMENTNAME": "EQ-3",
                "SCRAP_OBJECTTYPE": "LOT",
                "LOSSREASON_CODE": "002_B",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 30,
                "DEFECT_QTY": 0,
            },
        ]
    )
    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    result = cache_svc.compute_batch_pareto(
        query_id="qid-batch-1",
        metric_mode="reject_total",
        pareto_scope="all",
        include_excluded_scrap=True,
        pareto_selections={
            "reason": ["R-A"],
            "type": ["TYPE-2"],
        },
    )

    reason_items = result["dimensions"]["reason"]["items"]
    type_items = result["dimensions"]["type"]["items"]
    package_items = result["dimensions"]["package"]["items"]

    assert {item["reason"] for item in reason_items} == {"R-A", "R-B"}
    assert {item["reason"] for item in type_items} == {"TYPE-1", "TYPE-2"}
    assert [item["reason"] for item in package_items] == ["PKG-2"]


def test_compute_batch_pareto_prefers_cache_sql_before_legacy(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_batch_pareto",
        lambda *args, **kwargs: (None, {"pareto_source": "legacy", "pareto_fallback_reason": "miss"}),
    )

    sql_result = {
        "dimensions": {
            "reason": {"items": [{"reason": "R-A", "metric_value": 10}], "dimension": "reason", "metric_mode": "reject_total"},
            "package": {"items": [], "dimension": "package", "metric_mode": "reject_total"},
            "type": {"items": [], "dimension": "type", "metric_mode": "reject_total"},
            "workflow": {"items": [], "dimension": "workflow", "metric_mode": "reject_total"},
            "workcenter": {"items": [], "dimension": "workcenter", "metric_mode": "reject_total"},
            "equipment": {"items": [], "dimension": "equipment", "metric_mode": "reject_total"},
        },
        "metric_mode": "reject_total",
        "pareto_scope": "all",
        "pareto_display_scope": "top20",
    }
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_batch_pareto_from_spool",
        lambda **kwargs: (dict(sql_result), {"pareto_source": "cache_sql"}),
    )

    def _fail_if_legacy(*_args, **_kwargs):
        raise AssertionError("legacy DataFrame fallback should not be used")

    monkeypatch.setattr(cache_svc, "_get_cached_df", _fail_if_legacy)

    result = cache_svc.compute_batch_pareto(
        query_id="qid-cache-sql-first",
        metric_mode="reject_total",
        pareto_scope="all",
        pareto_display_scope="top20",
    )

    assert result is not None
    assert result["dimensions"]["reason"]["items"][0]["reason"] == "R-A"
    assert result["_pareto_meta"]["pareto_source"] == "cache_sql"
    assert result["_pareto_meta"]["pareto_fallback_reason"] == "miss"


def test_compute_batch_pareto_falls_back_to_legacy_when_cache_sql_unavailable(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_batch_pareto",
        lambda *args, **kwargs: (None, {"pareto_source": "legacy", "pareto_fallback_reason": "miss"}),
    )
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_batch_pareto_from_spool",
        lambda **kwargs: (
            None,
            {
                "pareto_source": "legacy",
                "pareto_sql_fallback_reason": "cache_sql_spool_miss",
            },
        ),
    )
    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: _build_detail_filter_df())
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    result = cache_svc.compute_batch_pareto(
        query_id="qid-cache-sql-fallback",
        metric_mode="reject_total",
        pareto_scope="all",
        pareto_display_scope="top20",
    )

    assert result is not None
    assert result["dimensions"]["reason"]["items"]
    assert result["_pareto_meta"]["pareto_sql_fallback_reason"] == "cache_sql_spool_miss"


def test_compute_batch_pareto_fail_fast_when_cache_sql_unavailable_and_legacy_disabled(monkeypatch):
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_batch_pareto",
        lambda *args, **kwargs: (None, {"pareto_source": "legacy", "pareto_fallback_reason": "miss"}),
    )
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_batch_pareto_from_spool",
        lambda **kwargs: (
            None,
            {
                "pareto_source": "legacy",
                "pareto_sql_fallback_reason": "cache_sql_spool_miss",
            },
        ),
    )
    monkeypatch.setattr(
        cache_svc,
        "_REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED",
        False,
    )

    with pytest.raises(RuntimeError, match="cache-sql batch-pareto unavailable"):
        cache_svc.compute_batch_pareto(
            query_id="qid-cache-sql-fail-fast",
            metric_mode="reject_total",
            pareto_scope="all",
            pareto_display_scope="top20",
        )


def test_compute_batch_pareto_memory_guard_rejects_large_cached_dataset(monkeypatch):
    df = _build_detail_filter_df()

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(cache_svc, "_df_memory_mb", lambda _df: 128.0)
    monkeypatch.setattr(cache_svc, "_REJECT_DERIVE_MAX_INPUT_MB", 64)

    with pytest.raises(MemoryError, match="超過 64 MB 上限"):
        cache_svc.compute_batch_pareto(
            query_id="qid-batch-mem-guard",
            metric_mode="reject_total",
            pareto_scope="all",
        )


def test_compute_batch_pareto_memory_guard_allows_after_filter_narrowing(monkeypatch):
    df = _build_detail_filter_df()

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(
        cache_svc,
        "_df_memory_mb",
        lambda frame: 128.0 if len(frame.index) > 1 else 16.0,
    )
    monkeypatch.setattr(cache_svc, "_REJECT_DERIVE_MAX_INPUT_MB", 64)

    result = cache_svc.compute_batch_pareto(
        query_id="qid-batch-mem-filtered",
        metric_mode="reject_total",
        pareto_scope="all",
        packages=["PKG-A"],
    )

    assert result is not None
    assert "dimensions" in result


def test_compute_batch_pareto_memory_guard_uses_compacted_pareto_frame(monkeypatch):
    df = _build_detail_filter_df()

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)

    dim_cols = {
        "LOSSREASONNAME",
        "PRODUCTLINENAME",
        "PJ_TYPE",
        "WORKFLOWNAME",
        "WORKCENTER_GROUP",
        "PRIMARY_EQUIPMENTNAME",
    }

    def fake_df_memory_mb(frame):
        has_object_dim = any(
            col in frame.columns and str(frame[col].dtype) == "object"
            for col in dim_cols
        )
        return 128.0 if has_object_dim else 16.0

    monkeypatch.setattr(cache_svc, "_df_memory_mb", fake_df_memory_mb)
    monkeypatch.setattr(cache_svc, "_REJECT_DERIVE_MAX_INPUT_MB", 64)

    result = cache_svc.compute_batch_pareto(
        query_id="qid-batch-mem-compact",
        metric_mode="reject_total",
        pareto_scope="all",
    )

    assert result is not None
    assert "dimensions" in result


def test_apply_pareto_selection_filter_supports_multi_dimension_and_logic():
    df = _build_detail_filter_df()

    filtered = cache_svc._apply_pareto_selection_filter(
        df,
        pareto_selections={
            "reason": ["001_A"],
            "type": ["TYPE-B"],
        },
    )

    assert len(filtered) == 1
    assert set(filtered["CONTAINERNAME"].tolist()) == {"LOT-002"}


# ============================================================
# 5.9 — 365-day date range → engine decomposition, no Oracle timeout
# ============================================================


class TestEngineDecompositionDateRange:
    """Verify engine routing for long date ranges."""

    def test_365_day_range_triggers_engine(self, monkeypatch):
        """5.9: 365-day date range → chunks decomposed, engine path used."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        # Track calls via engine module (local imports inside function pull from here)
        engine_calls = {
            "decompose": 0,
            "execute": 0,
            "merge": 0,
            "chunk_count": 0,
            "parallel": 0,
            "max_rows_per_chunk": 0,
        }

        original_decompose = engine_mod.decompose_by_time_range

        def tracked_decompose(*args, **kwargs):
            engine_calls["decompose"] += 1
            return original_decompose(*args, **kwargs)

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            engine_calls["chunk_count"] = len(chunks)
            engine_calls["parallel"] = int(kwargs.get("parallel", 1))
            engine_calls["max_rows_per_chunk"] = int(kwargs.get("max_rows_per_chunk", 0))
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({
            "CONTAINERID": ["C1"],
            "LOSSREASONNAME": ["R1"],
            "REJECT_TOTAL_QTY": [10],
        })

        def fake_merge_chunks(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return result_df

        # Mock on engine module (local imports will pick these up)
        monkeypatch.setattr(engine_mod, "decompose_by_time_range", tracked_decompose)
        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks", fake_merge_chunks)
        # Mock service-level helpers
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._prepare_sql",
            lambda *a, **kw: "SELECT 1 FROM dual",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._store_df",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._get_cached_df",
            lambda _: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._apply_policy_filters",
            lambda df, **kw: df,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._build_primary_response",
            lambda qid, df, meta, ri: {"query_id": qid, "rows": len(df)},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._build_where_clause",
            lambda **kw: ("", {}, {}),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._validate_range",
            lambda *a: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.redis_clear_batch",
            lambda *a, **kw: 0,
        )

        result = cache_svc.execute_primary_query(
            mode="date_range",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )

        assert engine_calls["decompose"] == 1
        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1
        assert result["rows"] == 1

        expected_chunks = original_decompose(
            "2025-01-01",
            "2025-12-31",
            grain_days=cache_svc._REJECT_ENGINE_GRAIN_DAYS,
        )
        assert engine_calls["chunk_count"] == len(expected_chunks)
        assert engine_calls["parallel"] == cache_svc._REJECT_ENGINE_PARALLEL
        assert engine_calls["max_rows_per_chunk"] == cache_svc._REJECT_ENGINE_MAX_ROWS_PER_CHUNK

    def test_engine_chunk_uses_primary_sql_without_offset_limit(self, monkeypatch):
        """Engine chunk should execute once via primary SQL without list pagination binds."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        captured = {"df": pd.DataFrame(), "merge_kwargs": None, "params": None, "sql_name": None}

        def fake_read_sql(sql, params):
            captured["params"] = dict(params or {})
            return pd.DataFrame(
                {
                    "CONTAINERID": [f"C{i}" for i in range(5)],
                    "LOSSREASONNAME": ["R1"] * 5,
                    "REJECT_TOTAL_QTY": [1] * 5,
                }
            )

        def fake_execute_plan(chunks, query_fn, **kwargs):
            page_size = kwargs.get("max_rows_per_chunk")
            captured["df"] = query_fn(chunks[0], max_rows_per_chunk=page_size)
            return kwargs.get("query_hash", "qh")

        def fake_merge_chunks(prefix, qhash, **kwargs):
            captured["merge_kwargs"] = kwargs
            return captured["df"]

        monkeypatch.setattr(cache_svc, "_REJECT_ENGINE_MAX_ROWS_PER_CHUNK", 2)
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
        monkeypatch.setattr(
            engine_mod,
            "decompose_by_time_range",
            lambda *_a, **_kw: [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"}],
        )
        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks", fake_merge_chunks)
        monkeypatch.setattr(cache_svc, "read_sql_df", fake_read_sql)
        monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _qid: None)
        monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
        monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
        monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda df, **kw: df)
        monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: None)
        monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: 0)
        monkeypatch.setattr(
            cache_svc,
            "_build_primary_response",
            lambda qid, df, meta, ri: {"query_id": qid, "rows": len(df)},
        )
        monkeypatch.setattr(
            cache_svc,
            "_prepare_sql",
            lambda name, **kw: captured.update({"sql_name": name}) or "SELECT 1 FROM dual",
        )

        result = cache_svc.execute_primary_query(
            mode="date_range",
            start_date="2025-01-01",
            end_date="2025-03-01",
        )

        assert result["rows"] == 5
        assert captured["sql_name"] == cache_svc._REJECT_PRIMARY_SQL_TEMPLATE
        assert "offset" not in (captured["params"] or {})
        assert "limit" not in (captured["params"] or {})
        assert captured["merge_kwargs"] == {}

    def test_direct_path_uses_primary_sql_without_offset_limit(self, monkeypatch):
        """Direct path should execute dedicated primary SQL without list pagination binds."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        captured = {"params": None, "sql_name": None}

        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: False)
        monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _qid: None)
        monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
        monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
        monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda df, **kw: df)
        monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: None)
        monkeypatch.setattr(
            cache_svc,
            "_build_primary_response",
            lambda qid, df, meta, ri: {"query_id": qid, "rows": len(df)},
        )
        monkeypatch.setattr(
            cache_svc,
            "_prepare_sql",
            lambda name, **kw: captured.update({"sql_name": name}) or "SELECT 1 FROM dual",
        )

        def fake_read_sql(_sql, params):
            captured["params"] = dict(params or {})
            return pd.DataFrame({"CONTAINERID": ["C1"]})

        monkeypatch.setattr(cache_svc, "read_sql_df", fake_read_sql)

        result = cache_svc.execute_primary_query(
            mode="date_range",
            start_date="2025-01-01",
            end_date="2025-01-10",
        )

        assert result["rows"] == 1
        assert captured["sql_name"] == cache_svc._REJECT_PRIMARY_SQL_TEMPLATE
        assert captured["params"] == {"start_date": "2025-01-01", "end_date": "2025-01-10"}

    def test_short_range_skips_engine(self, monkeypatch):
        """Short date range (<= threshold) uses direct path, no engine."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        engine_calls = {"decompose": 0}

        original_decompose = engine_mod.decompose_by_time_range

        def tracked_decompose(*args, **kwargs):
            engine_calls["decompose"] += 1
            return original_decompose(*args, **kwargs)

        monkeypatch.setattr(engine_mod, "decompose_by_time_range", tracked_decompose)
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._get_cached_df",
            lambda _: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._prepare_sql",
            lambda *a, **kw: "SELECT 1 FROM dual",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.read_sql_df",
            lambda sql, params: pd.DataFrame({"CONTAINERID": ["C1"]}),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._store_df",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._apply_policy_filters",
            lambda df, **kw: df,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._build_primary_response",
            lambda qid, df, meta, ri: {"query_id": qid, "rows": len(df)},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._build_where_clause",
            lambda **kw: ("", {}, {}),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.redis_clear_batch",
            lambda *a, **kw: 0,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._validate_range",
            lambda *a: None,
        )

        result = cache_svc.execute_primary_query(
            mode="date_range",
            start_date="2025-06-01",
            end_date="2025-06-10",
        )

        assert engine_calls["decompose"] == 0  # Engine NOT used
        assert result["rows"] == 1


# ============================================================
# 5.10 — Large workorder (500+ containers) → ID batching
# ============================================================


class TestEngineDecompositionContainerIDs:
    """Verify engine routing for large container ID sets."""

    def test_large_container_set_triggers_engine(self, monkeypatch):
        """5.10: 1500 container IDs → engine ID batching activated."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        engine_calls = {"execute": 0, "merge": 0}
        fake_ids = [f"CID-{i:04d}" for i in range(1500)]

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            # Verify correct number of chunks
            assert len(chunks) == 2  # 1500 / 1000 = 2 batches
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({"CONTAINERID": fake_ids[:5]})

        def fake_merge_chunks(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return result_df

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks", fake_merge_chunks)
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.resolve_containers",
            lambda input_type, values: {
                "container_ids": fake_ids,
                "resolution_info": {"type": input_type, "count": len(fake_ids)},
            },
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._get_cached_df",
            lambda _: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._prepare_sql",
            lambda *a, **kw: "SELECT 1 FROM dual",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._store_df",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._apply_policy_filters",
            lambda df, **kw: df,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._build_primary_response",
            lambda qid, df, meta, ri: {"query_id": qid, "rows": len(df)},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._build_where_clause",
            lambda **kw: ("", {}, {}),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.redis_clear_batch",
            lambda *a, **kw: 0,
        )

        result = cache_svc.execute_primary_query(
            mode="container",
            container_input_type="workorder",
            container_values=["WO-BIG"],
        )

        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1


def test_engine_path_stores_mixed_precision_decimal_chunks_without_redis_serialization_error(
    monkeypatch, caplog
):
    """Long-range engine path should handle Decimal object columns in chunk cache."""
    import mes_dashboard.core.redis_df_store as rds
    import mes_dashboard.services.batch_query_engine as bqe

    mock_client = MagicMock()
    stored = {}
    hashes = {}

    mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
    mock_client.get.side_effect = lambda k: stored.get(k)
    mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
    mock_client.hset.side_effect = lambda k, mapping=None: hashes.setdefault(k, {}).update(mapping or {})
    mock_client.hgetall.side_effect = lambda k: hashes.get(k, {})
    mock_client.expire.return_value = None

    engine_row = pd.DataFrame(
        {
            "CONTAINERID": ["C-1", "C-2"],
            "LOSSREASONNAME": ["001_A", "002_B"],
            "REJECT_TOTAL_QTY": [10, 20],
            "REJECT_SHARE_PCT": [Decimal("12.345"), Decimal("1.2")],
            "REJECT_RATE_PCT": [Decimal("0.123456"), Decimal("9.000001")],
        }
    )

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _: None)
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *a: None)
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda df, **kw: df)
    monkeypatch.setattr(cache_svc, "_build_primary_response", lambda qid, df, meta, ri: {"rows": len(df)})
    monkeypatch.setattr(cache_svc, "read_sql_df", lambda sql, params: engine_row.copy())
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *a, **kw: 0)

    monkeypatch.setattr(rds, "REDIS_ENABLED", True)
    monkeypatch.setattr(rds, "get_redis_client", lambda: mock_client)
    monkeypatch.setattr(bqe, "get_redis_client", lambda: mock_client)
    result = cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    expected_chunks = bqe.decompose_by_time_range(
        "2025-01-01",
        "2025-12-31",
        grain_days=cache_svc._REJECT_ENGINE_GRAIN_DAYS,
    )
    assert result["rows"] == len(expected_chunks) * 2
    assert "Failed to store DataFrame in Redis" not in caplog.text
    assert any("batch:reject" in key for key in stored)


def test_large_result_spills_to_parquet_and_view_export_use_spool_fallback(monkeypatch):
    """13.8: long-range oversized result should use spool and still serve view/export."""
    spool_data = {}
    df = _build_detail_filter_df().copy()

    cache_svc._dataset_cache.clear()
    monkeypatch.setattr(cache_svc, "_redis_load_df", lambda _qid: None)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "read_sql_df", lambda sql, params: df.copy())
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(
        cache_svc,
        "_build_primary_response",
        lambda qid, result_df, meta, resolution_info: {"query_id": qid, "rows": len(result_df)},
    )

    monkeypatch.setattr(cache_svc, "_REJECT_ENGINE_SPILL_ENABLED", True)
    monkeypatch.setattr(cache_svc, "_REJECT_ENGINE_MAX_TOTAL_ROWS", 1)
    monkeypatch.setattr(cache_svc, "_REJECT_ENGINE_MAX_RESULT_MB", 1)
    monkeypatch.setattr(cache_svc, "_store_df", lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("_store_df should not be called for spill path")))
    monkeypatch.setattr(cache_svc, "_redis_delete_df", lambda *_a, **_kw: None)

    def fake_store_spooled_df(namespace, query_id, data, ttl_seconds=None):
        spool_data[(namespace, query_id)] = data.copy()
        return True

    def fake_load_spooled_df(namespace, query_id):
        stored = spool_data.get((namespace, query_id))
        return stored.copy() if stored is not None else None

    monkeypatch.setattr(cache_svc, "store_spooled_df", fake_store_spooled_df)
    monkeypatch.setattr(cache_svc, "load_spooled_df", fake_load_spooled_df)

    result = cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-01-05",
    )

    query_id = result["query_id"]
    assert result["rows"] == len(df)
    assert (cache_svc._REDIS_NAMESPACE, query_id) in spool_data

    # Force cache miss for L1/L2 and verify spool fallback serves view/export.
    cache_svc._dataset_cache.clear()
    monkeypatch.setattr(cache_svc, "_redis_load_df", lambda _qid: None)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    view_result = cache_svc.apply_view(query_id=query_id, page=1, per_page=200)
    assert view_result is not None
    assert view_result["detail"]["pagination"]["total"] == len(df)

    export_rows = cache_svc.export_csv_from_cache(query_id=query_id)
    assert export_rows is not None
    assert len(export_rows) == len(df)


def test_resolve_containers_deduplicates_container_ids(monkeypatch):
    monkeypatch.setattr(
        cache_svc,
        "_RESOLVERS",
        {
            "lot": lambda values: {
                "data": [
                    {"container_id": "CID-1"},
                    {"container_id": "CID-1"},
                    {"container_id": "CID-2"},
                ],
                "input_count": len(values),
                "not_found": [],
                "expansion_info": {"LOT%": 2},
            }
        },
    )
    monkeypatch.setenv("CONTAINER_RESOLVE_MAX_EXPANSION_PER_TOKEN", "10")
    monkeypatch.setenv("CONTAINER_RESOLVE_MAX_CONTAINER_IDS", "10")

    resolved = cache_svc.resolve_containers("lot", ["LOT%"])

    assert resolved["container_ids"] == ["CID-1", "CID-2"]
    assert resolved["resolution_info"]["resolved_count"] == 2


def test_resolve_containers_allows_oversized_expansion_and_sets_guardrail(monkeypatch):
    monkeypatch.setattr(
        cache_svc,
        "_RESOLVERS",
        {
            "lot": lambda values: {
                "data": [{"container_id": "CID-1"}],
                "input_count": len(values),
                "not_found": [],
                "expansion_info": {"GA%": 999},
            }
        },
    )
    monkeypatch.setenv("CONTAINER_RESOLVE_MAX_EXPANSION_PER_TOKEN", "50")
    monkeypatch.setenv("CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN", "2")

    resolved = cache_svc.resolve_containers("lot", ["GA%"])
    guardrail = resolved["resolution_info"].get("guardrail") or {}
    assert guardrail.get("overflow") is True
    assert len(guardrail.get("expansion_offenders") or []) == 1


def test_partial_failure_in_response_meta(monkeypatch):
    import mes_dashboard.services.batch_query_engine as engine_mod

    df = pd.DataFrame({"CONTAINERID": ["C1"], "LOSSREASONNAME": ["R1"], "REJECT_TOTAL_QTY": [1]})

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _qid: None)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: False)
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cache_svc,
        "_build_primary_response",
        lambda qid, result_df, meta, resolution_info: {"query_id": qid, "meta": meta},
    )
    monkeypatch.setattr(cache_svc, "_store_partial_failure_flag", lambda *_a, **_kw: None)

    monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        engine_mod,
        "decompose_by_time_range",
        lambda *_a, **_kw: [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"}],
    )
    monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash"))
    monkeypatch.setattr(engine_mod, "merge_chunks", lambda *a, **kw: df.copy())
    monkeypatch.setattr(
        engine_mod,
        "get_batch_progress",
        lambda *_a, **_kw: {
            "has_partial_failure": "True",
            "failed": "2",
            "failed_ranges": json.dumps([{"start": "2025-01-01", "end": "2025-01-10"}]),
        },
    )

    result = cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-03-01",
    )
    meta = result.get("meta") or {}
    assert meta.get("has_partial_failure") is True
    assert meta.get("failed_chunk_count") == 2
    assert meta.get("failed_ranges") == [{"start": "2025-01-01", "end": "2025-01-10"}]


def test_cache_hit_restores_partial_failure(monkeypatch):
    cached_df = pd.DataFrame({"CONTAINERID": ["C1"], "LOSSREASONNAME": ["R1"], "REJECT_TOTAL_QTY": [1]})

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _qid: cached_df)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(
        cache_svc,
        "_load_partial_failure_flag",
        lambda _qid: {
            "has_partial_failure": True,
            "failed_chunk_count": 3,
            "failed_ranges": [],
        },
    )
    monkeypatch.setattr(
        cache_svc,
        "_build_primary_response",
        lambda qid, result_df, meta, resolution_info: {"query_id": qid, "meta": meta},
    )

    result = cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-01-31",
    )
    meta = result.get("meta") or {}
    assert meta.get("has_partial_failure") is True
    assert meta.get("failed_chunk_count") == 3
    assert meta.get("failed_ranges") == []


@pytest.mark.parametrize(
    "store_result,expected_ttl",
    [
        (True, cache_svc._REJECT_ENGINE_SPOOL_TTL_SECONDS),
        (False, cache_svc._CACHE_TTL),
    ],
)
def test_partial_failure_ttl_matches_spool(monkeypatch, store_result, expected_ttl):
    import mes_dashboard.services.batch_query_engine as engine_mod

    df = pd.DataFrame({"CONTAINERID": ["C1"], "LOSSREASONNAME": ["R1"], "REJECT_TOTAL_QTY": [1]})
    captured = {"ttls": []}

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _qid: None)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: store_result)
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cache_svc,
        "_build_primary_response",
        lambda qid, result_df, meta, resolution_info: {"query_id": qid, "meta": meta},
    )
    monkeypatch.setattr(
        cache_svc,
        "_store_partial_failure_flag",
        lambda _qid, _failed, _ranges, ttl: captured["ttls"].append(ttl),
    )

    monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        engine_mod,
        "decompose_by_time_range",
        lambda *_a, **_kw: [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"}],
    )
    monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash"))
    monkeypatch.setattr(engine_mod, "merge_chunks", lambda *a, **kw: df.copy())
    monkeypatch.setattr(
        engine_mod,
        "get_batch_progress",
        lambda *_a, **_kw: {"has_partial_failure": "True", "failed": "1", "failed_ranges": "[]"},
    )

    cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-03-01",
    )
    assert captured["ttls"] == [expected_ttl]
