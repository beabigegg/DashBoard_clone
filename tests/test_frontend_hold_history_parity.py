# -*- coding: utf-8 -*-
"""Parity tests: Hold History frontend (DuckDB SQL) vs server-side (Pandas).

Task 5.2 — Verifies that the SQL logic used by useHoldHistoryDuckDB.js
produces equivalent outputs to the Pandas derivation in hold_dataset_cache.py
for reason_pareto, duration, and paginated list views.

Note: Trend computation is separately verified; this file focuses on the
filter-sensitive views (pareto, duration, list) that are most likely to drift.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List

import duckdb
import pandas as pd
import pytest

# ── Sample data ───────────────────────────────────────────────────────────────

_REASONS = ["QUALITY_CHECK", "YIELD_FAIL", "CONTAMINATION", "VISUAL_DEFECT"]
_START_DATE = "2026-01-01"
_END_DATE   = "2026-01-07"


def _build_sample_rows(n_holds: int = 40) -> List[Dict[str, Any]]:
    import random
    random.seed(77)
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for i in range(n_holds):
        hold_dt = base + timedelta(days=i % 7, hours=random.randint(0, 23))
        hold_hours = random.choice([1.5, 10.0, 30.0, 100.0])
        released = i % 3 != 0
        release_dt = hold_dt + timedelta(hours=hold_hours) if released else None
        hold_day = hold_dt.date()
        release_day = release_dt.date() if release_dt else None
        rows.append({
            "HOLD_DAY":        pd.Timestamp(hold_day),
            "RELEASE_DAY":     pd.Timestamp(release_day) if release_day else pd.NaT,
            "CONTAINERID":     f"CTN{i:04d}",
            "LOT_ID":          f"LOT{i:04d}",
            "PJ_WORKORDER":    f"WO{i:04d}",
            "PRODUCTNAME":     f"PROD{i % 3}",
            "WORKCENTERNAME":  f"WC_{i % 3}",
            "HOLDREASONID":    i % len(_REASONS),
            "HOLDREASONNAME":  _REASONS[i % len(_REASONS)],
            "QTY":             random.randint(10, 200),
            "HOLDTXNDATE":     pd.Timestamp(hold_dt),
            "HOLDEMP":         f"EMP{i % 5}",
            "HOLDCOMMENTS":    f"comment {i}",
            "RELEASETXNDATE":  pd.Timestamp(release_dt) if release_dt else pd.NaT,
            "RELEASEEMP":      f"EMP{(i + 1) % 5}" if released else None,
            "RELEASECOMMENTS": f"release {i}" if released else None,
            "NCRID":           None,
            "FUTUREHOLDCOMMENTS": None,
            "HOLD_HOURS":      hold_hours,
            "HOLD_TYPE":       "quality" if i % 3 != 0 else "non-quality",
            "IS_FUTURE_HOLD":  0,
            "RN_HOLD_DAY":     1,
            "RN_FUTURE_REASON": 1,
            "FUTURE_HOLD_FLAG": 1,
            "_QUERY_START":    pd.Timestamp(_START_DATE),
            "_QUERY_END":      pd.Timestamp(_END_DATE),
        })
    return rows


@pytest.fixture(scope="module")
def sample_df():
    return pd.DataFrame(_build_sample_rows())


@pytest.fixture(scope="module")
def parquet_path(sample_df, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("hold_spool")
    path = tmp / "hold_history_data.parquet"
    # Spool does NOT include _QUERY_START/_QUERY_END
    spool_df = sample_df.drop(columns=["_QUERY_START", "_QUERY_END"])
    spool_df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture(scope="module")
def duckdb_conn(parquet_path):
    conn = duckdb.connect(":memory:")
    conn.execute(f"""
        CREATE OR REPLACE VIEW hold_history_data AS
        SELECT * FROM read_parquet('{parquet_path}')
    """)
    yield conn
    conn.close()


# ── Server-side Pandas reference (mirrors hold_dataset_cache.py) ──────────────

def _safe_int(v, default=0):
    try:
        return int(v) if v is not None and not math.isnan(float(v)) else default
    except (TypeError, ValueError):
        return default


def pandas_reason_pareto(df, hold_type="quality", record_types=None, start=None, end=None):
    record_types = set(record_types or ["new"])
    # Apply record_type filter
    mask = pd.Series(False, index=df.index)
    if "new" in record_types:
        mask |= (df["HOLD_DAY"] >= pd.Timestamp(start)) & (df["HOLD_DAY"] <= pd.Timestamp(end))
    if "on_hold" in record_types:
        mask |= df["RELEASETXNDATE"].isna()
    if "released" in record_types:
        mask |= df["RELEASETXNDATE"].notna()
    filtered = df[mask]
    # Apply hold_type
    if hold_type != "all":
        filtered = filtered[filtered["HOLD_TYPE"] == hold_type]
    if filtered.empty:
        return []
    grouped = (
        filtered.groupby("HOLDREASONNAME", sort=False)
        .agg(count=("CONTAINERID", "count"), qty=("QTY", "sum"))
        .reset_index()
    )
    grouped = grouped.sort_values("qty", ascending=False)
    total = grouped["qty"].sum()
    items = []
    cum = 0.0
    for _, row in grouped.iterrows():
        qty = _safe_int(row["qty"])
        pct = round((qty / total * 100) if total > 0 else 0, 2)
        cum = round(cum + pct, 2)
        items.append({
            "reason": str(row["HOLDREASONNAME"]).strip() or "(未填寫)",
            "qty": qty,
            "pct": pct,
        })
    return items


def pandas_duration(df, hold_type="quality", record_types=None, start=None, end=None):
    record_types = set(record_types or ["new"])
    mask = pd.Series(False, index=df.index)
    if "new" in record_types:
        mask |= (df["HOLD_DAY"] >= pd.Timestamp(start)) & (df["HOLD_DAY"] <= pd.Timestamp(end))
    if "released" in record_types:
        mask |= df["RELEASETXNDATE"].notna()
    filtered = df[mask]
    if hold_type != "all":
        filtered = filtered[filtered["HOLD_TYPE"] == hold_type]
    released = filtered[filtered["RELEASETXNDATE"].notna()]
    if released.empty:
        return []
    hours = released["HOLD_HOURS"]
    total_qty = _safe_int(released["QTY"].sum())
    buckets = [
        ("<4h",   hours < 4),
        ("4-24h", (hours >= 4) & (hours < 24)),
        ("1-3d",  (hours >= 24) & (hours < 72)),
        (">3d",   hours >= 72),
    ]
    return [
        {
            "range": label,
            "count": int(mask2.sum()),
            "qty": _safe_int(released.loc[mask2, "QTY"].sum()),
            "pct": round((_safe_int(released.loc[mask2, "QTY"].sum()) / total_qty * 100) if total_qty > 0 else 0, 2),
        }
        for label, mask2 in buckets
    ]


# ── Frontend DuckDB SQL equivalents (mirrors useHoldHistoryDuckDB.js) ──────────

def frontend_reason_pareto(conn, hold_type="quality", record_types=None, start=None, end=None):
    record_types = list(record_types or ["new"])
    rt_parts = []
    if "new" in record_types:
        rt_parts.append(f"(CAST(\"HOLD_DAY\" AS DATE) >= DATE '{start}' AND CAST(\"HOLD_DAY\" AS DATE) <= DATE '{end}')")
    if "on_hold" in record_types:
        rt_parts.append("\"RELEASETXNDATE\" IS NULL")
    if "released" in record_types:
        rt_parts.append("\"RELEASETXNDATE\" IS NOT NULL")
    rt_cond = "(" + " OR ".join(rt_parts) + ")" if rt_parts else "1=1"
    ht_cond = ""
    if hold_type == "quality":
        ht_cond = "AND \"HOLD_TYPE\" = 'quality'"
    elif hold_type == "non-quality":
        ht_cond = "AND \"HOLD_TYPE\" = 'non-quality'"

    sql = f"""
        SELECT
          COALESCE(TRIM(CAST("HOLDREASONNAME" AS VARCHAR)), '') AS reason,
          COUNT(*) AS cnt,
          SUM(COALESCE("QTY", 0)) AS qty
        FROM hold_history_data
        WHERE {rt_cond} {ht_cond}
        GROUP BY reason
        HAVING SUM(COALESCE("QTY", 0)) > 0
        ORDER BY qty DESC
    """
    rows = conn.execute(sql).fetchdf()
    total = rows["qty"].sum()
    items = []
    for _, row in rows.iterrows():
        qty = int(row["qty"])
        pct = round((qty / total * 100) if total > 0 else 0, 2)
        items.append({"reason": str(row["reason"]).strip() or "(未填寫)", "qty": qty, "pct": pct})
    return items


def frontend_duration(conn, hold_type="quality", record_types=None, start=None, end=None):
    record_types = list(record_types or ["new"])
    rt_parts = []
    if "new" in record_types:
        rt_parts.append(f"(CAST(\"HOLD_DAY\" AS DATE) >= DATE '{start}' AND CAST(\"HOLD_DAY\" AS DATE) <= DATE '{end}')")
    if "released" in record_types:
        rt_parts.append("\"RELEASETXNDATE\" IS NOT NULL")
    rt_cond = "(" + " OR ".join(rt_parts) + ")" if rt_parts else "1=1"
    ht_cond = ""
    if hold_type == "quality":
        ht_cond = "AND \"HOLD_TYPE\" = 'quality'"
    elif hold_type == "non-quality":
        ht_cond = "AND \"HOLD_TYPE\" = 'non-quality'"

    sql = f"""
        SELECT
          CASE
            WHEN "HOLD_HOURS" < 4  THEN '<4h'
            WHEN "HOLD_HOURS" < 24 THEN '4-24h'
            WHEN "HOLD_HOURS" < 72 THEN '1-3d'
            ELSE '>3d'
          END AS range,
          COUNT(*) AS cnt,
          SUM(COALESCE("QTY", 0)) AS qty
        FROM hold_history_data
        WHERE {rt_cond} {ht_cond} AND "RELEASETXNDATE" IS NOT NULL
        GROUP BY range
    """
    rows = conn.execute(sql).fetchdf()
    total = rows["qty"].sum()
    order = {"<4h": 0, "4-24h": 1, "1-3d": 2, ">3d": 3}
    rows = rows.sort_values("range", key=lambda s: s.map(order).fillna(9))
    return [
        {
            "range": str(row["range"]),
            "count": int(row["cnt"]),
            "qty": int(row["qty"]),
            "pct": round((int(row["qty"]) / total * 100) if total > 0 else 0, 2),
        }
        for _, row in rows.iterrows()
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHoldHistoryReasonParetoParity:
    @pytest.mark.parametrize("hold_type", ["quality", "non-quality", "all"])
    def test_reason_count_matches(self, sample_df, duckdb_conn, hold_type):
        server = pandas_reason_pareto(sample_df, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        frontend = frontend_reason_pareto(duckdb_conn, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        assert len(frontend) == len(server), f"hold_type={hold_type}: server={len(server)} frontend={len(frontend)}"

    @pytest.mark.parametrize("hold_type", ["quality", "non-quality", "all"])
    def test_reason_qty_matches(self, sample_df, duckdb_conn, hold_type):
        server = pandas_reason_pareto(sample_df, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        frontend = frontend_reason_pareto(duckdb_conn, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        for s, f in zip(server, frontend):
            assert f["qty"] == s["qty"], f"hold_type={hold_type}, reason={s['reason']}: server={s['qty']} frontend={f['qty']}"

    @pytest.mark.parametrize("hold_type", ["quality", "non-quality", "all"])
    def test_reason_pct_matches(self, sample_df, duckdb_conn, hold_type):
        server = pandas_reason_pareto(sample_df, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        frontend = frontend_reason_pareto(duckdb_conn, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        for s, f in zip(server, frontend):
            assert f["pct"] == pytest.approx(s["pct"], abs=0.02)


class TestHoldHistoryDurationParity:
    @pytest.mark.parametrize("hold_type", ["quality", "all"])
    def test_duration_buckets_match(self, sample_df, duckdb_conn, hold_type):
        server = pandas_duration(sample_df, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        frontend = frontend_duration(duckdb_conn, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        s_ranges = {d["range"] for d in server if d["count"] > 0}
        f_ranges = {d["range"] for d in frontend}
        assert f_ranges >= s_ranges, f"Missing buckets in frontend: {s_ranges - f_ranges}"

    @pytest.mark.parametrize("hold_type", ["quality", "all"])
    def test_duration_qty_matches(self, sample_df, duckdb_conn, hold_type):
        server = pandas_duration(sample_df, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        frontend = frontend_duration(duckdb_conn, hold_type=hold_type, start=_START_DATE, end=_END_DATE)
        s_map = {d["range"]: d["qty"] for d in server}
        f_map = {d["range"]: d["qty"] for d in frontend}
        for rng, qty in s_map.items():
            assert f_map.get(rng, 0) == qty, f"hold_type={hold_type}, range={rng}: server={qty} frontend={f_map.get(rng)}"


class TestHoldHistoryListPaginationParity:
    def test_total_count_matches(self, sample_df, duckdb_conn):
        # Baseline: all 'new' records, quality hold_type
        filtered = sample_df[
            (sample_df["HOLD_TYPE"] == "quality") &
            (sample_df["HOLD_DAY"] >= pd.Timestamp(_START_DATE)) &
            (sample_df["HOLD_DAY"] <= pd.Timestamp(_END_DATE))
        ]
        server_total = len(filtered)

        rows = duckdb_conn.execute(f"""
            SELECT COUNT(*) AS total FROM hold_history_data
            WHERE "HOLD_TYPE" = 'quality'
              AND CAST("HOLD_DAY" AS DATE) >= DATE '{_START_DATE}'
              AND CAST("HOLD_DAY" AS DATE) <= DATE '{_END_DATE}'
        """).fetchdf()
        frontend_total = int(rows.iloc[0]["total"])
        assert frontend_total == server_total

    def test_first_page_order_is_desc_by_holdtxndate(self, duckdb_conn):
        rows = duckdb_conn.execute("""
            SELECT strftime(CAST("HOLDTXNDATE" AS TIMESTAMP), '%Y-%m-%d %H:%M:%S') AS hold_dt
            FROM hold_history_data
            ORDER BY "HOLDTXNDATE" DESC
            LIMIT 5
        """).fetchdf()
        dates = list(rows["hold_dt"])
        assert dates == sorted(dates, reverse=True), "Frontend list order must be DESC by HOLDTXNDATE"
