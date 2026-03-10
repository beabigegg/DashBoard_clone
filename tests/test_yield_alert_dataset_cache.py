# -*- coding: utf-8 -*-
"""Unit tests for yield alert two-phase dataset cache service."""

from __future__ import annotations

import pandas as pd

import mes_dashboard.services.yield_alert_dataset_cache as dataset_cache


def test_execute_primary_query_returns_cached_query_id(monkeypatch):
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda query_id: {
            "move_df": pd.DataFrame(),
            "detail_df": pd.DataFrame(),
            "linkage_df": pd.DataFrame(),
        },
    )

    result = dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")
    assert result["query_id"]
    assert result["meta"]["cache_hit"] is True


def test_execute_primary_query_loads_and_stores_when_cache_miss(monkeypatch):
    calls: dict[str, bool] = {"stored": False}
    detail_df = pd.DataFrame(
        [
            {
                "DATE_BUCKET": "2026-02-21",
                "WORKORDER": "WO-1",
                "REASON_RAW": "031_TEST",
                "REASON_NAME": "031_TEST",
                "DEPARTMENT_NAME": "焊接_WB",
                "DEPARTMENT_GROUP": "焊接_WB",
                "PROCESS_CATEGORY": "WB",
                "LINE_NAME": "L1",
                "PACKAGE_NAME": "PKG",
                "TYPE_NAME": "TYPE",
                "FUNCTION_NAME": "FUNC",
                "OPERATION_TEXT": "10",
                "REASON_CODE": "031",
                "REASON_RAW_UPPER": "031_TEST",
                "REASON_NAME_UPPER": "031_TEST",
                "TRANSACTION_QTY": 100.0,
                "SCRAP_QTY": 1.0,
            }
        ]
    )

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _query_id: None)
    monkeypatch.setattr(dataset_cache, "_load_primary_detail_df", lambda *_args, **_kwargs: detail_df)

    def _fake_store(query_id, *, detail_df, linkage_df):  # noqa: ANN001
        if query_id and not detail_df.empty and linkage_df is not None:
            calls["stored"] = True

    monkeypatch.setattr(dataset_cache, "_store_payload", _fake_store)

    result = dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")
    assert result["meta"]["cache_hit"] is False
    assert calls["stored"] is True


def test_apply_view_returns_none_on_cache_miss(monkeypatch):
    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _query_id: None)
    result = dataset_cache.apply_view(query_id="missing")
    assert result is None


def test_apply_view_uses_cached_data_for_secondary_filters(monkeypatch):
    move_df = pd.DataFrame(
        [
            {"DATE_BUCKET": "2026-02-21", "DEPARTMENT_NAME": "焊接_WB", "TRANSACTION_QTY": 14039.147},
            {"DATE_BUCKET": "2026-02-21", "DEPARTMENT_NAME": "成型", "TRANSACTION_QTY": 100.0},
        ]
    )
    detail_df = pd.DataFrame(
        [
            {
                "DATE_BUCKET": "2026-02-21",
                "WORKORDER": "WO-1",
                "REASON_RAW": "031_腳架氧化",
                "REASON_NAME": "031_腳架氧化",
                "DEPARTMENT_NAME": "焊接_WB",
                "DEPARTMENT_GROUP": "焊接_WB",
                "PROCESS_CATEGORY": "WB",
                "LINE_NAME": "L1",
                "PACKAGE_NAME": "PKG-A",
                "TYPE_NAME": "TYPE-A",
                "FUNCTION_NAME": "FUNC-A",
                "OPERATION_TEXT": "10",
                "REASON_CODE": "031",
                "REASON_RAW_UPPER": "031_腳架氧化",
                "REASON_NAME_UPPER": "031_腳架氧化",
                "TRANSACTION_QTY": 14039.147,
                "SCRAP_QTY": 17.155,
            },
            {
                "DATE_BUCKET": "2026-02-21",
                "WORKORDER": "WO-2",
                "REASON_RAW": "(UNMAPPED)",
                "REASON_NAME": "(UNMAPPED)",
                "DEPARTMENT_NAME": "焊接_WB",
                "DEPARTMENT_GROUP": "焊接_WB",
                "PROCESS_CATEGORY": "WB",
                "LINE_NAME": "L1",
                "PACKAGE_NAME": "PKG-A",
                "TYPE_NAME": "TYPE-A",
                "FUNCTION_NAME": "FUNC-A",
                "OPERATION_TEXT": "10",
                "REASON_CODE": "UNMAPPED_REASON",
                "REASON_RAW_UPPER": "(UNMAPPED)",
                "REASON_NAME_UPPER": "(UNMAPPED)",
                "TRANSACTION_QTY": 200.0,
                "SCRAP_QTY": 2.0,
            },
            {
                "DATE_BUCKET": "2026-02-21",
                "WORKORDER": "WO-3",
                "REASON_RAW": "031_腳架氧化",
                "REASON_NAME": "031_腳架氧化",
                "DEPARTMENT_NAME": "成型",
                "DEPARTMENT_GROUP": "成型",
                "PROCESS_CATEGORY": "OTHER",
                "LINE_NAME": "L9",
                "PACKAGE_NAME": "PKG-Z",
                "TYPE_NAME": "TYPE-Z",
                "FUNCTION_NAME": "FUNC-Z",
                "OPERATION_TEXT": "30",
                "REASON_CODE": "031",
                "REASON_RAW_UPPER": "031_腳架氧化",
                "REASON_NAME_UPPER": "031_腳架氧化",
                "TRANSACTION_QTY": 100.0,
                "SCRAP_QTY": 5.0,
            },
        ]
    )
    linkage_df = pd.DataFrame([{"CANONICAL_KEY": "2026-02-21|WO-1|031", "REJECT_TOTAL_QTY": 17.155}])
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _query_id: {"move_df": move_df, "detail_df": detail_df, "linkage_df": linkage_df},
    )
    monkeypatch.setattr(dataset_cache, "_load_excluded_reason_tokens", lambda: {"358"})

    result = dataset_cache.apply_view(
        query_id="ya-001",
        filters={"departments": ["焊接_WB", "焊接_DW"]},
        risk_threshold=99,
        min_scrap_qty=0,
    )

    assert result is not None
    assert round(result["summary"]["transaction_qty"], 3) == 14239.147
    assert round(result["summary"]["scrap_qty"], 3) == 17.155
    assert result["alerts"]["pagination"]["total"] == 1
    assert result["alerts"]["items"][0]["department"] == "焊接_WB"

    # Secondary filters should be cache-based and not affect summary/trend dimensions.
    with_line_filter = dataset_cache.apply_view(
        query_id="ya-001",
        filters={"departments": ["焊接_WB", "焊接_DW"], "lines": ["L9"]},
        risk_threshold=99,
        min_scrap_qty=0,
    )
    assert with_line_filter["alerts"]["pagination"]["total"] == 0
    assert round(with_line_filter["summary"]["transaction_qty"], 3) == 14239.147
    assert round(with_line_filter["summary"]["scrap_qty"], 3) == 17.155
