# -*- coding: utf-8 -*-
"""Data boundary tests for EAP ALARM DuckDB spool-read views.

All tests use synthetic parquet fixtures — no live Oracle.

Tests:
  - test_unknown_alarm_category_code_fallback: ALARM_CATEGORY_CODE=99 → ALARM_CATEGORY="未知"
  - test_null_detail_params: rows without DETAIL entries → DETAIL_PARAMS=null in response
  - test_null_lot_id: rows with null LOT_ID → lot_id=null in response
  - test_empty_alarm_text_rows: ALARM_TEXT=null rows included in parquet, alarm_text=null
  - test_large_alarm_text: AlarmText >500 chars → no truncation, stored as-is

pytestmark = pytest.mark.integration
"""

from __future__ import annotations

import json
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytestmark = pytest.mark.integration

_PARQUET_SCHEMA = pa.schema([
    pa.field("EVENT_ID", pa.string(), nullable=False),
    pa.field("EQP_ID", pa.string(), nullable=False),
    pa.field("EQP_TYPE", pa.string(), nullable=False),
    pa.field("LOT_ID", pa.string(), nullable=True),
    pa.field("ALARM_TEXT", pa.string(), nullable=True),
    pa.field("ALARM_CATEGORY_CODE", pa.float64(), nullable=True),
    pa.field("ALARM_CATEGORY", pa.string(), nullable=False),
    pa.field("ALARM_TIME", pa.timestamp("us"), nullable=False),
    pa.field("DETAIL_PARAMS", pa.string(), nullable=True),
    pa.field("eqp_types_filter", pa.string(), nullable=False),
])


def _write_parquet(tmp_path, rows: list[dict]) -> str:
    """Write synthetic parquet spool file and return path."""
    import pandas as pd
    if rows:
        df = pd.DataFrame(rows)
        # Coerce types only when columns exist
        for col in ("EVENT_ID", "EQP_ID", "EQP_TYPE", "ALARM_CATEGORY", "eqp_types_filter"):
            if col in df.columns:
                df[col] = df[col].astype(str)
        if "ALARM_TIME" not in df.columns:
            df["ALARM_TIME"] = datetime(2025, 1, 3, 10, 0, 0)
        if "eqp_types_filter" not in df.columns:
            df["eqp_types_filter"] = "test1234"
        table = pa.Table.from_pandas(df, schema=_PARQUET_SCHEMA, safe=False)
    else:
        # Empty DataFrame: build schema-conformant zero-row table directly
        table = pa.table(
            {
                "EVENT_ID": pa.array([], type=pa.string()),
                "EQP_ID": pa.array([], type=pa.string()),
                "EQP_TYPE": pa.array([], type=pa.string()),
                "LOT_ID": pa.array([], type=pa.string()),
                "ALARM_TEXT": pa.array([], type=pa.string()),
                "ALARM_CATEGORY_CODE": pa.array([], type=pa.float64()),
                "ALARM_CATEGORY": pa.array([], type=pa.string()),
                "ALARM_TIME": pa.array([], type=pa.timestamp("us")),
                "DETAIL_PARAMS": pa.array([], type=pa.string()),
                "eqp_types_filter": pa.array([], type=pa.string()),
            },
            schema=_PARQUET_SCHEMA,
        )
    path = tmp_path / "test_spool.parquet"
    pq.write_table(table, str(path))
    return str(path)


def _base_row(**overrides) -> dict:
    base = {
        "EVENT_ID": "ROW001",
        "EQP_ID": "GDBA-001",
        "EQP_TYPE": "GDBA",
        "LOT_ID": "LOT001",
        "ALARM_TEXT": "Test Alarm",
        "ALARM_CATEGORY_CODE": 1.0,
        "ALARM_CATEGORY": "設備",
        "ALARM_TIME": datetime(2025, 1, 3, 10, 0, 0),
        "DETAIL_PARAMS": None,
        "eqp_types_filter": "test1234",
    }
    base.update(overrides)
    return base


# ── test_unknown_alarm_category_code_fallback ─────────────────────────────────

def test_unknown_alarm_category_code_fallback(tmp_path):
    """Code 99 → ALARM_CATEGORY='未知' in parquet and detail response."""
    from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
    label = decode_alarm_category(99)
    assert label == "未知", f"Expected '未知', got {label!r}"

    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", ALARM_CATEGORY_CODE=99.0, ALARM_CATEGORY="未知"),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["alarm_category"] == "未知"


# ── test_null_detail_params ───────────────────────────────────────────────────

