# -*- coding: utf-8 -*-
"""Parity tests: hold-history DuckDB SQL runtime vs Pandas derivation.

Covers tasks 4.7 and 9.2 — verifies that the DuckDB out-of-core view
computation produces identical results to the Pandas-based derivation for
all sub-views (reason_pareto / duration / list).

Note: The DuckDB SQL runtime references lowercase ``hold_day`` / ``release_day``
(matching Oracle SQL aliases), while the Pandas path references uppercase
``HOLD_DAY`` / ``RELEASE_DAY`` (from ``read_sql_df`` column uppercasing).
The test builds separate DataFrames with appropriate column naming for each
path, using identical underlying data, to isolate derivation logic parity
from the column-naming difference.
"""
from __future__ import annotations

import math
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import pandas as pd
import pytest

# ── Sample data ──────────────────────────────────────────────────────────────

_REASONS = ["QUALITY_CHECK", "YIELD_FAIL", "CONTAMINATION", "VISUAL_DEFECT"]
_START_DATE = "2026-01-01"
_END_DATE = "2026-01-07"

# Columns that the DuckDB SQL runtime references in lowercase
_LOWERCASE_COLS = {"hold_day", "release_day"}


def _build_sample_rows(n_holds: int = 30) -> List[Dict[str, Any]]:
    """Build sample hold-history rows (raw dict list)."""
    import random
    random.seed(99)

    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)

    for i in range(n_holds):
        hold_dt = base + timedelta(days=i % 7, hours=random.randint(0, 23))
        hold_day = hold_dt.strftime("%Y-%m-%d")
        hold_type = "quality" if i % 3 != 0 else "non-quality"
        reason = _REASONS[i % len(_REASONS)]
        qty = random.randint(10, 200)

        if random.random() < 0.6:
            release_dt = hold_dt + timedelta(hours=random.uniform(0.5, 120))
            release_day = release_dt.strftime("%Y-%m-%d")
            hold_hours = round((release_dt - hold_dt).total_seconds() / 3600, 2)
        else:
            release_dt = None
            release_day = None
            hold_hours = None

        rows.append({
            "CONTAINERID": f"CONT{i:04d}",
            "LOT_ID": f"LOT{i:04d}",
            "PJ_WORKORDER": f"WO{i % 5:03d}",
            "PRODUCTNAME": f"PROD_{i % 3}",
            "WORKCENTERNAME": f"WC_{i % 2}",
            "HOLDREASONNAME": reason,
            "QTY": qty,
            "HOLDTXNDATE": hold_dt,
            "HOLDEMP": f"EMP{i % 3:02d}",
            "HOLDCOMMENTS": f"Hold comment {i}",
            "RELEASETXNDATE": release_dt,
            "RELEASEEMP": f"REL{i % 2:02d}" if release_dt else None,
            "RELEASECOMMENTS": f"Released {i}" if release_dt else None,
            "HOLD_HOURS": hold_hours,
            "NCRID": f"NCR{i:05d}" if i % 4 == 0 else None,
            "FUTUREHOLDCOMMENTS": None,
            "HOLD_TYPE": hold_type,
            "hold_day": hold_day,
            "release_day": release_day,
            "RN_HOLD_DAY": 1 if i % 2 == 0 else 2,
            "IS_FUTURE_HOLD": 0,
            "FUTURE_HOLD_FLAG": 0,
        })

    return rows


def _build_duckdb_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build DataFrame with lowercase hold_day/release_day (DuckDB SQL runtime expects this)."""
    return pd.DataFrame(rows)


def _build_pandas_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build DataFrame with uppercase columns (as read_sql_df would produce).

    Oracle DATE columns are returned as Timestamps by cx_Oracle/oracledb,
    then read_sql_df uppercases column names. We replicate that here.
    """
    df = pd.DataFrame(rows)
    df.columns = [str(c).upper() for c in df.columns]
    # Convert date columns to Timestamps (matching Oracle driver behavior)
    df["HOLD_DAY"] = pd.to_datetime(df["HOLD_DAY"])
    df["RELEASE_DAY"] = pd.to_datetime(df["RELEASE_DAY"])
    # Add query date range so _apply_record_type_filter matches DuckDB behavior
    df["_QUERY_START"] = pd.Timestamp(_START_DATE)
    df["_QUERY_END"] = pd.Timestamp(_END_DATE)
    return df


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_parquet(df: pd.DataFrame, tmp_dir: str, name: str = "test_hold.parquet") -> str:
    path = str(Path(tmp_dir) / name)
    df.to_parquet(path, index=False, engine="pyarrow")
    return path


