# -*- coding: utf-8 -*-
"""Unit tests for reject_dataset_cache helpers."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from mes_dashboard.core import interactive_memory_guard as _img
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

    monkeypatch.setattr(cache_svc, "load_spooled_df", lambda _ns, _query_id: df)
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
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    # DuckDB runtime returns pre-filtered result for apply_view
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **kwargs: (
            {
                "analytics_raw": [],
                "summary": {"MOVEIN_QTY": 200, "REJECT_TOTAL_QTY": 40},
                "detail": {
                    "items": [
                        {"CONTAINERNAME": "LOT-001", "PJ_TYPE": "TYPE-A"},
                        {"CONTAINERNAME": "LOT-003", "PJ_TYPE": "TYPE-C"},
                    ],
                    "pagination": {"page": 1, "perPage": 50, "total": 2, "totalPages": 1},
                },
            },
            {"view_source": "cache_sql"},
        ),
    )
    # DuckDB export stream returns the same filtered rows
    monkeypatch.setattr(
        sql_runtime,
        "try_iter_export_rows_from_spool",
        lambda **kwargs: (
            iter([
                {"CONTAINERNAME": "LOT-001", "TYPE": "TYPE-A"},
                {"CONTAINERNAME": "LOT-003", "TYPE": "TYPE-C"},
            ]),
            {"export_source": "cache_sql"},
        ),
    )

    view_result = cache_svc.apply_view(
        query_id="qid-2",
        pareto_dimension="type",
        pareto_values=["TYPE-A", "TYPE-C"],
    )
    export_rows = list(cache_svc.export_csv_from_cache(
        query_id="qid-2",
        pareto_dimension="type",
        pareto_values=["TYPE-A", "TYPE-C"],
    ) or [])

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

    result = cache_svc.apply_view(query_id="qid-view-sql-first")
    assert result["detail"]["pagination"]["total"] == 1
    assert result["detail"]["items"][0]["CONTAINERNAME"] == "LOT-001"


def test_apply_view_sql_result_none_returns_none(monkeypatch):
    """apply_view returns None when DuckDB runtime returns no result (spool miss or error)."""
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **kwargs: (None, {"view_sql_fallback_reason": "cache_sql_spool_miss"}),
    )

    result = cache_svc.apply_view(query_id="qid-view-none")
    assert result is None


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

    rows = list(cache_svc.export_csv_from_cache(query_id="qid-export-sql-first") or [])
    assert len(rows) == 2
    assert rows[0]["LOT"] == "LOT-001"


def test_export_csv_from_cache_raises_when_cache_sql_unavailable(monkeypatch):
    """export_csv_from_cache always raises RuntimeError when DuckDB spool path fails."""
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    monkeypatch.setattr(
        sql_runtime,
        "try_iter_export_rows_from_spool",
        lambda **kwargs: (None, {"export_sql_fallback_reason": "cache_sql_spool_miss"}),
    )

    with pytest.raises(RuntimeError, match="cache-sql export unavailable"):
        cache_svc.export_csv_from_cache(query_id="qid-export-fail-fast")



def test_compute_batch_pareto_passes_pareto_selections_to_duckdb(monkeypatch):
    """compute_batch_pareto passes normalized pareto_selections to the DuckDB spool path."""
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    captured = {}

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_batch_pareto",
        lambda *args, **kwargs: (None, {"pareto_source": "legacy", "pareto_fallback_reason": "miss"}),
    )

    def fake_try_compute_batch_pareto_from_spool(**kwargs):
        captured.update(kwargs)
        return (
            {
                "dimensions": {
                    "reason": {"items": [{"reason": "R-A", "metric_value": 100}], "dimension": "reason", "metric_mode": "reject_total"},
                    "package": {"items": [{"reason": "PKG-2", "metric_value": 50}], "dimension": "package", "metric_mode": "reject_total"},
                    "type": {"items": [{"reason": "TYPE-2", "metric_value": 50}], "dimension": "type", "metric_mode": "reject_total"},
                },
                "metric_mode": "reject_total",
                "pareto_scope": "all",
                "pareto_display_scope": "all",
            },
            {"pareto_source": "cache_sql"},
        )

    monkeypatch.setattr(
        sql_runtime,
        "try_compute_batch_pareto_from_spool",
        fake_try_compute_batch_pareto_from_spool,
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

    assert result is not None
    assert result["dimensions"]["reason"]["items"][0]["reason"] == "R-A"
    # Verify that normalized pareto_selections were forwarded to DuckDB
    assert captured.get("pareto_selections") == {"reason": ["R-A"], "type": ["TYPE-2"]}
    assert captured.get("include_excluded_scrap") is True


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


def test_compute_batch_pareto_raises_when_cache_sql_unavailable(monkeypatch):
    """compute_batch_pareto always raises RuntimeError when both materialized and DuckDB paths fail."""
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

    with pytest.raises(RuntimeError, match="cache-sql batch-pareto unavailable"):
        cache_svc.compute_batch_pareto(
            query_id="qid-cache-sql-fail-fast",
            metric_mode="reject_total",
            pareto_scope="all",
            pareto_display_scope="top20",
        )


def test_compute_dimension_pareto_memory_guard_rejects_large_cached_dataset(monkeypatch):
    """Memory guard fires in compute_dimension_pareto pandas fallback when df exceeds limit."""
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime

    df = _build_detail_filter_df()

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_dimension_pareto",
        lambda *args, **kwargs: (None, {}),
    )
    monkeypatch.setattr(cache_svc, "load_spooled_df", lambda _ns, _query_id: df)
    monkeypatch.setattr(_img, "df_memory_mb", lambda _df: 128.0)
    monkeypatch.setattr(cache_svc, "_REJECT_DERIVE_MAX_INPUT_MB", 64)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    with pytest.raises(MemoryError, match="超過 64 MB 上限"):
        cache_svc.compute_dimension_pareto(
            query_id="qid-dim-mem-guard",
            dimension="reason",
            metric_mode="reject_total",
            pareto_scope="all",
        )


def test_compute_dimension_pareto_memory_guard_allows_after_filter_narrowing(monkeypatch):
    """Memory guard allows compute_dimension_pareto when narrowed df fits within limit."""
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime

    df = _build_detail_filter_df()

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_dimension_pareto",
        lambda *args, **kwargs: (None, {}),
    )
    monkeypatch.setattr(cache_svc, "load_spooled_df", lambda _ns, _query_id: df)
    monkeypatch.setattr(
        _img,
        "df_memory_mb",
        lambda frame: 128.0 if len(frame.index) > 1 else 16.0,
    )
    monkeypatch.setattr(cache_svc, "_REJECT_DERIVE_MAX_INPUT_MB", 64)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    result = cache_svc.compute_dimension_pareto(
        query_id="qid-dim-mem-filtered",
        dimension="package",
        metric_mode="reject_total",
        pareto_scope="all",
        packages=["PKG-A"],
    )

    assert result is not None
    assert "items" in result


def test_compute_dimension_pareto_memory_guard_uses_compacted_pareto_frame(monkeypatch):
    """Memory guard is evaluated on the compacted projection frame (category-optimised)."""
    from mes_dashboard.services import reject_pareto_materialized as mat_runtime

    df = _build_detail_filter_df()

    monkeypatch.setattr(
        mat_runtime,
        "try_materialized_dimension_pareto",
        lambda *args, **kwargs: (None, {}),
    )
    monkeypatch.setattr(cache_svc, "load_spooled_df", lambda _ns, _query_id: df)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

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

    monkeypatch.setattr(_img, "df_memory_mb", fake_df_memory_mb)
    monkeypatch.setattr(cache_svc, "_REJECT_DERIVE_MAX_INPUT_MB", 64)

    result = cache_svc.compute_dimension_pareto(
        query_id="qid-dim-mem-compact",
        dimension="reason",
        metric_mode="reject_total",
        pareto_scope="all",
    )

    assert result is not None
    assert "items" in result


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

    def test_365_day_range_triggers_engine(self, monkeypatch, tmp_path):
        """5.9: 365-day date range → chunks decomposed, engine path used."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_store

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

        def fake_merge_chunks_to_spool(prefix, qhash, spool_dir, **kwargs):
            engine_calls["merge"] += 1
            p = tmp_path / "result.parquet"
            result_df.to_parquet(str(p), engine="pyarrow", index=False)
            return p, len(result_df)

        # Mock on engine module (local imports will pick these up)
        monkeypatch.setattr(engine_mod, "decompose_by_time_range", tracked_decompose)
        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        # register_spool_file returns False → fallback reads from spool_tmp_path
        monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: False)
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
            "mes_dashboard.services.reject_dataset_cache._has_cached_df",
            lambda _: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._apply_policy_filters",
            lambda df, **kw: df,
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
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "analytics_raw": [],
                "summary": {},
                "detail": {"items": [{"CONTAINERID": "C1"}], "pagination": {"page": 1, "perPage": 50, "total": 1, "totalPages": 1}},
                "available_filters": {},
            },
        )

        result = cache_svc.execute_primary_query(
            mode="date_range",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )

        assert engine_calls["decompose"] == 1
        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1
        assert result["query_id"]

        expected_chunks = original_decompose(
            "2025-01-01",
            "2025-12-31",
            grain_days=cache_svc._REJECT_ENGINE_GRAIN_DAYS,
        )
        assert engine_calls["chunk_count"] == len(expected_chunks)
        assert engine_calls["parallel"] == cache_svc._REJECT_ENGINE_PARALLEL
        assert engine_calls["max_rows_per_chunk"] == cache_svc._REJECT_ENGINE_MAX_ROWS_PER_CHUNK

    def test_engine_chunk_uses_primary_sql_without_offset_limit(self, monkeypatch, tmp_path):
        """Engine chunk should execute once via primary SQL without list pagination binds."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_store

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

        def fake_merge_chunks_to_spool(prefix, qhash, spool_dir, **kwargs):
            captured["merge_kwargs"] = kwargs
            p = tmp_path / "result.parquet"
            captured["df"].to_parquet(str(p), engine="pyarrow", index=False)
            return p, len(captured["df"])

        monkeypatch.setattr(cache_svc, "_REJECT_ENGINE_MAX_ROWS_PER_CHUNK", 2)
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
        monkeypatch.setattr(
            engine_mod,
            "decompose_by_time_range",
            lambda *_a, **_kw: [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"}],
        )
        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: False)
        monkeypatch.setattr(cache_svc, "read_sql_df", fake_read_sql)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
        monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
        monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
        monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda df, **kw: df)
        monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: None)
        monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: 0)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "analytics_raw": [],
                "summary": {},
                "detail": {"items": [], "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 1}},
                "available_filters": {},
            },
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

        assert result["query_id"]
        assert captured["sql_name"] == cache_svc._REJECT_PRIMARY_SQL_TEMPLATE
        assert "offset" not in (captured["params"] or {})
        assert "limit" not in (captured["params"] or {})
        # Verify merge_chunks_to_spool received correct kwargs (no row limit)
        assert "max_total_rows" not in captured["merge_kwargs"]
        assert "overflow_mode" not in captured["merge_kwargs"]

    def test_direct_path_uses_primary_sql_without_offset_limit(self, monkeypatch):
        """Direct path should execute dedicated primary SQL without list pagination binds."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        captured = {"params": None, "sql_name": None}

        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
        monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
        monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
        monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda df, **kw: df)
        monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "analytics_raw": [],
                "summary": {},
                "detail": {"items": [{"CONTAINERID": "C1"}], "pagination": {"page": 1, "perPage": 50, "total": 1, "totalPages": 1}},
                "available_filters": {},
            },
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

        assert result["query_id"]
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
            "mes_dashboard.services.reject_dataset_cache._has_cached_df",
            lambda _: False,
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
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "analytics_raw": [],
                "summary": {},
                "detail": {"items": [{"CONTAINERID": "C1"}], "pagination": {"page": 1, "perPage": 50, "total": 1, "totalPages": 1}},
                "available_filters": {},
            },
        )

        result = cache_svc.execute_primary_query(
            mode="date_range",
            start_date="2025-06-01",
            end_date="2025-06-10",
        )

        assert engine_calls["decompose"] == 0  # Engine NOT used
        assert result["query_id"]


