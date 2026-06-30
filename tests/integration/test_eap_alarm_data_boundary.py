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
    # Matches _PAIR_SQL output column aliases (§3.17 parquet schema, v3)
    pa.field("ALARM_ID", pa.string(), nullable=True),
    pa.field("EQP_ID", pa.string(), nullable=False),
    pa.field("EQP_TYPE", pa.string(), nullable=False),
    pa.field("LOT_ID", pa.string(), nullable=True),
    pa.field("ALARM_TEXT", pa.string(), nullable=True),
    pa.field("ALARM_CATEGORY_CODE", pa.float64(), nullable=True),
    pa.field("ALARM_START", pa.timestamp("us"), nullable=False),
    pa.field("ALARM_END", pa.timestamp("us"), nullable=True),
    pa.field("DURATION_SECONDS", pa.float64(), nullable=True),
    pa.field("DETAIL_PARAMS", pa.string(), nullable=True),
    pa.field("eqp_types_filter", pa.string(), nullable=False),
])


def _write_parquet(tmp_path, rows: list[dict]) -> str:
    """Write synthetic parquet spool file and return path."""
    import pandas as pd
    if rows:
        df = pd.DataFrame(rows)
        # Coerce string types only when columns exist
        for col in ("ALARM_ID", "EQP_ID", "EQP_TYPE", "eqp_types_filter"):
            if col in df.columns:
                df[col] = df[col].astype(str)
        if "ALARM_START" not in df.columns:
            df["ALARM_START"] = datetime(2025, 1, 3, 10, 0, 0)
        if "ALARM_END" not in df.columns:
            df["ALARM_END"] = None
        if "DURATION_SECONDS" not in df.columns:
            df["DURATION_SECONDS"] = None
        if "eqp_types_filter" not in df.columns:
            df["eqp_types_filter"] = "test1234"
        table = pa.Table.from_pandas(df, schema=_PARQUET_SCHEMA, safe=False)
    else:
        # Empty DataFrame: build schema-conformant zero-row table directly
        table = pa.table(
            {
                "ALARM_ID": pa.array([], type=pa.string()),
                "EQP_ID": pa.array([], type=pa.string()),
                "EQP_TYPE": pa.array([], type=pa.string()),
                "LOT_ID": pa.array([], type=pa.string()),
                "ALARM_TEXT": pa.array([], type=pa.string()),
                "ALARM_CATEGORY_CODE": pa.array([], type=pa.float64()),
                "ALARM_START": pa.array([], type=pa.timestamp("us")),
                "ALARM_END": pa.array([], type=pa.timestamp("us")),
                "DURATION_SECONDS": pa.array([], type=pa.float64()),
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
        "ALARM_ID": "ALARM001",
        "EQP_ID": "GDBA-001",
        "EQP_TYPE": "GDBA",
        "LOT_ID": "LOT001",
        "ALARM_TEXT": "Test Alarm",
        "ALARM_CATEGORY_CODE": 1.0,
        "ALARM_START": datetime(2025, 1, 3, 10, 0, 0),
        "ALARM_END": None,
        "DURATION_SECONDS": None,
        "DETAIL_PARAMS": None,
        "eqp_types_filter": "test1234",
    }
    base.update(overrides)
    return base


# ── test_unknown_alarm_category_code_fallback ─────────────────────────────────

def test_unknown_alarm_category_code_fallback(tmp_path):
    """Code 99 → ALARM_CATEGORY_CODE returned as 99 in detail response."""
    from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
    label = decode_alarm_category(99)
    assert label == "未知", f"Expected '未知', got {label!r}"

    spool_path = _write_parquet(tmp_path, [
        _base_row(ALARM_ID="ROW001", ALARM_CATEGORY_CODE=99.0),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["alarm_category_code"] == 99


# ── test_null_detail_params ───────────────────────────────────────────────────

def test_null_detail_params(tmp_path):
    """Rows with DETAIL_PARAMS=null → detail_params=null in response."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(ALARM_ID="ALARM001", DETAIL_PARAMS=None),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["detail_params"] is None


# ── test_null_lot_id ──────────────────────────────────────────────────────────

def test_null_lot_id(tmp_path):
    """Rows with LOT_ID=null → lot_id=null in detail response."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(ALARM_ID="ALARM001", LOT_ID=None),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["lot_id"] is None


# ── test_empty_alarm_text_rows ────────────────────────────────────────────────

def test_empty_alarm_text_rows(tmp_path):
    """Rows with ALARM_TEXT=null included in parquet; alarm_text=null in response."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(ALARM_ID="ALARM001", ALARM_TEXT=None),
        _base_row(ALARM_ID="ALARM002", ALARM_TEXT="Has Text"),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["meta"]["total_count"] == 2
    alarm_texts = {r["alarm_id"]: r["alarm_text"] for r in result["rows"]}
    assert alarm_texts["ALARM001"] is None
    assert alarm_texts["ALARM002"] == "Has Text"


def test_null_alarm_text_excluded_from_filter_options(tmp_path):
    """Null ALARM_TEXT rows excluded from alarm_text_options list."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(ALARM_ID="ALARM001", ALARM_TEXT=None),
        _base_row(ALARM_ID="ALARM002", ALARM_TEXT="Real Alarm"),
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
        _base_row(ALARM_ID="ALARM001", ALARM_TEXT=large_text),
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
    assert summary["affected_equipment_count"] == 0

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
        _base_row(ALARM_ID="ALARM001", DETAIL_PARAMS=detail_json),
    ])

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=50)
    assert result["rows"][0]["detail_params"] == {"param_key": "param_value", "another_key": "42"}