def _run_duckdb_view(parquet_path: str, **kwargs) -> Dict[str, Any]:
    """Run DuckDB SQL runtime directly against Parquet."""
    import duckdb
    from mes_dashboard.services.hold_history_sql_runtime import (
        _attach_spool_view,
        _query_reason_pareto,
        _query_duration,
        _query_list,
    )

    hold_type = kwargs.get("hold_type", "quality")
    reason = kwargs.get("reason", None)
    record_type = kwargs.get("record_type", "new")
    duration_range = kwargs.get("duration_range", None)
    page = kwargs.get("page", 1)
    per_page = kwargs.get("per_page", 50)
    start_date = kwargs.get("start_date", _START_DATE)
    end_date = kwargs.get("end_date", _END_DATE)

    conn = duckdb.connect(database=":memory:")
    try:
        _attach_spool_view(conn, parquet_path)

        reason_pareto = _query_reason_pareto(
            conn, hold_type=hold_type, record_type=record_type,
            start_date=start_date, end_date=end_date,
        )
        duration = _query_duration(
            conn, hold_type=hold_type, record_type=record_type,
            start_date=start_date, end_date=end_date,
        )
        list_result = _query_list(
            conn, hold_type=hold_type, reason=reason,
            record_type=record_type, duration_range=duration_range,
            page=page, per_page=per_page,
            start_date=start_date, end_date=end_date,
        )

        return {
            "reason_pareto": reason_pareto,
            "duration": duration,
            "list": list_result,
        }
    finally:
        conn.close()


def _run_pandas_view(df: pd.DataFrame, **kwargs) -> Dict[str, Any]:
    """Run Pandas-based derivation."""
    from mes_dashboard.services.hold_dataset_cache import _derive_all_views

    return _derive_all_views(
        df,
        hold_type=kwargs.get("hold_type", "quality"),
        reason=kwargs.get("reason", None),
        record_type=kwargs.get("record_type", "new"),
        duration_range=kwargs.get("duration_range", None),
        page=kwargs.get("page", 1),
        per_page=kwargs.get("per_page", 50),
    )


# ── Parity assertions ───────────────────────────────────────────────────────

def _assert_float_close(a, b, label: str, tol: float = 0.05):
    assert abs(float(a) - float(b)) <= tol, (
        f"{label}: DuckDB={a} vs Pandas={b} (diff={abs(float(a)-float(b)):.4f})"
    )


# ── Test class ───────────────────────────────────────────────────────────────

