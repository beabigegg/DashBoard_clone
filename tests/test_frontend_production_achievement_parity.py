# -*- coding: utf-8 -*-
"""Dual-tier parity: frontend DuckDB-WASM SQL
(useProductionAchievementDuckDB.ts) vs Python golden references, for the
production-achievement 2-stage rollup pipeline.

History: added by change `production-achievement-async-spool` (ADR-0016) to
parity-check the single-stage `_buildRollup()`/`computeView()` SQL against
`build_achievement_rows()`. REWRITTEN by change `production-achievement-overhaul`
(qa-reviewer fix-back cycle): that single-stage pipeline was DELETED and
replaced by a 2-stage pipeline (`_buildRollupRaw()` -> `_buildRollup()`) plus
`computeDailyView()`/`computeCumulativeView()` (design.md "the two DuckDB
stages stay separate"; PACKAGE_LF promoted to a first-class grain dimension;
D1/D2 merge-mapping joins added). The PRIOR version of this file kept
green-passing while transcribing SQL for the deleted `_buildRollup()`/
`computeView()` -- a false-confidence parity gate on exactly this change's
riskiest new logic. This rewrite transcribes the CURRENT SQL and tests two
DISTINCT parity surfaces, both cited explicitly in business-rules.md PA-06's
Test Reference column:

  1. Stage 1 (`pa_rollup_raw`) vs `build_achievement_rows()` -- business-
     rules.md PA-06 pins THIS function's own grouping key/formula as
     "unchanged" by the PACKAGE_LF/D1/D2 extension (Stage 1 is still exactly
     SPECNAME -> raw workcenter_group, case-insensitive join, unmapped-
     SPECNAME exclusion) -- "browser: dual-tier parity test vs
     `build_achievement_rows()` reference". See
     TestProductionAchievementStage1RollupParity.

  2. The full 2-stage WIDENED business key (output_date, shift_code,
     workcenter_group[MERGED via D2], package_lf_group[resolved via D1]) vs
     a NEW pure-Python golden composed from the resolver functions the D1/D2
     services already expose explicitly as "parity-verification helper[s]"
     (`production_achievement_package_lf_service.resolve_package_lf_group`,
     `production_achievement_workcenter_merge_service.resolve_workcenter_merge_group`)
     -- NOT `build_achievement_rows()` itself, whose own scope PA-06 pins to
     Stage 1 only (see (1) above). This is business-rules.md PA-06's
     "browser: 2-stage pipeline parity test (PA-09/PA-10 joins)" reference.
     See TestProductionAchievementRollupParity (class name matches
     test-plan.md's Data-boundary row exactly).

Deliberately NOT covered here: PA-07's target-based `achievement_rate` (the
OLD `_FINAL_SQL`'s `LEFT JOIN pa_targets_map`). Verified directly against the
CURRENT `useProductionAchievementDuckDB.ts`: `computeDailyView()`/
`computeCumulativeView()` join only `pa_daily_plan_map`, never
`pa_targets_map` -- `pa_targets_map`/`updateTargetsMap()` are still
registered/updatable (feeding `TargetEditPanel.vue`'s still-present
edit-target UI via `useProductionAchievement.ts::saveTarget()`) but are no
longer joined into any rendered figure on this report. Recreating that join
as test-only SQL here would repeat the exact "parity test exercising deleted
logic" defect this rewrite fixes. PA-12/13's daily-plan-based achievement
formula (the one actually rendered) is covered by
`frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts`
(AC-10) and `tests/property/test_production_achievement_aggregate_invariant.py`
(D3), not this Python-side file.

Business-key diff performed via the `duckdb` Python package (same DuckDB SQL
dialect the browser's DuckDB-WASM engine runs) -- same convention as before.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import duckdb
import pandas as pd

from mes_dashboard.services.production_achievement_service import build_achievement_rows
from mes_dashboard.services.production_achievement_package_lf_service import (
    resolve_package_lf_group,
)
from mes_dashboard.services.production_achievement_workcenter_merge_service import (
    resolve_workcenter_merge_group,
)

# ── SQL literal helpers (mirrors useProductionAchievementDuckDB.ts's generic
#    buildValuesTableSql(), simplified: every inline map table built here --
#    spec_workcenter_map / workcenter_merge_map / package_lf_map -- is
#    all-VARCHAR, unlike the report envelope's numeric targets_map/
#    daily_plan_map, which this file no longer needs -- see module docstring) ──


def _sql_string(value: Any) -> str:
    if value is None:
        value = ""
    return "'" + str(value).replace("'", "''") + "'"


def _build_string_values_table_sql(table_name: str, col_names: List[str], rows: List[Dict[str, str]]) -> str:
    cols_sql = ", ".join(col_names)
    if not rows:
        null_select = ", ".join(f"CAST(NULL AS VARCHAR) AS {c}" for c in col_names)
        return f"CREATE OR REPLACE TABLE {table_name} AS SELECT {null_select} WHERE FALSE"
    values_rows = ["(" + ", ".join(_sql_string(row.get(c)) for c in col_names) + ")" for row in rows]
    values_sql = ",\n    ".join(values_rows)
    return f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM (VALUES\n    {values_sql}\n  ) AS t({cols_sql})"


def _build_spec_map_sql(rows: List[Dict[str, str]]) -> str:
    return _build_string_values_table_sql("pa_spec_workcenter_map", ["SPECNAME", "workcenter_group"], rows)


def _build_workcenter_merge_map_sql(rows: List[Dict[str, str]]) -> str:
    return _build_string_values_table_sql(
        "pa_workcenter_merge_map", ["raw_workcenter_group", "merged_workcenter_group"], rows
    )


def _build_package_lf_map_sql(rows: List[Dict[str, str]]) -> str:
    return _build_string_values_table_sql("pa_package_lf_map", ["raw_package_lf", "merged_group"], rows)


# ── Transcribed frontend SQL (useProductionAchievementDuckDB.ts, current) ───

_ROLLUP_RAW_SQL = """
    CREATE OR REPLACE TABLE pa_rollup_raw AS
    SELECT
      s.output_date AS output_date,
      s.shift_code AS shift_code,
      m.workcenter_group AS raw_workcenter_group,
      s.PACKAGE_LF AS raw_package_lf,
      SUM(s.actual_output_qty) AS actual_output_qty
    FROM production_achievement_data s
    INNER JOIN pa_spec_workcenter_map m
      ON UPPER(TRIM(CAST(s.SPECNAME AS VARCHAR))) = UPPER(TRIM(CAST(m.SPECNAME AS VARCHAR)))
    GROUP BY s.output_date, s.shift_code, m.workcenter_group, s.PACKAGE_LF
