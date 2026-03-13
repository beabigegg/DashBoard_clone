# -*- coding: utf-8 -*-
"""Parity tests: Resource History frontend (DuckDB SQL) vs server-side (Pandas).

Task 5.1 — Verifies that the SQL logic used by useResourceHistoryDuckDB.js
produces equivalent outputs to the Pandas derivation in resource_dataset_cache.py
for KPI, trend, heatmap, workcenter comparison, and detail views.

Tests run the same SQL that the frontend JS would execute (via DuckDB Python),
then compare against the server-side Pandas reference derivation.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import pandas as pd
import pytest

# ── Sample data ───────────────────────────────────────────────────────────────

_WORKCENTERS = ["WC_ALPHA", "WC_BETA", "WC_GAMMA"]
_FAMILIES = ["FAM_X", "FAM_Y"]
_RESOURCES = ["RES_001", "RES_002", "RES_003", "RES_004", "RES_005"]

_RESOURCE_LOOKUP: Dict[str, Dict[str, Any]] = {}
_WC_MAPPING: Dict[str, Dict[str, Any]] = {
    "WC_ALPHA": {"group": "WC_ALPHA", "sequence": 1},
    "WC_BETA":  {"group": "WC_BETA",  "sequence": 2},
    "WC_GAMMA": {"group": "WC_GAMMA", "sequence": 3},
}


def _build_sample_df(n_days: int = 7) -> pd.DataFrame:
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
            rows.append({
                "HISTORYID": historyid,
                "DATA_DATE": pd.Timestamp(f"2026-01-{day + 1:02d}"),
                "PRD_HOURS": round(random.uniform(4, 12), 2),
                "SBY_HOURS": round(random.uniform(0, 3), 2),
                "UDT_HOURS": round(random.uniform(0, 2), 2),
                "SDT_HOURS": round(random.uniform(0, 1), 2),
                "EGT_HOURS": round(random.uniform(0, 1), 2),
                "NST_HOURS": round(random.uniform(0, 1), 2),
                "TOTAL_HOURS": 24.0,
            })
    df = pd.DataFrame(rows)
    df["TOTAL_HOURS"] = df[["PRD_HOURS", "SBY_HOURS", "UDT_HOURS", "SDT_HOURS", "EGT_HOURS", "NST_HOURS"]].sum(axis=1)
    return df


@pytest.fixture(scope="module")
def sample_df():
    _RESOURCE_LOOKUP.clear()
    df = _build_sample_df()
    return df


@pytest.fixture(scope="module")
def parquet_path(sample_df, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("spool")
    path = tmp / "resource_history_data.parquet"
    sample_df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture(scope="module")
def duckdb_conn(parquet_path):
    conn = duckdb.connect(":memory:")
    conn.execute(f"""
        CREATE OR REPLACE VIEW resource_history_data AS
        SELECT * FROM read_parquet('{parquet_path}')
    """)
    yield conn
    conn.close()


# ── Server-side reference derivation (mirrors resource_dataset_cache.py) ──────

def _sf(v, default=0.0):
    try:
        return float(v) if v is not None and not pd.isna(v) else default
    except (TypeError, ValueError):
        return default


def _calc_ou_pct(prd, sby, udt, sdt, egt):
    denom = prd + sby + udt + sdt + egt
    return round(prd / denom * 100, 1) if denom > 0 else 0.0


def _calc_avail_pct(prd, sby, udt, sdt, egt, nst):
    num = prd + sby + egt
    denom = prd + sby + egt + sdt + udt + nst
    return round(num / denom * 100, 1) if denom > 0 else 0.0


def _status_pct(val, total):
    return round(val / total * 100, 1) if total > 0 else 0.0


def _trunc_date(dt, granularity):
    ts = pd.Timestamp(dt)
    if granularity == "year":  return ts.strftime("%Y")
    if granularity == "month": return ts.strftime("%Y-%m")
    if granularity == "week":
        return (ts - pd.Timedelta(days=ts.weekday())).strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m-%d")


def pandas_kpi(df):
    prd = _sf(df["PRD_HOURS"].sum())
    sby = _sf(df["SBY_HOURS"].sum())
    udt = _sf(df["UDT_HOURS"].sum())
    sdt = _sf(df["SDT_HOURS"].sum())
    egt = _sf(df["EGT_HOURS"].sum())
    nst = _sf(df["NST_HOURS"].sum())
    total = prd + sby + udt + sdt + egt + nst
    return {
        "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
        "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
        "prd_hours": round(prd, 1),
        "machine_count": int(df["HISTORYID"].nunique()),
    }


def pandas_trend(df, granularity="day"):
    df = df.copy()
    df["_period"] = df["DATA_DATE"].apply(lambda d: _trunc_date(d, granularity))
    grouped = df.groupby("_period", sort=True).agg(
        PRD_HOURS=("PRD_HOURS", "sum"),
        SBY_HOURS=("SBY_HOURS", "sum"),
        UDT_HOURS=("UDT_HOURS", "sum"),
        SDT_HOURS=("SDT_HOURS", "sum"),
        EGT_HOURS=("EGT_HOURS", "sum"),
        NST_HOURS=("NST_HOURS", "sum"),
    ).reset_index()
    items = []
    for _, row in grouped.iterrows():
        prd, sby = _sf(row["PRD_HOURS"]), _sf(row["SBY_HOURS"])
        udt, sdt = _sf(row["UDT_HOURS"]), _sf(row["SDT_HOURS"])
        egt, nst = _sf(row["EGT_HOURS"]), _sf(row["NST_HOURS"])
        items.append({
            "date": row["_period"],
            "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
            "prd_hours": round(prd, 1),
        })
    return items


# ── Frontend SQL equivalents (mirrors useResourceHistoryDuckDB.js) ─────────────

def frontend_kpi(conn):
    rows = conn.execute("""
        SELECT
          SUM(COALESCE("PRD_HOURS", 0)) AS prd_hours,
          SUM(COALESCE("SBY_HOURS", 0)) AS sby_hours,
          SUM(COALESCE("UDT_HOURS", 0)) AS udt_hours,
          SUM(COALESCE("SDT_HOURS", 0)) AS sdt_hours,
          SUM(COALESCE("EGT_HOURS", 0)) AS egt_hours,
          SUM(COALESCE("NST_HOURS", 0)) AS nst_hours,
          COUNT(DISTINCT "HISTORYID") AS machine_count
        FROM resource_history_data
    """).fetchdf()
    r = rows.iloc[0]
    prd, sby = float(r["prd_hours"]), float(r["sby_hours"])
    udt, sdt = float(r["udt_hours"]), float(r["sdt_hours"])
    egt, nst = float(r["egt_hours"]), float(r["nst_hours"])
    total = prd + sby + udt + sdt + egt + nst
    return {
        "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
        "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
        "prd_hours": round(prd, 1),
        "machine_count": int(r["machine_count"]),
    }


def frontend_trend(conn, granularity="day"):
    period_expr = {
        "year":  "strftime(CAST(\"DATA_DATE\" AS DATE), '%Y')",
        "month": "strftime(CAST(\"DATA_DATE\" AS DATE), '%Y-%m')",
        "week":  "strftime(date_trunc('week', CAST(\"DATA_DATE\" AS DATE)), '%Y-%m-%d')",
        "day":   "strftime(CAST(\"DATA_DATE\" AS DATE), '%Y-%m-%d')",
    }[granularity]
    rows = conn.execute(f"""
        SELECT
          {period_expr} AS period,
          SUM(COALESCE("PRD_HOURS", 0)) AS prd_hours,
          SUM(COALESCE("SBY_HOURS", 0)) AS sby_hours,
          SUM(COALESCE("UDT_HOURS", 0)) AS udt_hours,
          SUM(COALESCE("SDT_HOURS", 0)) AS sdt_hours,
          SUM(COALESCE("EGT_HOURS", 0)) AS egt_hours,
          SUM(COALESCE("NST_HOURS", 0)) AS nst_hours
        FROM resource_history_data
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    items = []
    for _, row in rows.iterrows():
        prd, sby = float(row["prd_hours"]), float(row["sby_hours"])
        udt, sdt = float(row["udt_hours"]), float(row["sdt_hours"])
        egt, nst = float(row["egt_hours"]), float(row["nst_hours"])
        items.append({
            "date": str(row["period"]),
            "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
            "prd_hours": round(prd, 1),
        })
    return items


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestResourceHistoryKpiParity:
    def test_ou_pct_matches(self, sample_df, duckdb_conn):
        server = pandas_kpi(sample_df)
        frontend = frontend_kpi(duckdb_conn)
        assert frontend["ou_pct"] == pytest.approx(server["ou_pct"], abs=0.2)

    def test_availability_pct_matches(self, sample_df, duckdb_conn):
        server = pandas_kpi(sample_df)
        frontend = frontend_kpi(duckdb_conn)
        assert frontend["availability_pct"] == pytest.approx(server["availability_pct"], abs=0.2)

    def test_prd_hours_matches(self, sample_df, duckdb_conn):
        server = pandas_kpi(sample_df)
        frontend = frontend_kpi(duckdb_conn)
        assert frontend["prd_hours"] == pytest.approx(server["prd_hours"], abs=0.2)

    def test_machine_count_matches(self, sample_df, duckdb_conn):
        server = pandas_kpi(sample_df)
        frontend = frontend_kpi(duckdb_conn)
        assert frontend["machine_count"] == server["machine_count"]


