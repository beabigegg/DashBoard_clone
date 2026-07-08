# -*- coding: utf-8 -*-
"""Dual-tier parity: frontend DuckDB-WASM SQL (useProductionAchievementDuckDB.ts)
vs the retained Python golden reference (production_achievement_service.build_achievement_rows()).

Change: production-achievement-async-spool (ADR-0016). PA-06/PA-07 relocated
from server-side Python to browser DuckDB-WASM SQL; `build_achievement_rows()`
is retained as the test-only golden reference (business-rules.md PA-06/PA-07
"Implementation locus" notes). Mirrors tests/test_frontend_hold_history_parity.py:
the "frontend_*" helpers below are a literal transcription of the SQL text
built by useProductionAchievementDuckDB.ts's buildValuesTableSql/_buildRollup/
computeView, executed via the `duckdb` Python package (same DuckDB SQL
dialect the browser's DuckDB-WASM engine runs) -- this is a stronger parity
signal than a Node-subprocess reimplementation of a scalar formula, since the
achievement_rate formula here is expressed entirely as inline SQL, not a
separately importable pure JS function.

Business-key diff performed over (output_date, shift_code, workcenter_group):
actual_output_qty, target_qty, achievement_rate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest

from mes_dashboard.services.production_achievement_service import build_achievement_rows

# ── Fixture: SPECNAME-grain spool rows (data-shape-contract.md §3.28.1) ─────
#
# Deliberately includes:
#  - case-variant SPECNAME duplicates ("Epoxy D/B" vs "epoxy d/b") that must
#    collapse into ONE workcenter_group via UPPER(TRIM(SPECNAME)) on both
#    sides (PA-06) -- this is the exact backend-vs-frontend join-key risk
#    flagged in implementation-plan.md's Known Risks.
#  - an unmapped SPECNAME ("UNKNOWN_SPEC") that must be excluded from BOTH
#    golden and frontend output (unmapped-SPECNAME exclusion, data-boundary,
#    not an error).
#  - four (shift_code, workcenter_group) target combinations covering every
#    PA-07 branch: missing target row -> null, stored target_qty=0 -> null
#    (never Infinity), zero actual + non-null target -> 0.0, normal division.
_SPOOL_ROWS: List[Dict[str, Any]] = [
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "Epoxy D/B", "actual_output_qty": 100},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "epoxy d/b", "actual_output_qty": 50},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "UNKNOWN_SPEC", "actual_output_qty": 999},
    {"output_date": "2026-04-27", "shift_code": "N", "SPECNAME": "金線製程", "actual_output_qty": 250},
    {"output_date": "2026-04-28", "shift_code": "D", "SPECNAME": "Epoxy D/B", "actual_output_qty": 0},
    {"output_date": "2026-04-28", "shift_code": "N", "SPECNAME": "金線製程", "actual_output_qty": 500},
]

_MAPPING: Dict[str, Dict[str, Any]] = {
    "EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1},
    "金線製程": {"workcenter": "WC2", "group": "焊接_WB", "sequence": 2},
}

_SPEC_MAP_ROWS: List[Dict[str, str]] = [
    {"SPECNAME": spec, "workcenter_group": info["group"]} for spec, info in _MAPPING.items()
]

# (shift_code, workcenter_group) -> target_qty
#  ("D", "焊接_DB")  -- missing entirely -> null
#  ("N", "焊接_WB") on 2026-04-27 relies on the SAME target row as 04-28 (no
#  date dimension per §3.26) -- covers "normal division" (250/500=0.5) and
#  "zero actual + non-null target" via a second group below.
_TARGETS: Dict[Tuple[str, str], Optional[int]] = {
    ("N", "焊接_WB"): 500,
}
_TARGETS_MAP_ROWS: List[Dict[str, Any]] = [
    {"shift_code": sc, "workcenter_group": wg, "target_qty": tq} for (sc, wg), tq in _TARGETS.items()
]

# Second target scenario set (stored zero target + zero-actual/non-zero-target)
# exercised via a second fixture below so each PA-07 branch has an isolated case.
_ZERO_TARGET_TARGETS: Dict[Tuple[str, str], Optional[int]] = {("D", "焊接_DB"): 0}
_ZERO_TARGET_MAP_ROWS: List[Dict[str, Any]] = [
    {"shift_code": sc, "workcenter_group": wg, "target_qty": tq} for (sc, wg), tq in _ZERO_TARGET_TARGETS.items()
]


def _golden_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "OUTPUT_DATE": r["output_date"],
                "SHIFT_CODE": r["shift_code"],
                "SPECNAME": r["SPECNAME"],
                "ACTUAL_OUTPUT_QTY": r["actual_output_qty"],
            }
            for r in _SPOOL_ROWS
        ]
    )


# ── Frontend DuckDB SQL equivalents (mirrors useProductionAchievementDuckDB.ts) ─

def _sql_string(value: Any) -> str:
    if value is None:
        value = ""
    return "'" + str(value).replace("'", "''") + "'"


def _sql_number_or_null(value: Any) -> str:
    if value is None or value == "":
        return "NULL"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "NULL"
    if n != n or n in (float("inf"), float("-inf")):
        return "NULL"
    return str(int(n)) if n == int(n) else str(n)


def _build_values_table_sql(
    table_name: str, columns: List[Dict[str, str]], rows: List[Dict[str, Any]]
) -> str:
    col_names = ", ".join(c["name"] for c in columns)
    if not rows:
        null_select = ", ".join(f'CAST(NULL AS {c["type"]}) AS {c["name"]}' for c in columns)
        return f"CREATE OR REPLACE TABLE {table_name} AS SELECT {null_select} WHERE FALSE"
    values_rows = []
    for row in rows:
        vals = [
            _sql_number_or_null(row.get(c["name"])) if c["kind"] == "number" else _sql_string(row.get(c["name"]))
            for c in columns
        ]
        values_rows.append("(" + ", ".join(vals) + ")")
    values_sql = ",\n    ".join(values_rows)
    return f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM (VALUES\n    {values_sql}\n  ) AS t({col_names})"


def _build_spec_map_sql(rows: List[Dict[str, str]]) -> str:
    return _build_values_table_sql(
        "pa_spec_workcenter_map",
        [
            {"name": "SPECNAME", "type": "VARCHAR", "kind": "string"},
            {"name": "workcenter_group", "type": "VARCHAR", "kind": "string"},
        ],
        rows,  # type: ignore[arg-type]
    )


def _build_targets_map_sql(rows: List[Dict[str, Any]]) -> str:
    return _build_values_table_sql(
        "pa_targets_map",
        [
            {"name": "shift_code", "type": "VARCHAR", "kind": "string"},
            {"name": "workcenter_group", "type": "VARCHAR", "kind": "string"},
            {"name": "target_qty", "type": "INTEGER", "kind": "number"},
        ],
        rows,
    )


_ROLLUP_SQL = """
    CREATE OR REPLACE TABLE pa_rollup AS
    SELECT
      s.output_date AS output_date,
      s.shift_code AS shift_code,
      m.workcenter_group AS workcenter_group,
      SUM(s.actual_output_qty) AS actual_output_qty
    FROM production_achievement_data s
    INNER JOIN pa_spec_workcenter_map m
      ON UPPER(TRIM(CAST(s.SPECNAME AS VARCHAR))) = UPPER(TRIM(CAST(m.SPECNAME AS VARCHAR)))
    GROUP BY s.output_date, s.shift_code, m.workcenter_group