"""

_ROLLUP_SQL = """
    CREATE OR REPLACE TABLE pa_rollup AS
    SELECT
      r.output_date AS output_date,
      r.shift_code AS shift_code,
      wm.merged_workcenter_group AS workcenter_group,
      COALESCE(pm.merged_group, NULLIF(CAST(r.raw_package_lf AS VARCHAR), ''), '(未分類)') AS package_lf_group,
      SUM(r.actual_output_qty) AS actual_output_qty
    FROM pa_rollup_raw r
    INNER JOIN pa_workcenter_merge_map wm
      ON r.raw_workcenter_group = wm.raw_workcenter_group
    LEFT JOIN pa_package_lf_map pm
      ON r.raw_package_lf = pm.raw_package_lf
    GROUP BY r.output_date, r.shift_code, wm.merged_workcenter_group,
      COALESCE(pm.merged_group, NULLIF(CAST(r.raw_package_lf AS VARCHAR), ''), '(未分類)')
"""

_WIDENED_FINAL_SELECT_SQL = """
    SELECT
      strftime(CAST(output_date AS DATE), '%Y-%m-%d') AS output_date,
      shift_code,
      workcenter_group,
      package_lf_group,
      actual_output_qty
    FROM pa_rollup
    ORDER BY output_date, shift_code, workcenter_group, package_lf_group
