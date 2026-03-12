# -*- coding: utf-8 -*-
"""Parity tests: resource-history DuckDB SQL runtime vs Pandas derivation.

Covers tasks 3.8 and 9.1 — verifies that the DuckDB out-of-core view
computation produces identical results to the Pandas-based derivation for
all sub-views (kpi / trend / heatmap / workcenter_comparison / detail).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import pandas as pd
import pytest

# ── Sample data ──────────────────────────────────────────────────────────────

_WORKCENTERS = ["WC_ALPHA", "WC_BETA", "WC_GAMMA"]
_FAMILIES = ["FAM_X", "FAM_Y"]
_RESOURCES = ["RES_001", "RES_002", "RES_003", "RES_004", "RES_005"]

# Dimension lookups matching the sample data
_RESOURCE_LOOKUP: Dict[str, Dict[str, Any]] = {}
_WC_MAPPING: Dict[str, Dict[str, Any]] = {
    "WC_ALPHA": {"group": "WC_ALPHA", "sequence": 1},
    "WC_BETA": {"group": "WC_BETA", "sequence": 2},
    "WC_GAMMA": {"group": "WC_GAMMA", "sequence": 3},
}


def _build_sample_df(n_days: int = 7) -> pd.DataFrame:
    """Build a realistic resource-history DataFrame."""
    import random
    random.seed(42)

    rows = []
    for res_idx, resource in enumerate(_RESOURCES):
        historyid = f"H{res_idx + 1:04d}"
        wc = _WORKCENTERS[res_idx % len(_WORKCENTERS)]
        family = _FAMILIES[res_idx % len(_FAMILIES)]

        _RESOURCE_LOOKUP[historyid] = {
            "WORKCENTERNAME": wc,
            "RESOURCEFAMILYNAME": family,
            "RESOURCENAME": resource,
        }

        for day in range(n_days):
            date_str = f"2026-01-{day + 1:02d}"
            prd = round(random.uniform(5, 15), 2)
            sby = round(random.uniform(1, 4), 2)
            udt = round(random.uniform(0.5, 3), 2)
            sdt = round(random.uniform(0.2, 2), 2)
            egt = round(random.uniform(0, 1), 2)
            nst = round(random.uniform(0, 0.5), 2)
            total = round(prd + sby + udt + sdt + egt + nst, 2)

            rows.append({
                "HISTORYID": historyid,
                "DATA_DATE": date_str,
                "PRD_HOURS": prd,
                "SBY_HOURS": sby,
                "UDT_HOURS": udt,
                "SDT_HOURS": sdt,
                "EGT_HOURS": egt,
                "NST_HOURS": nst,
                "TOTAL_HOURS": total,
            })

    return pd.DataFrame(rows)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_parquet(df: pd.DataFrame, tmp_dir: str) -> str:
    """Write DataFrame to a temporary Parquet file and return path."""
    path = str(Path(tmp_dir) / "test_resource.parquet")
    df.to_parquet(path, index=False, engine="pyarrow")
    return path


def _run_duckdb_view(parquet_path: str, granularity: str = "day") -> Dict[str, Any]:
    """Run the DuckDB SQL runtime directly against a Parquet file."""
    import duckdb
    from mes_dashboard.services.resource_history_sql_runtime import (
        _attach_spool_view,
        _build_resource_lookup_table,
        _query_kpi,
        _query_trend,
        _query_heatmap,
        _query_workcenter_comparison,
        _query_detail,
    )

    conn = duckdb.connect(database=":memory:")
    try:
        _attach_spool_view(conn, parquet_path)
        _build_resource_lookup_table(conn, _RESOURCE_LOOKUP, _WC_MAPPING)

        return {
            "summary": {
                "kpi": _query_kpi(conn),
                "trend": _query_trend(conn, granularity=granularity),
                "heatmap": _query_heatmap(conn, granularity=granularity),
                "workcenter_comparison": _query_workcenter_comparison(conn),
            },
            "detail": _query_detail(conn),
        }
    finally:
        conn.close()


def _run_pandas_view(df: pd.DataFrame, granularity: str = "day") -> Dict[str, Any]:
    """Run the Pandas-based derivation."""
    from mes_dashboard.services.resource_dataset_cache import (
        _derive_summary,
        _derive_detail,
    )

    summary = _derive_summary(df, _RESOURCE_LOOKUP, _WC_MAPPING, granularity)
    detail = _derive_detail(df, _RESOURCE_LOOKUP, _WC_MAPPING)
    return {"summary": summary, "detail": detail}


# ── Parity assertions ───────────────────────────────────────────────────────

def _assert_float_close(a: float, b: float, label: str, tol: float = 0.15):
    """Assert two floats are within tolerance."""
    assert abs(float(a) - float(b)) <= tol, (
        f"{label}: DuckDB={a} vs Pandas={b} (diff={abs(float(a)-float(b)):.4f}, tol={tol})"
    )


# ── Test class ───────────────────────────────────────────────────────────────

class TestResourceHistorySqlParity:
    """DuckDB SQL runtime must produce same results as Pandas derivation."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.df = _build_sample_df(7)
        self.parquet_path = _write_parquet(self.df, str(tmp_path))

    def test_kpi_parity(self):
        duck = _run_duckdb_view(self.parquet_path)
        pandas_result = _run_pandas_view(self.df)

        dk = duck["summary"]["kpi"]
        pk = pandas_result["summary"]["kpi"]

        for key in ["ou_pct", "availability_pct", "prd_hours", "sby_hours",
                     "udt_hours", "sdt_hours", "egt_hours", "nst_hours",
                     "prd_pct", "sby_pct", "udt_pct", "sdt_pct", "egt_pct", "nst_pct"]:
            _assert_float_close(dk[key], pk[key], f"kpi.{key}")

        assert dk["machine_count"] == pk["machine_count"], (
            f"machine_count: DuckDB={dk['machine_count']} vs Pandas={pk['machine_count']}"
        )

    def test_trend_parity_day(self):
        duck = _run_duckdb_view(self.parquet_path, granularity="day")
        pandas_result = _run_pandas_view(self.df, granularity="day")

        dt = duck["summary"]["trend"]
        pt = pandas_result["summary"]["trend"]

        assert len(dt) == len(pt), f"trend length: DuckDB={len(dt)} vs Pandas={len(pt)}"

        # Sort both by date for comparison
        dt_sorted = sorted(dt, key=lambda x: x["date"])
        pt_sorted = sorted(pt, key=lambda x: x["date"])

        for i, (d, p) in enumerate(zip(dt_sorted, pt_sorted)):
            assert d["date"] == p["date"], f"trend[{i}].date: {d['date']} vs {p['date']}"
            _assert_float_close(d["ou_pct"], p["ou_pct"], f"trend[{i}].ou_pct")
            _assert_float_close(d["prd_hours"], p["prd_hours"], f"trend[{i}].prd_hours")

    def test_trend_parity_week(self):
        duck = _run_duckdb_view(self.parquet_path, granularity="week")
        pandas_result = _run_pandas_view(self.df, granularity="week")

        dt = duck["summary"]["trend"]
        pt = pandas_result["summary"]["trend"]

        assert len(dt) == len(pt), f"trend(week) length: DuckDB={len(dt)} vs Pandas={len(pt)}"

    def test_heatmap_parity(self):
        duck = _run_duckdb_view(self.parquet_path)
        pandas_result = _run_pandas_view(self.df)

        dh = duck["summary"]["heatmap"]
        ph = pandas_result["summary"]["heatmap"]

        assert len(dh) == len(ph), f"heatmap length: DuckDB={len(dh)} vs Pandas={len(ph)}"

        # Build lookup: (workcenter, date) -> ou_pct
        d_map = {(h["workcenter"], h["date"]): h["ou_pct"] for h in dh}
        p_map = {(h["workcenter"], h["date"]): h["ou_pct"] for h in ph}

        assert set(d_map.keys()) == set(p_map.keys()), "heatmap keys differ"

        for key in d_map:
            _assert_float_close(d_map[key], p_map[key], f"heatmap[{key}].ou_pct")

    def test_workcenter_comparison_parity(self):
        duck = _run_duckdb_view(self.parquet_path)
        pandas_result = _run_pandas_view(self.df)

        dc = duck["summary"]["workcenter_comparison"]
        pc = pandas_result["summary"]["workcenter_comparison"]

        assert len(dc) == len(pc), (
            f"comparison length: DuckDB={len(dc)} vs Pandas={len(pc)}"
        )

        d_map = {c["workcenter"]: c for c in dc}
        p_map = {c["workcenter"]: c for c in pc}

        assert set(d_map.keys()) == set(p_map.keys()), "comparison workcenters differ"

        for wc in d_map:
            _assert_float_close(d_map[wc]["ou_pct"], p_map[wc]["ou_pct"], f"comparison[{wc}].ou_pct")
            _assert_float_close(d_map[wc]["prd_hours"], p_map[wc]["prd_hours"], f"comparison[{wc}].prd_hours")
            assert d_map[wc]["machine_count"] == p_map[wc]["machine_count"], (
                f"comparison[{wc}].machine_count: {d_map[wc]['machine_count']} vs {p_map[wc]['machine_count']}"
            )

    def test_detail_parity(self):
        duck = _run_duckdb_view(self.parquet_path)
        pandas_result = _run_pandas_view(self.df)

        dd = duck["detail"]
        pd_detail = pandas_result["detail"]

        assert dd["total"] == pd_detail["total"], (
            f"detail total: DuckDB={dd['total']} vs Pandas={pd_detail['total']}"
        )

        # Build lookup by resource name
        d_map = {r["resource"]: r for r in dd["data"]}
        p_map = {r["resource"]: r for r in pd_detail["data"]}

        assert set(d_map.keys()) == set(p_map.keys()), "detail resources differ"

        for res in d_map:
            for key in ["ou_pct", "availability_pct", "prd_hours", "sby_hours",
                         "udt_hours", "sdt_hours", "egt_hours", "nst_hours"]:
                _assert_float_close(
                    d_map[res][key], p_map[res][key], f"detail[{res}].{key}"
                )

    def test_empty_df_parity(self):
        """Both paths should handle empty DataFrames gracefully."""
        empty_df = pd.DataFrame(columns=[
            "HISTORYID", "DATA_DATE", "PRD_HOURS", "SBY_HOURS",
            "UDT_HOURS", "SDT_HOURS", "EGT_HOURS", "NST_HOURS", "TOTAL_HOURS",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_parquet(empty_df, tmp)
            duck = _run_duckdb_view(path)
            pandas_result = _run_pandas_view(empty_df)

            assert duck["summary"]["kpi"]["machine_count"] == 0
            assert pandas_result["summary"]["kpi"]["machine_count"] == 0
            assert duck["detail"]["total"] == 0
            assert pandas_result["detail"]["total"] == 0
