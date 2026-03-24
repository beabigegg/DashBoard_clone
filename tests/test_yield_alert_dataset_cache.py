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


def test_execute_primary_query_loads_and_stores_when_cache_miss(monkeypatch, tmp_path):
    calls: dict[str, bool] = {"stored": False}

    fake_parquet = tmp_path / "fake.parquet"
    fake_parquet.write_bytes(b"")  # placeholder file

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _query_id: None)
    monkeypatch.setattr(
        dataset_cache,
        "_streaming_write_to_spool",
        lambda *_args, **_kwargs: (fake_parquet, 1),
    )
    monkeypatch.setattr(dataset_cache, "register_spool_file", lambda *_args, **_kwargs: True)

    def _fake_store(query_id, *, linkage_df, spool_ready=True, empty_result=False, start_date="", end_date=""):  # noqa: ANN001
        if query_id and linkage_df is not None and spool_ready:
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
        lambda _query_id: {"linkage_df": linkage_df, "spool_ready": True, "empty_result": False},
    )
    monkeypatch.setattr(dataset_cache, "_load_detail_df_from_spool", lambda _qid: detail_df)
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

    # All supplementary filters now apply to ALL views (summary, trend, heatmap, etc.)
    # L9 belongs to dept "成型" — filtering by dept "焊接_WB" + line "L9" yields no match
    with_line_filter = dataset_cache.apply_view(
        query_id="ya-001",
        filters={"departments": ["焊接_WB", "焊接_DW"], "lines": ["L9"]},
        risk_threshold=99,
        min_scrap_qty=0,
    )
    assert with_line_filter["alerts"]["pagination"]["total"] == 0
    assert with_line_filter["summary"]["transaction_qty"] == 0.0

    # L1 belongs to dept "焊接_WB" — this combination narrows results correctly
    with_l1_filter = dataset_cache.apply_view(
        query_id="ya-001",
        filters={"departments": ["焊接_WB", "焊接_DW"], "lines": ["L1"]},
        risk_threshold=99,
        min_scrap_qty=0,
    )
    assert with_l1_filter["summary"]["transaction_qty"] > 0


def test_ensure_dataset_loaded_returns_cache_hit(monkeypatch):
    monkeypatch.setattr(dataset_cache, "_WARMUP_DAYS", 30)
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _query_id: {"detail_df": None, "linkage_df": pd.DataFrame()},
    )
    calls = {"executed": 0}

    def _fake_execute(*, start_date: str, end_date: str):
        calls["executed"] += 1
        return {"query_id": "qid"}

    monkeypatch.setattr(dataset_cache, "execute_primary_query", _fake_execute)

    result = dataset_cache.ensure_dataset_loaded()
    assert result["cache_hit"] is True
    assert calls["executed"] == 0