"""

# Stage-1-only re-aggregation down to (output_date, shift_code,
# raw_workcenter_group) -- collapses the PACKAGE_LF passthrough dimension
# pa_rollup_raw now carries, to compare against build_achievement_rows()'s
# own (unchanged, PACKAGE_LF-less) grain.
_STAGE1_FINAL_SELECT_SQL = """
    SELECT
      strftime(CAST(output_date AS DATE), '%Y-%m-%d') AS output_date,
      shift_code,
      raw_workcenter_group AS workcenter_group,
      SUM(actual_output_qty) AS actual_output_qty
    FROM pa_rollup_raw
    GROUP BY output_date, shift_code, raw_workcenter_group
    ORDER BY output_date, shift_code, raw_workcenter_group
"""


def _frontend_stage1_rows(
    spool_rows: List[Dict[str, Any]], spec_map_rows: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    conn = duckdb.connect(":memory:")
    try:
        conn.register("production_achievement_data", pd.DataFrame(spool_rows))
        conn.execute(_build_spec_map_sql(spec_map_rows))
        conn.execute(_ROLLUP_RAW_SQL)
        result = conn.execute(_STAGE1_FINAL_SELECT_SQL).fetchdf()
        return [
            {
                "output_date": str(row["output_date"]),
                "shift_code": str(row["shift_code"]),
                "workcenter_group": str(row["workcenter_group"]),
                "actual_output_qty": int(row["actual_output_qty"]),
            }
            for _, row in result.iterrows()
        ]
    finally:
        conn.close()


def _frontend_widened_rows(
    spool_rows: List[Dict[str, Any]],
    spec_map_rows: List[Dict[str, str]],
    workcenter_merge_rows: List[Dict[str, str]],
    package_lf_rows: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    conn = duckdb.connect(":memory:")
    try:
        conn.register("production_achievement_data", pd.DataFrame(spool_rows))
        conn.execute(_build_spec_map_sql(spec_map_rows))
        conn.execute(_build_workcenter_merge_map_sql(workcenter_merge_rows))
        conn.execute(_build_package_lf_map_sql(package_lf_rows))
        conn.execute(_ROLLUP_RAW_SQL)
        conn.execute(_ROLLUP_SQL)
        result = conn.execute(_WIDENED_FINAL_SELECT_SQL).fetchdf()
        return [
            {
                "output_date": str(row["output_date"]),
                "shift_code": str(row["shift_code"]),
                "workcenter_group": str(row["workcenter_group"]),
                "package_lf_group": str(row["package_lf_group"]),
                "actual_output_qty": int(row["actual_output_qty"]),
            }
            for _, row in result.iterrows()
        ]
    finally:
        conn.close()


def _golden_widened_rows(
    spool_rows: List[Dict[str, Any]],
    spec_map: Dict[str, str],
    workcenter_merge_map: Dict[str, str],
    package_lf_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Pure-Python golden reference for the WIDENED business key
    (output_date, shift_code, workcenter_group, package_lf_group) -- composed
    from the resolver functions the D1/D2 services expose as parity-
    verification helpers, NOT build_achievement_rows() (see module docstring
    for why that function's own scope stays Stage-1-only)."""
    grouped: Dict[Tuple[str, str, str, str], int] = {}
    for row in spool_rows:
        specname = row.get("SPECNAME")
        if specname is None:
            continue
        raw_group = spec_map.get(str(specname).strip().upper())
        if not raw_group:
            continue  # PA-06 unmapped-SPECNAME exclusion (unchanged)
        merged_group = resolve_workcenter_merge_group(raw_group, workcenter_merge_map)
        if merged_group is None:
            continue  # D2 exclude-by-absence (PA-10)
        package_lf_group = resolve_package_lf_group(row.get("PACKAGE_LF"), package_lf_map)
        qty = row.get("actual_output_qty") or 0
        key = (str(row["output_date"]), str(row["shift_code"]), merged_group, package_lf_group)
        grouped[key] = grouped.get(key, 0) + int(qty)

    rows = [
        {
            "output_date": k[0],
            "shift_code": k[1],
            "workcenter_group": k[2],
            "package_lf_group": k[3],
            "actual_output_qty": v,
        }
        for k, v in grouped.items()
    ]
    rows.sort(key=lambda r: (r["output_date"], r["shift_code"], r["workcenter_group"], r["package_lf_group"]))
    return rows