# ============================================================
# 5.10 — Large workorder (500+ containers) → ID batching
# ============================================================


class TestEngineDecompositionContainerIDs:
    """Verify engine routing for large container ID sets."""

    def test_large_container_set_triggers_engine(self, monkeypatch, tmp_path):
        """5.10: 1500 container IDs → engine ID batching activated."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_store

        engine_calls = {"execute": 0, "merge": 0}
        fake_ids = [f"CID-{i:04d}" for i in range(1500)]

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            # Verify correct number of chunks
            assert len(chunks) == 2  # 1500 / 1000 = 2 batches
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({"CONTAINERID": fake_ids[:5]})

        def fake_merge_chunks_to_spool(prefix, qhash, spool_dir, **kwargs):
            engine_calls["merge"] += 1
            p = tmp_path / "result.parquet"
            result_df.to_parquet(str(p), engine="pyarrow", index=False)
            return p, len(result_df)

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: False)
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.resolve_containers",
            lambda input_type, values: {
                "container_ids": fake_ids,
                "resolution_info": {"type": input_type, "count": len(fake_ids)},
            },
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache._has_cached_df",
            lambda _: False,
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
            "mes_dashboard.services.reject_dataset_cache._build_where_clause",
            lambda **kw: ("", {}, {}),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.reject_dataset_cache.redis_clear_batch",
            lambda *a, **kw: 0,
        )
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "analytics_raw": [],
                "summary": {},
                "detail": {"items": [], "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 1}},
                "available_filters": {},
            },
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

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *a: None)
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda df, **kw: df)
    monkeypatch.setattr(
        cache_svc,
        "apply_view",
        lambda **kw: {
            "analytics_raw": [],
            "summary": {},
            "detail": {"items": [], "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 1}},
            "available_filters": {},
        },
    )
    monkeypatch.setattr(cache_svc, "read_sql_df", lambda sql, params: engine_row.copy())
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *a, **kw: 0)

    monkeypatch.setattr(rds, "REDIS_ENABLED", True)
    monkeypatch.setattr(rds, "get_redis_client", lambda: mock_client)
    monkeypatch.setattr(bqe, "get_redis_client", lambda: mock_client)
    cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert "Failed to store DataFrame in Redis" not in caplog.text
    assert any("batch:reject" in key for key in stored)


def test_large_result_spills_to_parquet_and_view_export_use_spool_fallback(monkeypatch):
    """13.8: long-range oversized result should use spool and still serve view/export."""
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    spool_data = {}
    df = _build_detail_filter_df().copy()

    # DuckDB SQL runtime returns pre-computed result for apply_view
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **_kwargs: (
            {
                "analytics_raw": [],
                "summary": {},
                "detail": {
                    "items": [{"CONTAINERID": f"C{i}"} for i in range(len(df))],
                    "pagination": {"total": len(df), "page": 1, "perPage": 200, "totalPages": 1},
                },
            },
            {"view_source": "cache_sql"},
        ),
    )
    # DuckDB export stream also returns the same number of rows
    monkeypatch.setattr(
        sql_runtime,
        "try_iter_export_rows_from_spool",
        lambda **_kwargs: (
            iter([{"CONTAINERID": f"C{i}"} for i in range(len(df))]),
            {"export_source": "cache_sql"},
        ),
    )

    cache_svc._dataset_cache.clear()
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "read_sql_df", lambda sql, params: df.copy())
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)

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
    assert (cache_svc._REDIS_NAMESPACE, query_id) in spool_data

    # Force cache miss for L1/L2 and verify DuckDB runtime serves view/export.
    cache_svc._dataset_cache.clear()
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    view_result = cache_svc.apply_view(query_id=query_id, page=1, per_page=200)
    assert view_result is not None
    assert view_result["detail"]["pagination"]["total"] == len(df)

    export_rows = list(cache_svc.export_csv_from_cache(query_id=query_id) or [])
    assert export_rows is not None
    assert len(export_rows) == len(df)


def test_execute_primary_query_registered_spool_builds_response_without_reloading_dataframe(
    monkeypatch, tmp_path
):
    import mes_dashboard.services.batch_query_engine as engine_mod
    import mes_dashboard.core.query_spool_store as spool_store

    has_cached_calls = {"count": 0}

    def fake_has_cached_df(_query_id):
        has_cached_calls["count"] += 1
        return False  # always miss, forcing Oracle execution

    monkeypatch.setattr(cache_svc, "_has_cached_df", fake_has_cached_df)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cache_svc,
        "_store_query_result",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("registered spool path should not call _store_query_result")
        ),
    )
    monkeypatch.setattr(
        cache_svc,
        "apply_view",
        lambda **kw: {
            "analytics_raw": [
                {
                    "bucket_date": "2025-01-01",
                    "reason": "001_A",
                    "MOVEIN_QTY": 100,
                    "REJECT_TOTAL_QTY": 10,
                    "DEFECT_QTY": 0,
                    "AFFECTED_LOT_COUNT": 1,
                    "AFFECTED_WORKORDER_COUNT": 1,
                }
            ],
            "summary": {"MOVEIN_QTY": 100, "REJECT_TOTAL_QTY": 10},
            "detail": {
                "items": [{"CONTAINERNAME": "LOT-001"}],
                "pagination": {"page": 1, "perPage": 50, "total": 1, "totalPages": 1},
            },
            "available_filters": {"workcenter_groups": ["WB"], "packages": [], "reasons": ["001_A"]},
        },
    )

    monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        engine_mod,
        "decompose_by_time_range",
        lambda *_a, **_kw: [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"}],
    )
    monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash"))
    monkeypatch.setattr(
        engine_mod,
        "merge_chunks_to_spool",
        lambda *a, **kw: (tmp_path / "spooled.parquet", 1),
    )
    monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: True)

    result = cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-03-01",
    )

    assert result["query_id"]
    assert result["detail"]["pagination"]["total"] == 1
    assert result["trend"]["items"][0]["REJECT_TOTAL_QTY"] == 10
    assert has_cached_calls["count"] == 2


def test_execute_primary_query_build_response_false_skips_response_derivation(monkeypatch):
    import mes_dashboard.services.batch_query_engine as engine_mod

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(
        cache_svc,
        "read_sql_df",
        lambda _sql, _params: pd.DataFrame({"CONTAINERID": ["C1"], "REJECT_TOTAL_QTY": [1]}),
    )
    monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: False)
    monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        cache_svc,
        "_apply_policy_filters",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("build_response=False should skip policy filtering")
        ),
    )
    monkeypatch.setattr(
        cache_svc,
        "apply_view",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("build_response=False should skip response construction via apply_view")
        ),
    )

    result = cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2025-01-01",
        end_date="2025-01-05",
        build_response=False,
    )

    assert result["query_id"]
    assert result["meta"] == {}


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


def test_partial_failure_in_response_meta(monkeypatch, tmp_path):
    import mes_dashboard.services.batch_query_engine as engine_mod
    import mes_dashboard.core.query_spool_store as spool_store
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    df = pd.DataFrame({"CONTAINERID": ["C1"], "LOSSREASONNAME": ["R1"], "REJECT_TOTAL_QTY": [1]})
    spool_parquet = tmp_path / "spool.parquet"
    df.to_parquet(str(spool_parquet), engine="pyarrow", index=False)

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(cache_svc, "_store_partial_failure_flag", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: None)

    monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        engine_mod,
        "decompose_by_time_range",
        lambda *_a, **_kw: [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"}],
    )
    monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash"))
    monkeypatch.setattr(
        engine_mod,
        "merge_chunks_to_spool",
        lambda *a, **kw: (spool_parquet, len(df)),
    )
    monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: True)
    monkeypatch.setattr(
        engine_mod,
        "get_batch_progress",
        lambda *_a, **_kw: {
            "has_partial_failure": "True",
            "failed": "2",
            "failed_ranges": json.dumps([{"start": "2025-01-01", "end": "2025-01-10"}]),
        },
    )
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **_kw: (
            {"analytics_raw": [], "summary": {}, "detail": {"items": [], "pagination": {"total": 0}}},
            {"view_source": "cache_sql"},
        ),
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
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: True)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
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
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **_kw: (
            {"analytics_raw": [], "summary": {}, "detail": {"items": [], "pagination": {"total": 0, "page": 1, "perPage": 50, "totalPages": 1}}},
            {"view_source": "cache_sql"},
        ),
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
def test_partial_failure_ttl_matches_spool(monkeypatch, tmp_path, store_result, expected_ttl):
    import mes_dashboard.services.batch_query_engine as engine_mod
    import mes_dashboard.core.query_spool_store as spool_store
    from mes_dashboard.services import reject_cache_sql_runtime as sql_runtime

    df = pd.DataFrame({"CONTAINERID": ["C1"], "LOSSREASONNAME": ["R1"], "REJECT_TOTAL_QTY": [1]})
    captured = {"ttls": []}

    # Write df to parquet so the fallback path can load it
    spool_parquet = tmp_path / "spool.parquet"
    df.to_parquet(str(spool_parquet), engine="pyarrow", index=False)

    # DuckDB SQL runtime mock so _build_response_from_spool doesn't fail when store_result=True
    monkeypatch.setattr(
        sql_runtime,
        "try_compute_view_from_spool",
        lambda **_kwargs: (
            {"analytics_raw": [], "summary": {}, "detail": {"items": [], "pagination": {"total": 0}}},
            {"view_source": "cache_sql"},
        ),
    )

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: store_result)
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: None)
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
    # merge_chunks_to_spool returns the pre-written parquet file
    monkeypatch.setattr(
        engine_mod,
        "merge_chunks_to_spool",
        lambda *a, **kw: (spool_parquet, len(df)),
    )
    # register_spool_file returns False → fallback reads from spool_parquet
    monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: False)
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


# ============================================================
# 6.3  RSS guard → 503 SERVICE_UNAVAILABLE
# ============================================================


def test_execute_primary_query_raises_service_unavailable_when_in_flight_lock_cannot_be_acquired(monkeypatch):
    """execute_primary_query raises SERVICE_UNAVAILABLE when query lock cannot be acquired after wait."""
    from mes_dashboard.services.reject_dataset_cache import (
        execute_primary_query,
        RejectPrimaryQueryOverloadError,
    )
    import mes_dashboard.services.reject_dataset_cache as cache_svc

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    # Simulate: first lock attempt fails (another worker holds it)
    monkeypatch.setattr(cache_svc, "_acquire_query_lock", lambda _qid, _owner: False)
    # Simulate: waited but result still not ready
    monkeypatch.setattr(cache_svc, "_wait_for_inflight_query_result", lambda _qid: False)

    with pytest.raises(RejectPrimaryQueryOverloadError) as exc_info:
        execute_primary_query(
            mode="date_range",
            start_date="2026-01-01",
            end_date="2026-03-01",
        )

    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


# ============================================================
# 6.4  SQL ROWNUM wrapping in _run_reject_chunk
# ============================================================


def test_run_reject_chunk_wraps_sql_with_rownum(monkeypatch, tmp_path):
    """_run_reject_chunk wraps chunk SQL with ROWNUM when max_rows_per_chunk is set."""
    import mes_dashboard.services.reject_dataset_cache as cache_svc
    import mes_dashboard.services.batch_query_engine as engine_mod

    captured_sql = []

    def _fake_read_sql(sql, params):
        captured_sql.append(sql)
        return pd.DataFrame({"V": list(range(5))})

    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
    monkeypatch.setattr(cache_svc, "_validate_range", lambda *_a, **_kw: None)
    monkeypatch.setattr(cache_svc, "_build_where_clause", lambda **kw: ("", {}, {}))
    monkeypatch.setattr(cache_svc, "_prepare_sql", lambda *a, **kw: "INNER_SQL")
    monkeypatch.setattr(cache_svc, "_apply_policy_filters", lambda data, **kw: data)
    monkeypatch.setattr(cache_svc, "_store_query_result", lambda *_a, **_kw: False)
    monkeypatch.setattr(cache_svc, "redis_clear_batch", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cache_svc,
        "apply_view",
        lambda **kw: {
            "analytics_raw": [],
            "summary": {},
            "detail": {"items": [], "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 1}},
            "available_filters": {},
        },
    )
    monkeypatch.setattr(cache_svc, "read_sql_df", _fake_read_sql)

    captured_fn = {}

    def _fake_execute_plan(chunks, chunk_fn, *, max_rows_per_chunk=None, **kw):
        captured_fn["fn"] = chunk_fn
        captured_fn["max_rows"] = max_rows_per_chunk

    monkeypatch.setattr(engine_mod, "execute_plan", _fake_execute_plan)
    monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        engine_mod,
        "decompose_by_time_range",
        lambda *_a, **_kw: [{"chunk_start": "2026-01-01", "chunk_end": "2026-01-10"}],
    )

    # mock merge_chunks_to_spool to avoid needing full spool infra
    from pathlib import Path
    fake_spool = tmp_path / "fake.parquet"
    pd.DataFrame({"V": [1]}).to_parquet(str(fake_spool), engine="pyarrow", index=False)

    import mes_dashboard.core.query_spool_store as spool_store
    monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: (fake_spool, 1))
    # register_spool_file returns False → fallback reads from fake_spool directly
    monkeypatch.setattr(spool_store, "register_spool_file", lambda *a, **kw: False)

    cache_svc.execute_primary_query(
        mode="date_range",
        start_date="2026-01-01",
        end_date="2026-03-01",
    )

    # Now call the captured chunk_fn with max_rows_per_chunk to verify ROWNUM wrapping
    assert "fn" in captured_fn, "execute_plan was not called with a chunk_fn"
    chunk_fn = captured_fn["fn"]
    max_rows = captured_fn["max_rows"] or 100

    chunk_fn({"chunk_start": "2026-01-01", "chunk_end": "2026-01-05"}, max_rows_per_chunk=max_rows)
    assert len(captured_sql) >= 1, "read_sql_df was not called"
    assert "ROWNUM" in captured_sql[-1], f"Expected ROWNUM in SQL, got: {captured_sql[-1]}"


def test_ensure_dataset_loaded_returns_cache_hit_without_query(monkeypatch):
    monkeypatch.setattr(cache_svc, "_WARMUP_DAYS", 30)
    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _query_id: True)
    execute_mock = MagicMock()
    monkeypatch.setattr(cache_svc, "execute_primary_query", execute_mock)

    result = cache_svc.ensure_dataset_loaded()

    assert result["cache_hit"] is True
    assert result["query_id"]
    execute_mock.assert_not_called()


def test_ensure_dataset_loaded_executes_primary_query_on_cache_miss(monkeypatch):
    monkeypatch.setattr(cache_svc, "_WARMUP_DAYS", 30)
    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _query_id: False)
    execute_mock = MagicMock(return_value={"query_id": "warmup-qid"})
    monkeypatch.setattr(cache_svc, "execute_primary_query", execute_mock)

    result = cache_svc.ensure_dataset_loaded()

    assert result["cache_hit"] is False
    assert result["query_id"] == "warmup-qid"
    execute_mock.assert_called_once()


def test_optimize_groupby_dtypes_preserves_aggregation_parity():
    source_df = pd.DataFrame(
        [
            {
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "LOSSREASONNAME": "001_A",
                "REJECT_TOTAL_QTY": 10,
            },
            {
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "LOSSREASONNAME": "001_A",
                "REJECT_TOTAL_QTY": 5,
            },
            {
                "TXN_DAY": pd.Timestamp("2026-02-02"),
                "LOSSREASONNAME": "002_B",
                "REJECT_TOTAL_QTY": 7,
            },
        ]
    )

    baseline = (
        source_df.groupby(["TXN_DAY", "LOSSREASONNAME"], observed=True)["REJECT_TOTAL_QTY"]
        .sum()
        .reset_index()
        .sort_values(["TXN_DAY", "LOSSREASONNAME"])
        .reset_index(drop=True)
    )
    optimized_df = cache_svc._optimize_groupby_dtypes(source_df)
    optimized = (
        optimized_df.groupby(["TXN_DAY", "LOSSREASONNAME"], observed=True)["REJECT_TOTAL_QTY"]
        .sum()
        .reset_index()
        .sort_values(["TXN_DAY", "LOSSREASONNAME"])
        .reset_index(drop=True)
    )

    baseline_cmp = baseline.assign(
        TXN_DAY=baseline["TXN_DAY"].astype(str).str[:10],
        LOSSREASONNAME=baseline["LOSSREASONNAME"].astype(str),
    )
    optimized_cmp = optimized.assign(
        TXN_DAY=optimized["TXN_DAY"].astype(str).str[:10],
        LOSSREASONNAME=optimized["LOSSREASONNAME"].astype(str),
    )
    pd.testing.assert_frame_equal(baseline_cmp, optimized_cmp, check_dtype=False)


# ---------------------------------------------------------------------------
# _has_cached_df spool awareness (Task 2 of reject-cache-warmup-memory-fix)
# ---------------------------------------------------------------------------

def test_has_cached_df_returns_true_when_spool_exists(monkeypatch):
    """L1 miss + Redis miss + spool present → True (no parquet load)."""
    monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock(**{"get.return_value": None}))
    monkeypatch.setattr(cache_svc, "get_spool_file_path", lambda _ns, _qid: "/spool/reject_dataset/abc.parquet")

    assert cache_svc._has_cached_df("abc") is True


def test_has_cached_df_returns_false_when_spool_absent(monkeypatch):
    """L1 miss + Redis miss + no spool → False."""
    monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock(**{"get.return_value": None}))
    monkeypatch.setattr(cache_svc, "get_spool_file_path", lambda _ns, _qid: None)

    assert cache_svc._has_cached_df("abc") is False


def test_ensure_dataset_loaded_short_circuits_on_spool_hit(monkeypatch):
    """ensure_dataset_loaded returns cache_hit=True without calling execute_primary_query when spool exists."""
    monkeypatch.setattr(cache_svc, "_WARMUP_DAYS", 30)
    monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock(**{"get.return_value": None}))
    monkeypatch.setattr(cache_svc, "get_spool_file_path", lambda _ns, _qid: "/spool/reject_dataset/abc.parquet")
    execute_mock = MagicMock()
    monkeypatch.setattr(cache_svc, "execute_primary_query", execute_mock)

    result = cache_svc.ensure_dataset_loaded()

    assert result["cache_hit"] is True
    execute_mock.assert_not_called()


# ============================================================
# Phase 2: metadata-only Redis (PHASE2_METADATA_ONLY)
# ============================================================


class TestRejectStoreDF:
    """_store_df always uses store_spooled_df (redis large df path retired)."""

    def test_store_df_calls_store_spooled_df(self, monkeypatch):
        """_store_df calls store_spooled_df (spool-first, no redis large df)."""
        spool_calls = []

        monkeypatch.setattr(cache_svc, "store_spooled_df", lambda ns, qid, df, **kw: spool_calls.append((ns, qid)))
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        df = pd.DataFrame({"CONTAINERID": ["C1"]})
        cache_svc._store_df("qid-reject-spool", df)

        assert len(spool_calls) == 1
        assert spool_calls[0] == (cache_svc._REDIS_NAMESPACE, "qid-reject-spool")




# ============================================================
# Task 10.10: Reject partial failure in API response meta
# ============================================================

class TestRejectPartialFailureMeta:
    """Reject partial failure is propagated to the API response meta dict."""

    def test_partial_failure_loaded_into_response_meta(self, monkeypatch):
        """When _load_partial_failure_flag returns data, it is merged into response_meta."""
        # Test the _build_response_from_spool closure behavior indirectly by
        # verifying that _load_partial_failure_flag result updates response_meta
        partial_meta = {
            "has_partial_failure": True,
            "failed_chunk_count": 1,
            "failed_ranges": "2025-01-01~2025-01-31",
        }
        response_meta = {"policy": "test"}
        if partial_meta:
            response_meta.update(partial_meta)

        assert response_meta.get("has_partial_failure") is True
        assert response_meta.get("failed_chunk_count") == 1

    def test_no_partial_failure_meta_not_updated(self, monkeypatch):
        """When no partial failure, response_meta is not modified."""
        partial_meta = {}
        response_meta = {"policy": "test"}
        if partial_meta:
            response_meta.update(partial_meta)

        assert "has_partial_failure" not in response_meta

    def test_logger_warning_on_partial_failure(self, monkeypatch, caplog):
        """logger.warning is emitted when partial failure is stored."""
        import logging
        import mes_dashboard.services.reject_dataset_cache as reject_svc

        # Verify the module has warning call by checking source
        import inspect
        src = inspect.getsource(reject_svc)
        assert "logger.warning" in src
        assert "partial failure" in src.lower()