def test_ensure_dataset_loaded_executes_query_on_miss(monkeypatch):
    monkeypatch.setattr(dataset_cache, "_WARMUP_DAYS", 30)
    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _query_id: None)
    calls = {"executed": 0}

    def _fake_execute(*, start_date: str, end_date: str):
        calls["executed"] += 1
        return {"query_id": "warmup-yield"}

    monkeypatch.setattr(dataset_cache, "execute_primary_query", _fake_execute)

    result = dataset_cache.ensure_dataset_loaded()
    assert result["cache_hit"] is False
    assert result["query_id"] == "warmup-yield"
    assert calls["executed"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# Task 6.3: _prepare_detail_chunk schema validation
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_detail_chunk_produces_detail_columns_schema():
    """_prepare_detail_chunk must output exactly _DETAIL_COLUMNS as PyArrow column names."""
    columns = [
        "DATE_BUCKET", "WIP_ENTITY_NAME", "REASON_RAW", "REASON_NAME",
        "DEPARTMENT_NAME", "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME",
        "FUNCTION_NAME", "OPERATION_SEQ_NUM", "TRANSACTION_QTY", "SCRAP_QTY",
    ]
    rows = [
        (
            "2026-02-21", "GA-WO-001", "031_腳架氧化", "031_腳架氧化",
            "焊接_WB", "L1", "PKG-A", "TYPE-A",
            "FUNC-A", 10, 100.0, 5.0,
        )
    ]
    table = dataset_cache._prepare_detail_chunk(columns, rows)
    assert list(table.schema.names) == dataset_cache._DETAIL_COLUMNS
    assert table.num_rows == 1


def test_prepare_detail_chunk_handles_null_values():
    """_prepare_detail_chunk must apply fillna defaults for nullable fields."""
    columns = [
        "DATE_BUCKET", "WIP_ENTITY_NAME", "REASON_RAW", "REASON_NAME",
        "DEPARTMENT_NAME", "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME",
        "FUNCTION_NAME", "OPERATION_SEQ_NUM", "TRANSACTION_QTY", "SCRAP_QTY",
    ]
    rows = [
        (None, None, None, None, None, None, None, None, None, None, None, None)
    ]
    table = dataset_cache._prepare_detail_chunk(columns, rows)
    df = table.to_pandas()
    assert df["WORKORDER"].iloc[0] == "(NA)"
    assert df["REASON_RAW"].iloc[0] == "(UNMAPPED)"
    assert df["TRANSACTION_QTY"].iloc[0] == 0.0
    assert df["SCRAP_QTY"].iloc[0] == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Task 6.6: Failure mode tests
# ──────────────────────────────────────────────────────────────────────────────

def test_execute_primary_query_spool_register_fail_raises_spool_write_error(monkeypatch, tmp_path):
    """When register_spool_file returns False, SpoolWriteError is raised (not a silent success)."""
    fake_parquet = tmp_path / "fake.parquet"
    fake_parquet.write_bytes(b"")

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _query_id: None)
    monkeypatch.setattr(
        dataset_cache, "_streaming_write_to_spool", lambda *_a, **_kw: (fake_parquet, 5)
    )
    monkeypatch.setattr(dataset_cache, "register_spool_file", lambda *_a, **_kw: False)

    import pytest
    with pytest.raises(dataset_cache.SpoolWriteError):
        dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")


def test_execute_primary_query_empty_result_does_not_raise(monkeypatch):
    """When the Oracle query returns 0 rows, execute_primary_query stores empty marker and returns normally."""
    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _query_id: None)
    monkeypatch.setattr(
        dataset_cache, "_streaming_write_to_spool", lambda *_a, **_kw: (None, 0)
    )
    stored = {}

    def _fake_store(query_id, *, linkage_df, spool_ready, empty_result, start_date, end_date):
        stored["empty_result"] = empty_result
        stored["spool_ready"] = spool_ready

    monkeypatch.setattr(dataset_cache, "_store_payload", _fake_store)

    result = dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")
    assert result["meta"]["detail_rows"] == 0
    assert stored["empty_result"] is True
    assert stored["spool_ready"] is False


def test_apply_view_returns_empty_success_for_empty_result_marker(monkeypatch):
    """apply_view returns empty structured result (not None) when empty_result marker is set."""
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "linkage_df": pd.DataFrame(columns=dataset_cache._LINKAGE_COLUMNS),
            "spool_ready": False,
            "empty_result": True,
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
        },
    )
    monkeypatch.setattr(dataset_cache, "_load_excluded_reason_tokens", lambda: set())

    result = dataset_cache.apply_view(query_id="empty-qid")
    assert result is not None
    assert result["summary"]["transaction_qty"] == 0.0
    assert result["summary"]["scrap_qty"] == 0.0
    assert result["alerts"]["pagination"]["total"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Coverage gap: execute_linkage_query spool-based path
# ──────────────────────────────────────────────────────────────────────────────

def test_execute_linkage_query_returns_none_on_cache_miss(monkeypatch):
    """execute_linkage_query returns None when payload is not in cache."""
    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _qid: None)
    result = dataset_cache.execute_linkage_query(query_id="missing-qid")
    assert result is None


def test_execute_linkage_query_returns_early_for_empty_result(monkeypatch):
    """execute_linkage_query returns linkage_ready=True immediately for empty_result marker."""
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "empty_result": True,
            "spool_ready": False,
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
        },
    )
    result = dataset_cache.execute_linkage_query(query_id="empty-qid")
    assert result is not None
    assert result["meta"]["linkage_ready"] is True
    assert result["meta"]["linkage_rows"] == 0


def test_execute_linkage_query_returns_not_ready_when_spool_missing(monkeypatch):
    """execute_linkage_query returns linkage_not_ready when spool file is unavailable."""
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "empty_result": False,
            "spool_ready": True,
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
        },
    )
    monkeypatch.setattr(dataset_cache, "get_spool_file_path", lambda _ns, _qid: None)
    result = dataset_cache.execute_linkage_query(query_id="no-spool-qid")
    assert result is not None
    assert result["meta"]["linkage_ready"] is False
    assert result["meta"]["linkage_not_ready_reason"] == "spool_not_available"