def _by_key3(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    return {(r["output_date"], r["shift_code"], r["workcenter_group"]): r for r in rows}


def _by_key4(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    return {(r["output_date"], r["shift_code"], r["workcenter_group"], r["package_lf_group"]): r for r in rows}


# ── Fixture 1: Stage-1-only (business-rules.md PA-06, unchanged grain) ──────
#
# Self-contained, independent of D1/D2 -- Stage 1 has no concept of either
# merge-mapping table. Every row still carries a PACKAGE_LF value (the real
# Stage-1 SQL now unconditionally selects s.PACKAGE_LF -- the column must
# exist on the registered spool table), but it is dropped by the
# re-aggregation in _STAGE1_FINAL_SELECT_SQL, matching build_achievement_rows()'s
# own PACKAGE_LF-less grain (its own dedicated "PACKAGE_LF passthrough" test
# lives in test_production_achievement_service.py).
_STAGE1_MAPPING: Dict[str, Dict[str, Any]] = {
    "EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1},
    "金線製程": {"workcenter": "WC2", "group": "焊接_WB", "sequence": 2},
}
_STAGE1_SPEC_MAP_ROWS: List[Dict[str, str]] = [
    {"SPECNAME": spec, "workcenter_group": info["group"]} for spec, info in _STAGE1_MAPPING.items()
]
_STAGE1_SPOOL_ROWS: List[Dict[str, Any]] = [
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 100},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "epoxy d/b", "PACKAGE_LF": "SOT23-6L", "actual_output_qty": 50},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "UNKNOWN_SPEC", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 999},
    {"output_date": "2026-04-27", "shift_code": "N", "SPECNAME": "金線製程", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 250},
]


def _stage1_golden_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "OUTPUT_DATE": r["output_date"],
                "SHIFT_CODE": r["shift_code"],
                "SPECNAME": r["SPECNAME"],
                "ACTUAL_OUTPUT_QTY": r["actual_output_qty"],
            }
            for r in _STAGE1_SPOOL_ROWS
        ]
    )