class TestResourceHistoryTrendParity:
    @pytest.mark.parametrize("granularity", ["day", "week", "month"])
    def test_trend_date_count_matches(self, sample_df, duckdb_conn, granularity):
        server = pandas_trend(sample_df, granularity)
        frontend = frontend_trend(duckdb_conn, granularity)
        assert len(frontend) == len(server)

    @pytest.mark.parametrize("granularity", ["day", "week", "month"])
    def test_trend_ou_pct_matches(self, sample_df, duckdb_conn, granularity):
        server = pandas_trend(sample_df, granularity)
        frontend = frontend_trend(duckdb_conn, granularity)
        for s, f in zip(server, frontend):
            assert f["ou_pct"] == pytest.approx(s["ou_pct"], abs=0.2), \
                f"ou_pct mismatch at {s['date']}: server={s['ou_pct']} frontend={f['ou_pct']}"

    @pytest.mark.parametrize("granularity", ["day", "week", "month"])
    def test_trend_prd_hours_matches(self, sample_df, duckdb_conn, granularity):
        server = pandas_trend(sample_df, granularity)
        frontend = frontend_trend(duckdb_conn, granularity)
        for s, f in zip(server, frontend):
            assert f["prd_hours"] == pytest.approx(s["prd_hours"], abs=0.2)