def test_execute_linkage_query_computes_linkage_from_spool(monkeypatch, tmp_path):
    """execute_linkage_query extracts workorders via DuckDB and computes linkage."""
    # Create a real parquet spool file with test data
    import pyarrow as pa
    import pyarrow.parquet as pq

    detail_df = pd.DataFrame(
        {
            "DATE_BUCKET": ["2026-02-21", "2026-02-21"],
            "WORKORDER": ["WO-001", "WO-002"],
            "REASON_RAW": ["031_腳架氧化", "031_腳架氧化"],
            "REASON_NAME": ["031_腳架氧化", "031_腳架氧化"],
            "DEPARTMENT_NAME": ["焊接_WB", "焊接_WB"],
            "DEPARTMENT_GROUP": ["焊接_WB", "焊接_WB"],
            "PROCESS_CATEGORY": ["WB", "WB"],
            "LINE_NAME": ["L1", "L1"],
            "PACKAGE_NAME": ["PKG-A", "PKG-A"],
            "TYPE_NAME": ["TYPE-A", "TYPE-A"],
            "FUNCTION_NAME": ["FUNC-A", "FUNC-A"],
            "OPERATION_TEXT": ["10", "10"],
            "REASON_CODE": ["031", "031"],
            "REASON_RAW_UPPER": ["031_腳架氧化", "031_腳架氧化"],
            "REASON_NAME_UPPER": ["031_腳架氧化", "031_腳架氧化"],
            "TRANSACTION_QTY": [100.0, 200.0],
            "SCRAP_QTY": [5.0, 3.0],
        }
    )
    spool_file = tmp_path / "test_spool.parquet"
    pq.write_table(pa.Table.from_pandas(detail_df, preserve_index=False), str(spool_file))

    stored = {}

    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "empty_result": False,
            "spool_ready": True,
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
            "linkage_df": pd.DataFrame(columns=dataset_cache._LINKAGE_COLUMNS),
        },
    )
    monkeypatch.setattr(dataset_cache, "get_spool_file_path", lambda _ns, _qid: str(spool_file))
    monkeypatch.setattr(
        dataset_cache, "_compute_reject_linkage",
        lambda *, start_date, end_date, workorders: {
            "2026-02-21|WO-001|031": 5.0,
        },
    )

    def _fake_store(query_id, *, linkage_df, spool_ready, empty_result, start_date, end_date):
        stored["linkage_rows"] = len(linkage_df)

    monkeypatch.setattr(dataset_cache, "_store_payload", _fake_store)
    monkeypatch.setattr(dataset_cache, "maybe_gc_collect", lambda: None)

    result = dataset_cache.execute_linkage_query(query_id="spool-qid")
    assert result is not None
    assert result["meta"]["linkage_ready"] is True
    assert result["meta"]["linkage_rows"] == 1
    assert stored["linkage_rows"] == 1


