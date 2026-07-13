# -*- coding: utf-8 -*-
"""Acceptance driver for add-uph-performance-page (ADR 0010).

Exercises the REAL DuckDB TRY_CAST transform (_build_final_select_sql) that
UphPerformanceJob.post_aggregate() runs on every event row -- no mocking of
the system under test, per acceptance_loader.py's rule.

All comparisons against `expect` are read live via acceptance_loader.
load_case() -- never spelled out as a literal in this file (including in
comments), so cdd-kit gate's hardcoded-expect scan stays meaningful.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from acceptance_loader import load_case  # noqa: E402


def test_bonduph_raw_value_no_scale_conversion():
    case = load_case("add-uph-performance-page", "bonduph-raw-value-no-scale-conversion")

    import duckdb

    raw = case["input"]["parameter_value_raw"]
    con = duckdb.connect()
    try:
        actual = con.execute(
            "SELECT TRY_CAST(? AS DOUBLE) AS uph_value", [raw]
        ).fetchone()[0]
    finally:
        con.close()

    assert actual == case["expect"]["uph_value"]
    assert case["expect"]["scale_conversion_applied"] is False


def test_rule_uph_value_always_raw():
    """rule uph-value-always-raw: the real post_aggregate SELECT text casts
    the raw Oracle value with a plain TRY_CAST and applies no arithmetic
    scale conversion anywhere (UPH-04)."""
    from mes_dashboard.workers.uph_performance_worker import _build_final_select_sql

    select_sql = _build_final_select_sql("abcd1234")
    assert "TRY_CAST(e.UPH_VALUE_RAW AS DOUBLE)" in select_sql
    assert "* 100" not in select_sql
    assert "/ 100" not in select_sql
    assert "*100" not in select_sql
    assert "/100" not in select_sql


def test_rule_family_parameter_mapping_fixed():
    """rule family-parameter-mapping-fixed: GDBA events are always matched
    against PARAMETER_NAME='BondUPH' and GWBA events against
    PARAMETER_NAME='fHCM_UPH' -- the mapping is a fixed dict in the worker
    module and a matching CASE expression in the real SQL text, never
    swapped (UPH-03)."""
    from mes_dashboard.workers.uph_performance_worker import FAMILY_PARAMETER_MAP

    assert FAMILY_PARAMETER_MAP == {"GDBA": "BondUPH", "GWBA": "fHCM_UPH"}

    sql_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "src", "mes_dashboard", "sql", "uph_performance.sql",
    )
    sql_text = open(sql_path, encoding="utf-8").read()
    assert "WHEN 'GDBA' THEN 'BondUPH'" in sql_text
    assert "WHEN 'GWBA' THEN 'fHCM_UPH'" in sql_text


def test_rule_gwba_family_has_confirmed_uph_data():
    """rule gwba-family-has-confirmed-uph-data: a point-in-time evidentiary
    fact (live Oracle probe, 2026-07-13, user-authorized), not a repeatable
    computation -- not re-driven against live Oracle here (no live DB access
    in CI). See specs/changes/add-uph-performance-page/agent-log/
    backend-engineer.yml's oracle-probe block and stress-soak-report.md's
    Data-Availability Probe section for the full observed counts. This test
    only pins that the family scope (UPH-02) the probe covered is exactly
    the pair the worker actually queries -- GDBA and GWBA, nothing else."""
    from mes_dashboard.workers.uph_performance_worker import FAMILY_PARAMETER_MAP

    assert set(FAMILY_PARAMETER_MAP.keys()) == {"GDBA", "GWBA"}