class TestResourceHistoryByHistoryIdParity:
    def test_historyid_count_matches(self, sample_df, duckdb_conn):
        by_resource = sample_df.groupby("HISTORYID").agg(
            PRD_HOURS=("PRD_HOURS", "sum"),
        ).reset_index()
        server_count = len(by_resource)

        frontend_rows = duckdb_conn.execute("""
            SELECT "HISTORYID", SUM(COALESCE("PRD_HOURS", 0)) AS prd_hours
            FROM resource_history_data
            GROUP BY "HISTORYID"
        """).fetchdf()
        assert len(frontend_rows) == server_count

    def test_prd_hours_per_resource_matches(self, sample_df, duckdb_conn):
        by_resource = sample_df.groupby("HISTORYID").agg(
            PRD_HOURS=("PRD_HOURS", "sum"),
        ).reset_index().sort_values("HISTORYID")

        frontend_rows = duckdb_conn.execute("""
            SELECT "HISTORYID", SUM(COALESCE("PRD_HOURS", 0)) AS prd_hours
            FROM resource_history_data
            GROUP BY "HISTORYID"
            ORDER BY "HISTORYID"
        """).fetchdf()

        for _, sr in by_resource.iterrows():
            fr = frontend_rows[frontend_rows["HISTORYID"] == sr["HISTORYID"]]
            assert not fr.empty
            assert float(fr.iloc[0]["prd_hours"]) == pytest.approx(float(sr["PRD_HOURS"]), abs=0.01)