def test_null_detail_params(tmp_path):
    """Rows with DETAIL_PARAMS=null → detail_params=null in response."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", DETAIL_PARAMS=None),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["detail_params"] is None


# ── test_null_lot_id ──────────────────────────────────────────────────────────

def test_null_lot_id(tmp_path):
    """Rows with LOT_ID=null → lot_id=null in detail response."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", LOT_ID=None),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["lot_id"] is None


# ── test_empty_alarm_text_rows ────────────────────────────────────────────────

def test_empty_alarm_text_rows(tmp_path):
    """Rows with ALARM_TEXT=null included in parquet; alarm_text=null in response."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", ALARM_TEXT=None),
        _base_row(EVENT_ID="ROW002", ALARM_TEXT="Has Text"),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["meta"]["total_count"] == 2
    alarm_texts = {r["event_id"]: r["alarm_text"] for r in result["rows"]}
    assert alarm_texts["ROW001"] is None
    assert alarm_texts["ROW002"] == "Has Text"


def test_null_alarm_text_excluded_from_filter_options(tmp_path):
    """Null ALARM_TEXT rows excluded from alarm_text_options list."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", ALARM_TEXT=None),
        _base_row(EVENT_ID="ROW002", ALARM_TEXT="Real Alarm"),
    ])

    from mes_dashboard.services.eap_alarm_service import get_filter_options
    result = get_filter_options(spool_path, filters=None)
    assert None not in result["alarm_text_options"]
    assert "Real Alarm" in result["alarm_text_options"]


# ── test_large_alarm_text ─────────────────────────────────────────────────────

def test_large_alarm_text(tmp_path):
    """AlarmText >500 chars → stored and returned as-is (no truncation)."""
    large_text = "A" * 600
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", ALARM_TEXT=large_text),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    returned_text = result["rows"][0]["alarm_text"]
    assert returned_text == large_text, (
        f"AlarmText was truncated: expected len {len(large_text)}, got len {len(returned_text or '')}"
    )


# ── test_zero_row_spool ───────────────────────────────────────────────────────

def test_zero_row_spool(tmp_path):
    """Zero-row spool → empty state (no 500 error, returns empty lists/dicts)."""
    spool_path = _write_parquet(tmp_path, [])  # empty DataFrame

    from mes_dashboard.services.eap_alarm_service import (
        get_detail,
        get_filter_options,
        get_pareto,
        get_summary,
    )

    detail = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert detail["rows"] == []
    assert detail["meta"]["total_count"] == 0

    summary = get_summary(spool_path, filters=None)
    assert summary["total_alarm_count"] == 0
    assert summary["top_equipment"] is None

    pareto = get_pareto(spool_path, filters=None)
    assert pareto["items"] == []
    assert pareto["total"] == 0

    options = get_filter_options(spool_path, filters=None)
    assert options["alarm_text_options"] == []
    assert options["equipment_id_options"] == []


# ── test_detail_params_json_parsing ──────────────────────────────────────────

def test_detail_params_json_object(tmp_path):
    """DETAIL_PARAMS JSON string → parsed to object in response."""
    detail_json = json.dumps({"param_key": "param_value", "another_key": "42"})
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", DETAIL_PARAMS=detail_json),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["detail_params"] == {"param_key": "param_value", "another_key": "42"}


# ── test_summary_top_equipment ────────────────────────────────────────────────

def test_summary_top_equipment(tmp_path):
    """Summary top_equipment returns the EQP_ID with most alarms."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(EVENT_ID="ROW001", EQP_ID="GDBA-001"),
        _base_row(EVENT_ID="ROW002", EQP_ID="GDBA-001"),
        _base_row(EVENT_ID="ROW003", EQP_ID="GCBA-002"),
    ])

    from mes_dashboard.services.eap_alarm_service import get_summary
    result = get_summary(spool_path, filters=None)
    assert result["top_equipment"] is not None
    assert result["top_equipment"]["eqp_id"] == "GDBA-001"
    assert result["top_equipment"]["alarm_count"] == 2


# ── test_per_page_capped_at_200 ───────────────────────────────────────────────

def test_per_page_capped_at_200(tmp_path):
    """detail per_page is capped at 200 (data-shape §3.17)."""
    rows = [_base_row(EVENT_ID=f"ROW{i:04d}", ALARM_TEXT=f"Alarm {i}") for i in range(5)]
    spool_path = _write_parquet(tmp_path, rows)

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=999)
    assert result["meta"]["per_page"] == 200