class TestProductionAchievementStage1RollupParity:
    """Stage 1 (`pa_rollup_raw`) vs `build_achievement_rows()`. business-
    rules.md PA-06: "This rule's own grouping key, formula, and unmapped-
    SPECNAME exclusion described above are themselves unchanged by [the
    PACKAGE_LF/D1/D2] extension" -- still SPECNAME -> raw workcenter_group
    only, no merge-mapping applied at this stage."""

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_business_key_sets_match(self, mock_mapping):
        mock_mapping.return_value = _STAGE1_MAPPING
        golden = build_achievement_rows(_stage1_golden_df(), targets={})
        frontend = _frontend_stage1_rows(_STAGE1_SPOOL_ROWS, _STAGE1_SPEC_MAP_ROWS)

        golden_keys = set(_by_key3(golden).keys())
        frontend_keys = set(_by_key3(frontend).keys())
        assert frontend_keys == golden_keys, (
            f"business-key mismatch: golden-only={golden_keys - frontend_keys} "
            f"frontend-only={frontend_keys - golden_keys}"
        )

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_case_variant_specnames_collapse_into_one_group(self, mock_mapping):
        """"Epoxy D/B" + "epoxy d/b" -> ONE (2026-04-27, D, 焊接_DB) row, qty=150."""
        mock_mapping.return_value = _STAGE1_MAPPING
        golden = _by_key3(build_achievement_rows(_stage1_golden_df(), targets={}))
        frontend = _by_key3(_frontend_stage1_rows(_STAGE1_SPOOL_ROWS, _STAGE1_SPEC_MAP_ROWS))

        key = ("2026-04-27", "D", "焊接_DB")
        assert golden[key]["actual_output_qty"] == 150
        assert frontend[key]["actual_output_qty"] == 150

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_unmapped_specname_excluded_both_sides(self, mock_mapping):
        mock_mapping.return_value = _STAGE1_MAPPING
        golden = build_achievement_rows(_stage1_golden_df(), targets={})
        frontend = _frontend_stage1_rows(_STAGE1_SPOOL_ROWS, _STAGE1_SPEC_MAP_ROWS)

        assert all(r["workcenter_group"] != "UNKNOWN_SPEC" for r in golden)
        assert all(r["workcenter_group"] != "UNKNOWN_SPEC" for r in frontend)
        # UNKNOWN_SPEC's 999 qty must not leak into any group's actual_output_qty
        assert sum(r["actual_output_qty"] for r in golden) < 999
        assert sum(r["actual_output_qty"] for r in frontend) < 999

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_actual_output_qty_matches_per_key(self, mock_mapping):
        mock_mapping.return_value = _STAGE1_MAPPING
        golden = _by_key3(build_achievement_rows(_stage1_golden_df(), targets={}))
        frontend = _by_key3(_frontend_stage1_rows(_STAGE1_SPOOL_ROWS, _STAGE1_SPEC_MAP_ROWS))
        for key, g_row in golden.items():
            assert frontend[key]["actual_output_qty"] == g_row["actual_output_qty"], key


# ── Fixture 2: 2-stage widened grain (D1 + D2 in the SAME fixture) ──────────
#
# SPEC_MAP resolves 4 SPECNAMEs to 4 distinct raw workcenter_groups:
#   EPOXY D/B  -> 焊接_DB      (D2: included, 1:1)
#   金線製程    -> 焊接_WB      (D2: included, one arm of a 2-raw merge)
#   銀線製程    -> 焊接_WB_二   (D2: included, MERGES into 焊接_WB -- same
#                                merged group as 金線製程's raw group via a
#                                DIFFERENT raw group, proving D2 does a real
#                                merge, not just inclusion passthrough)
#   切割製程    -> 切割         (D2: raw group absent from the merge map ->
#                                excluded entirely)
_SPEC_MAP: Dict[str, str] = {
    "EPOXY D/B": "焊接_DB",
    "金線製程": "焊接_WB",
    "銀線製程": "焊接_WB_二",
    "切割製程": "切割",
}
_SPEC_MAP_ROWS: List[Dict[str, str]] = [
    {"SPECNAME": spec, "workcenter_group": raw_group} for spec, raw_group in _SPEC_MAP.items()
]

# D2 (PA-10): "切割" deliberately ABSENT -> exclude-by-absence.
_WORKCENTER_MERGE_MAP: Dict[str, str] = {
    "焊接_DB": "焊接_DB",
    "焊接_WB": "焊接_WB",
    "焊接_WB_二": "焊接_WB",
}
_WORKCENTER_MERGE_MAP_ROWS: List[Dict[str, str]] = [
    {"raw_workcenter_group": raw, "merged_workcenter_group": merged}
    for raw, merged in _WORKCENTER_MERGE_MAP.items()
]

# D1 (PA-09): "SOD-123FL"/"TO-277" deliberately ABSENT -> fallback-to-self.
_PACKAGE_LF_MAP: Dict[str, str] = {
    "SOT23-5L": "SOT23-5L/6L",
    "SOT23-6L": "SOT23-5L/6L",
}
_PACKAGE_LF_MAP_ROWS: List[Dict[str, str]] = [
    {"raw_package_lf": raw, "merged_group": merged} for raw, merged in _PACKAGE_LF_MAP.items()
]