"""

_FINAL_SQL = """
    SELECT
      strftime(CAST(r.output_date AS DATE), '%Y-%m-%d') AS output_date,
      r.shift_code AS shift_code,
      r.workcenter_group AS workcenter_group,
      r.actual_output_qty AS actual_output_qty,
      t.target_qty AS target_qty,
      CASE
        WHEN t.target_qty IS NULL THEN NULL
        WHEN t.target_qty = 0 THEN NULL
        ELSE CAST(r.actual_output_qty AS DOUBLE) / t.target_qty
      END AS achievement_rate
    FROM pa_rollup r
    LEFT JOIN pa_targets_map t
      ON r.shift_code = t.shift_code AND r.workcenter_group = t.workcenter_group
    ORDER BY r.output_date, r.shift_code, r.workcenter_group
"""


def _frontend_rows(
    spool_rows: List[Dict[str, Any]],
    spec_map_rows: List[Dict[str, str]],
    targets_map_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    conn = duckdb.connect(":memory:")
    try:
        spool_df = pd.DataFrame(spool_rows)
        conn.register("production_achievement_data", spool_df)
        conn.execute(_build_spec_map_sql(spec_map_rows))
        conn.execute(_build_targets_map_sql(targets_map_rows))
        conn.execute(_ROLLUP_SQL)
        result = conn.execute(_FINAL_SQL).fetchdf()
        rows = []
        for _, row in result.iterrows():
            target_qty = row["target_qty"]
            rate = row["achievement_rate"]
            rows.append(
                {
                    "output_date": str(row["output_date"]),
                    "shift_code": str(row["shift_code"]),
                    "workcenter_group": str(row["workcenter_group"]),
                    "actual_output_qty": int(row["actual_output_qty"]),
                    "target_qty": None if pd.isna(target_qty) else int(target_qty),
                    "achievement_rate": None if pd.isna(rate) else float(rate),
                }
            )
        return rows
    finally:
        conn.close()


def _by_key(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    return {(r["output_date"], r["shift_code"], r["workcenter_group"]): r for r in rows}


class TestProductionAchievementRollupParity:
    """PA-06: SPECNAME -> workcenter_group rollup, case-insensitive join key."""

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_business_key_sets_match(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = build_achievement_rows(_golden_df(), targets=_TARGETS)
        frontend = _frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS)

        golden_keys = set(_by_key(golden).keys())
        frontend_keys = set(_by_key(frontend).keys())
        assert frontend_keys == golden_keys, (
            f"business-key mismatch: golden-only={golden_keys - frontend_keys} "
            f"frontend-only={frontend_keys - golden_keys}"
        )

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_case_variant_specnames_collapse_into_one_group(self, mock_mapping):
        """"Epoxy D/B" + "epoxy d/b" -> ONE (2026-04-27, D, 焊接_DB) row, qty=150."""
        mock_mapping.return_value = _MAPPING
        golden = _by_key(build_achievement_rows(_golden_df(), targets=_TARGETS))
        frontend = _by_key(_frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS))

        key = ("2026-04-27", "D", "焊接_DB")
        assert golden[key]["actual_output_qty"] == 150
        assert frontend[key]["actual_output_qty"] == 150

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_unmapped_specname_excluded_both_sides(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = build_achievement_rows(_golden_df(), targets=_TARGETS)
        frontend = _frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS)

        assert all(r["workcenter_group"] != "UNKNOWN_SPEC" for r in golden)
        assert all(r["workcenter_group"] != "UNKNOWN_SPEC" for r in frontend)
        # UNKNOWN_SPEC's 999 qty must not leak into any group's actual_output_qty
        assert sum(r["actual_output_qty"] for r in golden) < 999
        assert sum(r["actual_output_qty"] for r in frontend) < 999

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_actual_output_qty_matches_per_key(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = _by_key(build_achievement_rows(_golden_df(), targets=_TARGETS))
        frontend = _by_key(_frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS))
        for key, g_row in golden.items():
            assert frontend[key]["actual_output_qty"] == g_row["actual_output_qty"], key


class TestProductionAchievementRateParity:
    """PA-07: target join + achievement_rate null/zero guards."""

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_missing_target_row_is_null_both_sides(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = _by_key(build_achievement_rows(_golden_df(), targets=_TARGETS))
        frontend = _by_key(_frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS))

        key = ("2026-04-27", "D", "焊接_DB")  # no ("D", "焊接_DB") target row
        assert golden[key]["target_qty"] is None
        assert golden[key]["achievement_rate"] is None
        assert frontend[key]["target_qty"] is None
        assert frontend[key]["achievement_rate"] is None

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_normal_division_matches(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = _by_key(build_achievement_rows(_golden_df(), targets=_TARGETS))
        frontend = _by_key(_frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS))

        key = ("2026-04-27", "N", "焊接_WB")  # 250 / 500 = 0.5
        assert golden[key]["achievement_rate"] == pytest.approx(0.5)
        assert frontend[key]["achievement_rate"] == pytest.approx(0.5)
        assert frontend[key]["achievement_rate"] == pytest.approx(golden[key]["achievement_rate"])

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_zero_actual_nonzero_target_is_zero_not_null(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = _by_key(build_achievement_rows(_golden_df(), targets=_TARGETS))
        frontend = _by_key(_frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _TARGETS_MAP_ROWS))

        # Sanity check on the shared fixture first (actual=500, target=500 -> 1.0):
        wb_key = ("2026-04-28", "N", "焊接_WB")
        assert golden[wb_key]["achievement_rate"] == pytest.approx(1.0)
        assert frontend[wb_key]["achievement_rate"] == pytest.approx(1.0)
        # Dedicated zero-actual + non-null-target case, isolated fixture:
        zero_actual_df = pd.DataFrame(
            [{"OUTPUT_DATE": "2026-05-01", "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 0}]
        )
        zero_actual_spool = [
            {"output_date": "2026-05-01", "shift_code": "D", "SPECNAME": "Epoxy D/B", "actual_output_qty": 0}
        ]
        nonzero_target = {("D", "焊接_DB"): 500}
        nonzero_target_rows = [{"shift_code": "D", "workcenter_group": "焊接_DB", "target_qty": 500}]

        golden_zero = build_achievement_rows(zero_actual_df, targets=nonzero_target)
        frontend_zero = _frontend_rows(zero_actual_spool, _SPEC_MAP_ROWS, nonzero_target_rows)

        assert golden_zero[0]["actual_output_qty"] == 0
        assert golden_zero[0]["achievement_rate"] == 0.0
        assert frontend_zero[0]["actual_output_qty"] == 0
        assert frontend_zero[0]["achievement_rate"] == 0.0

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_zero_stored_target_is_null_not_infinity_both_sides(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        golden = build_achievement_rows(_golden_df(), targets=_ZERO_TARGET_TARGETS)
        frontend = _frontend_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _ZERO_TARGET_MAP_ROWS)

        golden_row = _by_key(golden)[("2026-04-27", "D", "焊接_DB")]
        frontend_row = _by_key(frontend)[("2026-04-27", "D", "焊接_DB")]
        assert golden_row["target_qty"] == 0
        assert golden_row["achievement_rate"] is None
        assert frontend_row["target_qty"] == 0
        assert frontend_row["achievement_rate"] is None
        for row in frontend:
            assert row["achievement_rate"] != float("inf")


class TestProductionAchievementEmptySpoolParity:
    """Empty / all-unmapped spool -> empty rows on BOTH sides, never an error."""

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_empty_spool_yields_empty_rows_both_sides(self, mock_mapping):
        mock_mapping.return_value = _MAPPING
        empty_df = pd.DataFrame(columns=["OUTPUT_DATE", "SHIFT_CODE", "SPECNAME", "ACTUAL_OUTPUT_QTY"])
        golden = build_achievement_rows(empty_df, targets=_TARGETS)
        assert golden == []

        # Frontend side: a genuinely zero-row spool table with the exact
        # §3.28.1 schema (never omitted/errored — the empty-result invariant).
        conn = duckdb.connect(":memory:")
        try:
            conn.execute(
                "CREATE TABLE production_achievement_data ("
                "output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, actual_output_qty BIGINT)"
            )
            conn.execute(_build_spec_map_sql(_SPEC_MAP_ROWS))
            conn.execute(_build_targets_map_sql(_TARGETS_MAP_ROWS))
            conn.execute(_ROLLUP_SQL)
            result = conn.execute(_FINAL_SQL).fetchdf()
            assert len(result) == 0
        finally:
            conn.close()

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_all_unmapped_specnames_yields_empty_rows_both_sides(self, mock_mapping):
        mock_mapping.return_value = {}  # no mapping entries at all
        golden = build_achievement_rows(_golden_df(), targets=_TARGETS)
        assert golden == []

        frontend = _frontend_rows(_SPOOL_ROWS, spec_map_rows=[], targets_map_rows=_TARGETS_MAP_ROWS)
        assert frontend == []