class TestHoldHistorySqlParity:
    """DuckDB SQL runtime must produce same results as Pandas derivation."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.raw_rows = _build_sample_rows(30)
        # DuckDB path: lowercase hold_day/release_day
        duck_df = _build_duckdb_df(self.raw_rows)
        self.parquet_path = _write_parquet(duck_df, str(tmp_path))
        # Pandas path: uppercase columns (as read_sql_df would produce)
        self.pandas_df = _build_pandas_df(self.raw_rows)

    def test_reason_pareto_parity_quality(self):
        duck = _run_duckdb_view(self.parquet_path, hold_type="quality")
        pandas_result = _run_pandas_view(self.pandas_df, hold_type="quality")

        dr = duck["reason_pareto"]["items"]
        pr = pandas_result["reason_pareto"]["items"]

        assert len(dr) == len(pr), (
            f"reason_pareto length: DuckDB={len(dr)} vs Pandas={len(pr)}"
        )

        d_map = {r["reason"]: r for r in dr}
        p_map = {r["reason"]: r for r in pr}

        assert set(d_map.keys()) == set(p_map.keys()), "reason names differ"

        for reason in d_map:
            assert d_map[reason]["qty"] == p_map[reason]["qty"], (
                f"reason_pareto[{reason}].qty: {d_map[reason]['qty']} vs {p_map[reason]['qty']}"
            )
            _assert_float_close(
                d_map[reason]["pct"], p_map[reason]["pct"],
                f"reason_pareto[{reason}].pct"
            )

    def test_reason_pareto_parity_all(self):
        duck = _run_duckdb_view(self.parquet_path, hold_type="all")
        pandas_result = _run_pandas_view(self.pandas_df, hold_type="all")

        dr = duck["reason_pareto"]["items"]
        pr = pandas_result["reason_pareto"]["items"]

        assert len(dr) == len(pr), (
            f"reason_pareto(all) length: DuckDB={len(dr)} vs Pandas={len(pr)}"
        )

    def test_duration_parity(self):
        duck = _run_duckdb_view(self.parquet_path, hold_type="quality")
        pandas_result = _run_pandas_view(self.pandas_df, hold_type="quality")

        dd = duck["duration"]["items"]
        pd_items = pandas_result["duration"]["items"]

        assert len(dd) == len(pd_items), (
            f"duration length: DuckDB={len(dd)} vs Pandas={len(pd_items)}"
        )

        d_map = {d["range"]: d for d in dd}
        p_map = {d["range"]: d for d in pd_items}

        for bucket in ["<4h", "4-24h", "1-3d", ">3d"]:
            assert d_map[bucket]["count"] == p_map[bucket]["count"], (
                f"duration[{bucket}].count: {d_map[bucket]['count']} vs {p_map[bucket]['count']}"
            )
            assert d_map[bucket]["qty"] == p_map[bucket]["qty"], (
                f"duration[{bucket}].qty: {d_map[bucket]['qty']} vs {p_map[bucket]['qty']}"
            )
            _assert_float_close(
                d_map[bucket]["pct"], p_map[bucket]["pct"],
                f"duration[{bucket}].pct"
            )

    def test_list_pagination_parity(self):
        duck = _run_duckdb_view(
            self.parquet_path, hold_type="quality", page=1, per_page=10,
        )
        pandas_result = _run_pandas_view(
            self.pandas_df, hold_type="quality", page=1, per_page=10,
        )

        dl = duck["list"]
        pl = pandas_result["list"]

        assert dl["pagination"]["total"] == pl["pagination"]["total"], (
            f"list total: DuckDB={dl['pagination']['total']} vs Pandas={pl['pagination']['total']}"
        )
        assert dl["pagination"]["totalPages"] == pl["pagination"]["totalPages"], (
            f"list totalPages differ"
        )
        assert len(dl["items"]) == len(pl["items"]), (
            f"list items length: DuckDB={len(dl['items'])} vs Pandas={len(pl['items'])}"
        )

    def test_list_reason_filter_parity(self):
        reason = "QUALITY_CHECK"
        duck = _run_duckdb_view(
            self.parquet_path, hold_type="quality", reason=reason,
        )
        pandas_result = _run_pandas_view(
            self.pandas_df, hold_type="quality", reason=reason,
        )

        dl = duck["list"]
        pl = pandas_result["list"]

        assert dl["pagination"]["total"] == pl["pagination"]["total"], (
            f"list(reason={reason}) total: DuckDB={dl['pagination']['total']} vs Pandas={pl['pagination']['total']}"
        )

    def test_non_quality_filter_parity(self):
        duck = _run_duckdb_view(self.parquet_path, hold_type="non-quality")
        pandas_result = _run_pandas_view(self.pandas_df, hold_type="non-quality")

        dr = duck["reason_pareto"]["items"]
        pr = pandas_result["reason_pareto"]["items"]

        d_total = sum(r["qty"] for r in dr)
        p_total = sum(r["qty"] for r in pr)

        assert d_total == p_total, (
            f"non-quality total qty: DuckDB={d_total} vs Pandas={p_total}"
        )

    def test_empty_df_parity(self):
        duck_cols = [
            "CONTAINERID", "LOT_ID", "PJ_WORKORDER", "PRODUCTNAME",
            "WORKCENTERNAME", "HOLDREASONNAME", "QTY", "HOLDTXNDATE",
            "HOLDEMP", "HOLDCOMMENTS", "RELEASETXNDATE", "RELEASEEMP",
            "RELEASECOMMENTS", "HOLD_HOURS", "NCRID", "FUTUREHOLDCOMMENTS",
            "HOLD_TYPE", "hold_day", "release_day", "RN_HOLD_DAY",
            "IS_FUTURE_HOLD", "FUTURE_HOLD_FLAG",
        ]
        pandas_cols = [c.upper() for c in duck_cols]

        with tempfile.TemporaryDirectory() as tmp:
            duck_df = pd.DataFrame(columns=duck_cols)
            path = _write_parquet(duck_df, tmp)
            duck = _run_duckdb_view(path)

            pandas_df = pd.DataFrame(columns=pandas_cols)
            pandas_result = _run_pandas_view(pandas_df)

            assert len(duck["reason_pareto"]["items"]) == 0
            assert len(pandas_result["reason_pareto"]["items"]) == 0
            assert duck["list"]["pagination"]["total"] == 0
            assert pandas_result["list"]["pagination"]["total"] == 0