# Main widened-grain fixture -- covers, in ONE shared spool (per the fix-back
# instructions, D1 and D2's riskiest/opposite behaviors must share a fixture):
#   r1+r2: case-variant SPECNAME collapse (still applies at Stage 1) AND a D1
#          merge-of-two-raw-package-lf-values landing in ONE output row.
#   r3:    D1 fallback-to-self (raw PACKAGE_LF "SOD-123FL" has no map row).
#   r4+r5: D1 NULL and blank PACKAGE_LF both resolve to the "(未分類)" sentinel.
#   r6:    unmapped SPECNAME -- excluded (PA-06, unchanged).
#   r7:    D2 exclude-by-absence -- raw workcenter_group "切割" has no merge
#          row, dropped entirely (never falls back to itself -- that would be
#          D1's opposite default).
#   r8+r9: D2 merge-of-two-raw-workcenter-groups (焊接_WB + 焊接_WB_二) landing
#          in ONE merged group, AND a second D1 merge-of-two-raw-package-lf
#          pair, combined.
# Verified by direct execution against the real resolve_package_lf_group()/
# resolve_workcenter_merge_group() before being hard-coded below (backend-
# engineer fix-back session) -- see agent-log for the reproduction.
_SPOOL_ROWS: List[Dict[str, Any]] = [
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 100},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "epoxy d/b", "PACKAGE_LF": "SOT23-6L", "actual_output_qty": 50},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": "SOD-123FL", "actual_output_qty": 30},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": None, "actual_output_qty": 20},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": "", "actual_output_qty": 5},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "UNKNOWN_SPEC", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 999},
    {"output_date": "2026-04-27", "shift_code": "D", "SPECNAME": "切割製程", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 777},
    {"output_date": "2026-04-27", "shift_code": "N", "SPECNAME": "金線製程", "PACKAGE_LF": "SOT23-5L", "actual_output_qty": 250},
    {"output_date": "2026-04-27", "shift_code": "N", "SPECNAME": "銀線製程", "PACKAGE_LF": "SOT23-6L", "actual_output_qty": 60},
]