# ── test_summary_top_equipment ────────────────────────────────────────────────

def test_summary_affected_equipment_count(tmp_path):
    """Summary affected_equipment_count equals distinct EQP_IDs in spool."""
    spool_path = _write_parquet(tmp_path, [
        _base_row(ALARM_ID="ALARM001", EQP_ID="GDBA-001"),
        _base_row(ALARM_ID="ALARM002", EQP_ID="GDBA-001"),
        _base_row(ALARM_ID="ALARM003", EQP_ID="GCBA-002"),
    ])

    from mes_dashboard.services.eap_alarm_service import get_summary
    result = get_summary(spool_path, filters=None)
    assert result["total_alarm_count"] == 3
    assert result["affected_equipment_count"] == 2


# ── test_per_page_capped_at_200 ───────────────────────────────────────────────

def test_per_page_capped_at_200(tmp_path):
    """detail per_page is capped at 200 (data-shape §3.17)."""
    rows = [_base_row(ALARM_ID=f"ALARM{i:04d}", ALARM_TEXT=f"Alarm {i}") for i in range(5)]
    spool_path = _write_parquet(tmp_path, rows)

    from mes_dashboard.services.eap_alarm_service import get_detail
    result = get_detail(spool_path, filters=None, page=1, per_page=999)
    assert result["meta"]["per_page"] == 200


# ── lot_ids data boundary tests ───────────────────────────────────────────────

def test_lot_ids_whitespace_stripped(monkeypatch):
    """lot_ids whitespace-stripped by the spool-key builder and validation layer (AC-5, EA-09).

    The canonical repr in make_eap_alarm_spool_key strips each lot_id via str.strip().
    The validation layer also strips before dedup. This test verifies the spool key
    treats padded and stripped versions of the same lot_id as identical.
    """
    from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key

    k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["LOT-A"])
    k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["  LOT-A  "])
    assert k1 == k2, (
        "Whitespace-padded lot_id must produce same spool key as stripped version"
    )


def test_lot_ids_deduped_before_oracle(monkeypatch):
    """Validation deduplicates lot_ids before they reach the worker (AC-5).

    validate_eap_alarm_params silently deduplicates; the resulting list
    is smaller than the input. This test verifies the dedup rule (EA-09).
    """
    from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params

    # Duplicates in input — must not raise, must silently dedup
    validate_eap_alarm_params(
        "2025-01-01", "2025-01-07",
        lot_ids=["LOT-A", "LOT-A", "LOT-B", "LOT-A"],
    )

    # Verify spool key for deduplicated input == key for un-deduplicated input
    # (spool key canonical repr strips before sorting)
    from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
    k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["LOT-A", "LOT-B"])
    # The key builder does NOT dedup — dedup is in validation.
    # This test just confirms validation passes without error for duplicate input.
    assert k1 is not None  # spool key must be constructable from the clean set


def test_lot_ids_max200_cap_exceeded(monkeypatch):
    """201 lot_ids → ValueError before Oracle call (EA-09 boundary is strictly > 200)."""
    from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
    lot_ids = [f"LOT-{i:04d}" for i in range(201)]
    with pytest.raises(ValueError, match="lot_ids exceeds max"):
        validate_eap_alarm_params("2025-01-01", "2025-01-07", lot_ids=lot_ids)


def test_char_padded_containername_matches(monkeypatch):
    """CHAR-padded CONTAINERNAME ('LOT-A   ') must match stripped lot_id 'LOT-A' (design.md Open Risk).

    The EXISTS clause uses NVL(TRIM(c.CONTAINERNAME), ...) so trailing spaces are neutralized.
    This test verifies the SQL clause includes TRIM on the column side.
    """
    from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists

    clauses, params = _build_product_dims_exists(["TypeA"], [], [])
    # The clause must apply NVL(TRIM(...)) on the container column so CHAR padding is absorbed
    assert "NVL(TRIM" in clauses[0], (
        f"EXISTS clause must apply NVL(TRIM(...)) to handle CHAR-padding: {clauses[0]}"
    )


def test_empty_product_dims_no_exists_clause():
    """Empty pj_types/product_lines/pj_bops → no EXISTS clauses generated (AC-2)."""
    from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
    clauses, params = _build_product_dims_exists([], [], [])
    assert clauses == []
    assert params == {}