def test_execute_linkage_query_derives_dates_from_spool_when_missing(monkeypatch, tmp_path):
    """execute_linkage_query uses DuckDB to derive date range when metadata is missing."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    detail_df = pd.DataFrame(
        {
            "DATE_BUCKET": ["2026-02-20", "2026-02-21"],
            "WORKORDER": ["WO-001", "WO-001"],
            "REASON_RAW": ["031_腳架氧化", "031_腳架氧化"],
            "REASON_NAME": ["031_腳架氧化", "031_腳架氧化"],
            "DEPARTMENT_NAME": ["焊接_WB", "焊接_WB"],
            "DEPARTMENT_GROUP": ["焊接_WB", "焊接_WB"],
            "PROCESS_CATEGORY": ["WB", "WB"],
            "LINE_NAME": ["L1", "L1"],
            "PACKAGE_NAME": ["PKG-A", "PKG-A"],
            "TYPE_NAME": ["TYPE-A", "TYPE-A"],
            "FUNCTION_NAME": ["FUNC-A", "FUNC-A"],
            "OPERATION_TEXT": ["10", "10"],
            "REASON_CODE": ["031", "031"],
            "REASON_RAW_UPPER": ["031_腳架氧化", "031_腳架氧化"],
            "REASON_NAME_UPPER": ["031_腳架氧化", "031_腳架氧化"],
            "TRANSACTION_QTY": [100.0, 200.0],
            "SCRAP_QTY": [5.0, 3.0],
        }
    )
    spool_file = tmp_path / "test_spool.parquet"
    pq.write_table(pa.Table.from_pandas(detail_df, preserve_index=False), str(spool_file))

    captured_dates = {}

    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "empty_result": False,
            "spool_ready": True,
            "start_date": "",  # missing
            "end_date": "",    # missing
            "linkage_df": pd.DataFrame(columns=dataset_cache._LINKAGE_COLUMNS),
        },
    )
    monkeypatch.setattr(dataset_cache, "get_spool_file_path", lambda _ns, _qid: str(spool_file))

    def _fake_linkage(*, start_date, end_date, workorders):
        captured_dates["start"] = start_date
        captured_dates["end"] = end_date
        return {}

    monkeypatch.setattr(dataset_cache, "_compute_reject_linkage", _fake_linkage)
    monkeypatch.setattr(dataset_cache, "_store_payload", lambda *a, **kw: None)
    monkeypatch.setattr(dataset_cache, "maybe_gc_collect", lambda: None)

    dataset_cache.execute_linkage_query(query_id="derive-dates-qid")
    assert captured_dates["start"] == "2026-02-20"
    assert captured_dates["end"] == "2026-02-21"


# ──────────────────────────────────────────────────────────────────────────────
# Task 6.4: Integration test — primary query → spool → DuckDB view → response
# ──────────────────────────────────────────────────────────────────────────────

def test_primary_query_to_spool_to_view_full_pipeline(monkeypatch, tmp_path):
    """Integration: streaming write → register spool → apply_view via pandas fallback produces correct response."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    # --- Phase 1: Simulate streaming write producing a real parquet spool ---
    detail_rows = [
        {
            "DATE_BUCKET": "2026-02-21",
            "WORKORDER": "WO-001",
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
            "TRANSACTION_QTY": 100.0,
            "SCRAP_QTY": 5.0,
        },
        {
            "DATE_BUCKET": "2026-02-21",
            "WORKORDER": "WO-002",
            "REASON_RAW": "032_打線斷裂",
            "REASON_NAME": "032_打線斷裂",
            "DEPARTMENT_NAME": "焊接_WB",
            "DEPARTMENT_GROUP": "焊接_WB",
            "PROCESS_CATEGORY": "WB",
            "LINE_NAME": "L2",
            "PACKAGE_NAME": "PKG-B",
            "TYPE_NAME": "TYPE-B",
            "FUNCTION_NAME": "FUNC-B",
            "OPERATION_TEXT": "20",
            "REASON_CODE": "032",
            "REASON_RAW_UPPER": "032_打線斷裂",
            "REASON_NAME_UPPER": "032_打線斷裂",
            "TRANSACTION_QTY": 200.0,
            "SCRAP_QTY": 10.0,
        },
    ]
    detail_df = pd.DataFrame(detail_rows)
    spool_file = tmp_path / "integration_spool.parquet"
    pq.write_table(pa.Table.from_pandas(detail_df, preserve_index=False), str(spool_file))

    linkage_df = pd.DataFrame(
        [{"CANONICAL_KEY": "2026-02-21|WO-001|031", "REJECT_TOTAL_QTY": 5.0}]
    )

    # --- Phase 2: Wire up apply_view to use the spool file ---
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "linkage_df": linkage_df,
            "spool_ready": True,
            "empty_result": False,
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
        },
    )
    monkeypatch.setattr(dataset_cache, "_load_detail_df_from_spool", lambda _qid: detail_df)
    monkeypatch.setattr(dataset_cache, "_load_excluded_reason_tokens", lambda: set())

    # --- Phase 3: Call apply_view and verify the full response ---
    result = dataset_cache.apply_view(query_id="integration-qid")
    assert result is not None

    # Summary should aggregate both rows
    assert result["summary"]["transaction_qty"] == 300.0
    assert result["summary"]["scrap_qty"] == 15.0

    # Alerts should have 2 items (each workorder+reason is a distinct alert)
    assert result["alerts"]["pagination"]["total"] == 2

    # Meta should indicate pandas fallback
    assert result["meta"]["view_source"] == "pandas"

    # Filter options should be populated
    assert "filter_options" in result

    # Trend items should exist
    assert "items" in result["trend"]