# Dedicated fixture for test_multiple_package_lf_per_specname_day_parity: the
# SAME (output_date, shift_code, SPECNAME) triple with two DIFFERENT raw
# PACKAGE_LF values, neither mapped -> must fan out into TWO distinct output
# rows (never collapsed together), each independently fallback-to-self (D1).
_MULTI_PACKAGE_LF_SAME_DAY_ROWS: List[Dict[str, Any]] = [
    {"output_date": "2026-04-28", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": "SOD-123FL", "actual_output_qty": 40},
    {"output_date": "2026-04-28", "shift_code": "D", "SPECNAME": "Epoxy D/B", "PACKAGE_LF": "TO-277", "actual_output_qty": 15},
]


class TestProductionAchievementRollupParity:
    """Full 2-stage widened business key (output_date, shift_code,
    workcenter_group[post-D2], package_lf_group[post-D1]) -- business-
    rules.md PA-06's "browser: 2-stage pipeline parity test (PA-09/PA-10
    joins)" reference. Golden side composed from resolve_workcenter_merge_group
    (D2) + resolve_package_lf_group (D1), the services' own parity-
    verification-helper functions -- see module docstring for why
    build_achievement_rows() itself is NOT used here."""

    def _golden(self) -> List[Dict[str, Any]]:
        return _golden_widened_rows(_SPOOL_ROWS, _SPEC_MAP, _WORKCENTER_MERGE_MAP, _PACKAGE_LF_MAP)

    def _frontend(self) -> List[Dict[str, Any]]:
        return _frontend_widened_rows(_SPOOL_ROWS, _SPEC_MAP_ROWS, _WORKCENTER_MERGE_MAP_ROWS, _PACKAGE_LF_MAP_ROWS)

    def test_business_key_sets_match_widened_grain(self):
        golden_keys = set(_by_key4(self._golden()).keys())
        frontend_keys = set(_by_key4(self._frontend()).keys())
        assert frontend_keys == golden_keys, (
            f"widened business-key mismatch: golden-only={golden_keys - frontend_keys} "
            f"frontend-only={frontend_keys - golden_keys}"
        )

    def test_case_variant_specnames_collapse_into_one_group(self):
        """"Epoxy D/B" + "epoxy d/b" -> ONE (…, 焊接_DB, SOT23-5L/6L) row,
        qty=150 (also exercises a D1 merge-of-two-raw-PACKAGE_LF pair)."""
        golden = _by_key4(self._golden())
        frontend = _by_key4(self._frontend())
        key = ("2026-04-27", "D", "焊接_DB", "SOT23-5L/6L")
        assert golden[key]["actual_output_qty"] == 150
        assert frontend[key]["actual_output_qty"] == 150

    def test_unmapped_specname_excluded_both_sides(self):
        """"UNKNOWN_SPEC" has no SPECNAME mapping at all -- excluded (PA-06,
        unchanged) both sides; its qty=999 (and "切割製程"'s qty=777, D2-
        excluded) must never leak into any total (the fixture's full sum is
        2291; only 515 legitimately survives both exclusions)."""
        golden = self._golden()
        frontend = self._frontend()
        assert sum(r["actual_output_qty"] for r in golden) == 515
        assert sum(r["actual_output_qty"] for r in frontend) == 515

    def test_d1_fallback_to_self_for_unmapped_raw_package_lf(self):
        """D1 (PA-09): raw PACKAGE_LF "SOD-123FL" has no package_lf_map row
        -> groups under itself, NOT excluded (that would be D2's opposite
        default)."""
        golden = _by_key4(self._golden())
        frontend = _by_key4(self._frontend())
        key = ("2026-04-27", "D", "焊接_DB", "SOD-123FL")
        assert golden[key]["actual_output_qty"] == 30
        assert frontend[key]["actual_output_qty"] == 30

    def test_d1_null_and_blank_package_lf_resolve_to_sentinel(self):
        """D1 (PA-09): NULL and blank raw PACKAGE_LF both resolve to the
        "(未分類)" sentinel and combine into ONE row, qty=20+5=25."""
        golden = _by_key4(self._golden())
        frontend = _by_key4(self._frontend())
        key = ("2026-04-27", "D", "焊接_DB", "(未分類)")
        assert golden[key]["actual_output_qty"] == 25
        assert frontend[key]["actual_output_qty"] == 25

    def test_d2_excludes_raw_workcenter_group_absent_from_merge_map(self):
        """D2 (PA-10): raw workcenter_group "切割" has no workcenter_merge_map
        row -> the entire row (qty=777) is EXCLUDED, never falls back to
        itself (that would be D1's opposite default)."""
        golden = self._golden()
        frontend = self._frontend()
        assert all(r["workcenter_group"] != "切割" for r in golden)
        assert all(r["workcenter_group"] != "切割" for r in frontend)

    def test_d2_merges_two_raw_groups_into_one_merged_group(self):
        """D2 (PA-10): two DIFFERENT raw workcenter_groups (焊接_WB, 焊接_WB_二)
        both merge into 焊接_WB -- a real merge, not just inclusion
        passthrough. Combined with a D1 merge-of-two-raw-PACKAGE_LF pair:
        qty=250+60=310."""
        golden = _by_key4(self._golden())
        frontend = _by_key4(self._frontend())
        key = ("2026-04-27", "N", "焊接_WB", "SOT23-5L/6L")
        assert golden[key]["actual_output_qty"] == 310
        assert frontend[key]["actual_output_qty"] == 310

    def test_d1_and_d2_are_not_swapped_join_kinds(self):
        """Guard against the easiest copy-paste inversion (business-rules.md
        PA-09/PA-10 explicitly flags this): for the SAME absent raw string
        ("切割"), D2 (workcenter_merge_map) EXCLUDES while D1
        (package_lf_map) would FALL BACK TO SELF -- the two joins must never
        agree on an absent key."""
        assert resolve_workcenter_merge_group("切割", _WORKCENTER_MERGE_MAP) is None
        assert resolve_package_lf_group("切割", _PACKAGE_LF_MAP) == "切割"
        # SQL-level confirmation on the actual pipeline output: "切割"
        # (excluded raw workcenter_group) never appears as workcenter_group,
        # but "SOD-123FL" (an equally-unmapped raw PACKAGE_LF) DOES appear as
        # package_lf_group -- opposite join kinds, same fixture.
        frontend = self._frontend()
        assert all(r["workcenter_group"] != "切割" for r in frontend)
        assert any(r["package_lf_group"] == "SOD-123FL" for r in frontend)

    def test_multiple_package_lf_per_specname_day_parity(self):
        """The SAME (output_date, shift_code, SPECNAME) triple with two
        different, both-unmapped raw PACKAGE_LF values must fan out into TWO
        distinct output rows (never collapsed together) -- each
        independently fallback-to-self (D1)."""
        golden = _by_key4(
            _golden_widened_rows(_MULTI_PACKAGE_LF_SAME_DAY_ROWS, _SPEC_MAP, _WORKCENTER_MERGE_MAP, _PACKAGE_LF_MAP)
        )
        frontend = _by_key4(
            _frontend_widened_rows(
                _MULTI_PACKAGE_LF_SAME_DAY_ROWS, _SPEC_MAP_ROWS, _WORKCENTER_MERGE_MAP_ROWS, _PACKAGE_LF_MAP_ROWS
            )
        )
        key_a = ("2026-04-28", "D", "焊接_DB", "SOD-123FL")
        key_b = ("2026-04-28", "D", "焊接_DB", "TO-277")
        assert set(golden.keys()) == {key_a, key_b}
        assert set(frontend.keys()) == {key_a, key_b}
        assert golden[key_a]["actual_output_qty"] == frontend[key_a]["actual_output_qty"] == 40
        assert golden[key_b]["actual_output_qty"] == frontend[key_b]["actual_output_qty"] == 15


class TestProductionAchievementEmptySpoolParity:
    """Empty / all-unmapped spool -> empty rows on BOTH sides, never an
    error (widened 5-column §3.28.1 schema)."""

    def test_empty_spool_yields_empty_rows_both_sides(self):
        assert _golden_widened_rows([], _SPEC_MAP, _WORKCENTER_MERGE_MAP, _PACKAGE_LF_MAP) == []

        # A genuinely zero-row spool table with the exact widened §3.28.1
        # schema (never omitted/errored -- the empty-result invariant).
        conn = duckdb.connect(":memory:")
        try:
            conn.execute(
                "CREATE TABLE production_achievement_data ("
                "output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, "
                "PACKAGE_LF VARCHAR, actual_output_qty BIGINT)"
            )
            conn.execute(_build_spec_map_sql(_SPEC_MAP_ROWS))
            conn.execute(_build_workcenter_merge_map_sql(_WORKCENTER_MERGE_MAP_ROWS))
            conn.execute(_build_package_lf_map_sql(_PACKAGE_LF_MAP_ROWS))
            conn.execute(_ROLLUP_RAW_SQL)
            conn.execute(_ROLLUP_SQL)
            result = conn.execute(_WIDENED_FINAL_SELECT_SQL).fetchdf()
            assert len(result) == 0
        finally:
            conn.close()

    def test_all_unmapped_specnames_yields_empty_rows_both_sides(self):
        assert _golden_widened_rows(_SPOOL_ROWS, {}, _WORKCENTER_MERGE_MAP, _PACKAGE_LF_MAP) == []
        assert _frontend_widened_rows(_SPOOL_ROWS, [], _WORKCENTER_MERGE_MAP_ROWS, _PACKAGE_LF_MAP_ROWS) == []
