# -*- coding: utf-8 -*-
"""DuckDB SQL runtime correctness tests for resource-history.

Originally a pandas parity test (tasks 3.8 and 9.1). The Pandas derivation
path was retired in Phase 3; this file now verifies DuckDB SQL runtime
produces structurally correct, sane output against known sample data.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

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


# ── DuckDB correctness tests ─────────────────────────────────────────────────

class TestResourceHistorySqlParity:
    """DuckDB SQL runtime produces structurally correct, sane output."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.df = _build_sample_df(7)
        self.parquet_path = _write_parquet(self.df, str(tmp_path))

    def test_kpi_structure_and_sanity(self):
        result = _run_duckdb_view(self.parquet_path)
        kpi = result["summary"]["kpi"]
        expected_keys = [
            "ou_pct", "availability_pct", "prd_hours", "sby_hours",
            "udt_hours", "sdt_hours", "egt_hours", "nst_hours",
            "prd_pct", "sby_pct", "udt_pct", "sdt_pct", "egt_pct", "nst_pct",
            "machine_count",
        ]
        for key in expected_keys:
            assert key in kpi, f"kpi missing key: {key}"
        assert kpi["machine_count"] == len(_RESOURCES)
        assert 0.0 <= kpi["ou_pct"] <= 100.0
        assert 0.0 <= kpi["availability_pct"] <= 100.0
        assert kpi["prd_hours"] > 0

    def test_trend_day_structure(self):
        result = _run_duckdb_view(self.parquet_path, granularity="day")
        trend = result["summary"]["trend"]
        assert len(trend) == 7  # 7 sample days
        for item in trend:
            assert "date" in item
            assert "ou_pct" in item
            assert "prd_hours" in item
            assert 0.0 <= item["ou_pct"] <= 100.0

    def test_trend_week_structure(self):
        result = _run_duckdb_view(self.parquet_path, granularity="week")
        trend = result["summary"]["trend"]
        assert len(trend) >= 1
        for item in trend:
            assert "date" in item
            assert "ou_pct" in item

    def test_heatmap_structure(self):
        result = _run_duckdb_view(self.parquet_path)
        heatmap = result["summary"]["heatmap"]
        assert len(heatmap) > 0
        for item in heatmap:
            assert "workcenter" in item
            assert "date" in item
            assert "ou_pct" in item
            assert 0.0 <= item["ou_pct"] <= 100.0

    def test_workcenter_comparison_structure(self):
        result = _run_duckdb_view(self.parquet_path)
        comparison = result["summary"]["workcenter_comparison"]
        assert len(comparison) == len(_WORKCENTERS)
        wc_names = {c["workcenter"] for c in comparison}
        assert wc_names == set(_WORKCENTERS)
        for c in comparison:
            assert "ou_pct" in c
            assert "prd_hours" in c
            assert "machine_count" in c
            assert c["machine_count"] > 0

    def test_detail_structure(self):
        result = _run_duckdb_view(self.parquet_path)
        detail = result["detail"]
        assert detail["total"] == len(_RESOURCES)
        assert len(detail["data"]) == len(_RESOURCES)
        for row in detail["data"]:
            for key in ["ou_pct", "availability_pct", "prd_hours", "sby_hours",
                        "udt_hours", "sdt_hours", "egt_hours", "nst_hours"]:
                assert key in row, f"detail row missing key: {key}"
                assert row[key] >= 0

    def test_empty_df(self):
        """Empty DataFrame returns zero-valued structure."""
        empty_df = pd.DataFrame(columns=[
            "HISTORYID", "DATA_DATE", "PRD_HOURS", "SBY_HOURS",
            "UDT_HOURS", "SDT_HOURS", "EGT_HOURS", "NST_HOURS", "TOTAL_HOURS",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_parquet(empty_df, tmp)
            result = _run_duckdb_view(path)
            assert result["summary"]["kpi"]["machine_count"] == 0
            assert result["detail"]["total"] == 0