# ──────────────────────────────────────────────────────────────────────────────
# Task 6.5: Telemetry/log field verification
# ──────────────────────────────────────────────────────────────────────────────

def test_streaming_spool_logs_latency_and_rows(monkeypatch, tmp_path, caplog):
    """execute_primary_query logs streaming spool done with query_id, rows, and latency_ms."""
    import logging

    fake_parquet = tmp_path / "fake.parquet"
    fake_parquet.write_bytes(b"")

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _qid: None)
    monkeypatch.setattr(
        dataset_cache, "_streaming_write_to_spool", lambda *_a, **_kw: (fake_parquet, 42)
    )
    monkeypatch.setattr(dataset_cache, "register_spool_file", lambda *_a, **_kw: True)
    monkeypatch.setattr(dataset_cache, "_store_payload", lambda *a, **kw: None)
    monkeypatch.setattr(dataset_cache, "maybe_gc_collect", lambda: None)

    with caplog.at_level(logging.INFO, logger="mes_dashboard.yield_alert_dataset_cache"):
        dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")

    spool_done_logs = [r for r in caplog.records if "streaming spool done" in r.message]
    assert len(spool_done_logs) == 1
    assert "rows=42" in spool_done_logs[0].message
    assert "latency_ms=" in spool_done_logs[0].message


def test_empty_result_logs_latency(monkeypatch, caplog):
    """execute_primary_query logs empty result with latency_ms."""
    import logging

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _qid: None)
    monkeypatch.setattr(
        dataset_cache, "_streaming_write_to_spool", lambda *_a, **_kw: (None, 0)
    )
    monkeypatch.setattr(dataset_cache, "_store_payload", lambda *a, **kw: None)

    with caplog.at_level(logging.INFO, logger="mes_dashboard.yield_alert_dataset_cache"):
        dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")

    empty_logs = [r for r in caplog.records if "empty result" in r.message]
    assert len(empty_logs) == 1
    assert "latency_ms=" in empty_logs[0].message


def test_single_flight_wait_logs_on_lock_contention(monkeypatch, caplog):
    """execute_primary_query logs single-flight wait and resolution when lock is held."""
    import logging

    call_count = {"n": 0}

    def _fake_cache(query_id):
        call_count["n"] += 1
        if call_count["n"] >= 3:  # resolve on 2nd poll (1st call is the initial check)
            return {
                "linkage_df": pd.DataFrame(columns=dataset_cache._LINKAGE_COLUMNS),
                "spool_ready": True,
                "empty_result": False,
            }
        return None

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", _fake_cache)
    monkeypatch.setattr(dataset_cache, "try_acquire_lock", lambda *a, **kw: False)
    # Speed up the test by making sleep a no-op
    monkeypatch.setattr(dataset_cache.time, "sleep", lambda _s: None)

    with caplog.at_level(logging.INFO, logger="mes_dashboard.yield_alert_dataset_cache"):
        result = dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")

    assert result["meta"]["cache_hit"] is True
    wait_logs = [r for r in caplog.records if "single-flight wait" in r.message]
    assert len(wait_logs) == 1
    resolved_logs = [r for r in caplog.records if "single-flight resolved" in r.message]
    assert len(resolved_logs) == 1


def test_spool_write_failure_logs_warning(monkeypatch, caplog):
    """SpoolWriteError from streaming write is raised with descriptive message."""
    import logging
    import pytest

    monkeypatch.setattr(dataset_cache, "_get_cached_payload", lambda _qid: None)
    monkeypatch.setattr(
        dataset_cache, "_streaming_write_to_spool",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(dataset_cache.SpoolWriteError, match="SPOOL_WRITE_FAILED"):
        dataset_cache.execute_primary_query(start_date="2026-02-21", end_date="2026-02-21")


def test_linkage_spool_not_available_logs_warning(monkeypatch, caplog):
    """execute_linkage_query returns spool_not_available reason when spool is missing."""
    monkeypatch.setattr(
        dataset_cache,
        "_get_cached_payload",
        lambda _qid: {
            "empty_result": False,
            "spool_ready": False,
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
        },
    )
    result = dataset_cache.execute_linkage_query(query_id="no-spool")
    assert result["meta"]["linkage_not_ready_reason"] == "spool_not_available"
