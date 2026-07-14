# -*- coding: utf-8 -*-
"""Acceptance driver for production-achievement-overhaul (ADR 0010).

Exercises the REAL DuckDB SQL expression that
useProductionAchievementDuckDB.ts's _buildRollup() runs for D1 (PACKAGE_LF
sparse-mapping, fallback-to-self, PA-09) -- no mocking of the system under
test, per acceptance_loader.py's rule. The SQL below is a literal
transcription of the production expression at
frontend/src/production-achievement/composables/useProductionAchievementDuckDB.ts
(COALESCE(pm.merged_group, NULLIF(CAST(r.raw_package_lf AS VARCHAR), ''),
'(未分類)'), LEFT JOIN pa_package_lf_map), executed via the real `duckdb`
Python package -- the same same-dialect, stronger-than-reimplementation
convention already established by
tests/test_frontend_production_achievement_parity.py for this exact feature.

All comparisons against `expect` are read live via acceptance_loader.
load_case() -- never spelled out as a literal in this file (including in
comments), so cdd-kit gate's hardcoded-expect scan stays meaningful.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from acceptance_loader import load_case  # noqa: E402

_SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "src", "production-achievement", "composables",
    "useProductionAchievementDuckDB.ts",
)


def test_package_lf_fallback_to_self():
    case = load_case("production-achievement-overhaul", "package-lf-fallback-to-self")

    import duckdb

    raw_package_lf = case["input"]["raw_package_lf"]
    package_lf_map = case["input"]["package_lf_map"]  # sparse exceptions-only rows

    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE r (raw_package_lf VARCHAR)")
        con.execute("INSERT INTO r VALUES (?)", [raw_package_lf])

        con.execute("CREATE TABLE pa_package_lf_map (raw_package_lf VARCHAR, merged_group VARCHAR)")
        for row in package_lf_map:
            con.execute(
                "INSERT INTO pa_package_lf_map VALUES (?, ?)",
                [row["raw_package_lf"], row["merged_group"]],
            )

        # Literal transcription of _buildRollup()'s D1 expression (see module
        # docstring for the exact source path/line).
        actual = con.execute(
            """
            SELECT
                COALESCE(pm.merged_group, NULLIF(CAST(r.raw_package_lf AS VARCHAR), ''), '(未分類)') AS merged_group
            FROM r
            LEFT JOIN pa_package_lf_map pm ON r.raw_package_lf = pm.raw_package_lf
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert actual == case["expect"]["merged_group"]


def test_rule_d1_uses_left_join_not_inner_join():
    """rule: D1's package_lf_map join in the real source must be LEFT JOIN,
    never INNER JOIN -- an INNER JOIN would silently drop every unmapped raw
    PACKAGE_LF value, which is D2's opposite default (workcenter_merge_map),
    not this table's (PA-09 vs PA-10, the easiest thing to invert by
    copy-paste). Pins the actual production SQL text, not a
    reimplementation."""
    sql_text = open(_SOURCE_PATH, encoding="utf-8").read()

    join_marker = "LEFT JOIN ${PACKAGE_LF_MAP_TABLE} pm"
    assert join_marker in sql_text, (
        "expected LEFT JOIN on PACKAGE_LF_MAP_TABLE not found in "
        + _SOURCE_PATH
        + " -- has _buildRollup() been restructured?"
    )
    # The sibling workcenter_merge_map join (D2) must remain INNER JOIN, the
    # deliberately opposite default -- this rule also guards against the two
    # ever being swapped.
    assert "INNER JOIN ${WORKCENTER_MERGE_MAP_TABLE} wm" in sql_text
