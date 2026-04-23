# -*- coding: utf-8 -*-
"""DuckDB SQL runtime correctness tests for hold-history.

Originally a pandas parity test (tasks 4.7 and 9.2). The Pandas derivation
path was retired in Phase 3; this file now verifies DuckDB SQL runtime
produces structurally correct, sane output against known sample data.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest


# ── Sample data ──────────────────────────────────────────────────────────────

_REASONS = ["QUALITY_CHECK", "YIELD_FAIL", "CONTAMINATION", "VISUAL_DEFECT"]
_START_DATE = "2026-01-01"
_END_DATE = "2026-01-07"


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
            "RN_FUTURE_REASON": (i // len(_REASONS)) + 1,  # repeats every len(_REASONS) lots
            "IS_FUTURE_HOLD": 0,
            "FUTURE_HOLD_FLAG": 0,
        })

    return rows


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


# ── Standalone helper tests ──────────────────────────────────────────────────

def test_resolve_view_date_range_uses_valid_input_dates(monkeypatch):
    from mes_dashboard.services import hold_history_sql_runtime as runtime

    def _should_not_be_called(*_args, **_kwargs):
        raise AssertionError("fallback SQL query should not run when inputs are valid")

    monkeypatch.setattr(runtime, "_fetch_dict_rows", _should_not_be_called)

    start, end = runtime._resolve_view_date_range(
        conn=object(),
        start_date="2026-03-01",
        end_date="2026-03-05",
    )
    assert start == "2026-03-01"
    assert end == "2026-03-05"


def test_resolve_view_date_range_falls_back_to_spool_bounds(monkeypatch):
    from mes_dashboard.services import hold_history_sql_runtime as runtime

    monkeypatch.setattr(
        runtime,
        "_fetch_dict_rows",
        lambda conn, sql, params=None: [{"min_day": "2026-03-02", "max_day": "2026-03-09"}],
    )

    start, end = runtime._resolve_view_date_range(
        conn=object(),
        start_date="",
        end_date=None,
    )
    assert start == "2026-03-02"
    assert end == "2026-03-09"


# ── DuckDB correctness tests ─────────────────────────────────────────────────

class TestHoldHistorySqlParity:
    """DuckDB SQL runtime produces structurally correct, sane output."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.raw_rows = _build_sample_rows(30)
        duck_df = pd.DataFrame(self.raw_rows)
        self.parquet_path = _write_parquet(duck_df, str(tmp_path))

    def test_reason_pareto_quality(self):
        result = _run_duckdb_view(self.parquet_path, hold_type="quality")
        items = result["reason_pareto"]["items"]
        assert len(items) > 0
        for item in items:
            assert "reason" in item
            assert item["qty"] >= 0
            assert 0.0 <= item["pct"] <= 100.0

    def test_reason_pareto_all(self):
        result = _run_duckdb_view(self.parquet_path, hold_type="all")
        items = result["reason_pareto"]["items"]
        assert len(items) > 0
        total_pct = sum(item["pct"] for item in items)
        assert abs(total_pct - 100.0) < 1.0

    def test_duration_buckets_present(self):
        result = _run_duckdb_view(self.parquet_path, hold_type="quality")
        items = result["duration"]["items"]
        bucket_labels = {item["range"] for item in items}
        assert "<4h" in bucket_labels
        assert "4-24h" in bucket_labels
        assert "1-3d" in bucket_labels
        assert ">3d" in bucket_labels

    def test_list_pagination_structure(self):
        result = _run_duckdb_view(
            self.parquet_path, hold_type="quality", page=1, per_page=10,
        )
        lst = result["list"]
        assert "pagination" in lst
        assert "items" in lst
        pg = lst["pagination"]
        assert pg["total"] >= 0
        assert pg["totalPages"] >= 1
        assert len(lst["items"]) <= 10

    def test_list_reason_filter(self):
        reason = "QUALITY_CHECK"
        result = _run_duckdb_view(
            self.parquet_path, hold_type="quality", reason=reason,
        )
        lst = result["list"]
        assert lst["pagination"]["total"] >= 0

    def test_non_quality_filter(self):
        result = _run_duckdb_view(self.parquet_path, hold_type="non-quality")
        items = result["reason_pareto"]["items"]
        total_qty = sum(r["qty"] for r in items)
        assert total_qty >= 0

    def test_empty_df(self):
        duck_cols = [
            "CONTAINERID", "LOT_ID", "PJ_WORKORDER", "PRODUCTNAME",
            "WORKCENTERNAME", "HOLDREASONNAME", "QTY", "HOLDTXNDATE",
            "HOLDEMP", "HOLDCOMMENTS", "RELEASETXNDATE", "RELEASEEMP",
            "RELEASECOMMENTS", "HOLD_HOURS", "NCRID", "FUTUREHOLDCOMMENTS",
            "HOLD_TYPE", "hold_day", "release_day", "RN_HOLD_DAY",
            "RN_FUTURE_REASON", "IS_FUTURE_HOLD", "FUTURE_HOLD_FLAG",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            duck_df = pd.DataFrame(columns=duck_cols)
            path = _write_parquet(duck_df, tmp)
            result = _run_duckdb_view(path)
            assert len(result["reason_pareto"]["items"]) == 0
            assert result["list"]["pagination"]["total"] == 0


class TestDurationAvgMaxParity:
    """DuckDB _query_duration() AVG/MAX fields are structurally correct."""

    @classmethod
    def setup_class(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        rows = _build_sample_rows(30)
        df = pd.DataFrame(rows)
        cls.parquet_path = _write_parquet(df, cls.tmp.name)

    @classmethod
    def teardown_class(cls):
        cls.tmp.cleanup()

    def _run_duration(self, **kwargs):
        import duckdb
        from mes_dashboard.services.hold_history_sql_runtime import _attach_spool_view, _query_duration
        conn = duckdb.connect(database=":memory:")
        try:
            _attach_spool_view(conn, self.parquet_path)
            return _query_duration(conn, **kwargs)
        finally:
            conn.close()

    def test_avg_released_hours_non_negative(self):
        result = self._run_duration(hold_type="quality", record_type="new",
                                    start_date=_START_DATE, end_date=_END_DATE)
        assert result["avgReleasedHours"] >= 0
        assert result["maxReleasedHours"] >= 0
        assert result["avgOnHoldHours"] >= 0
        assert result["maxOnHoldHours"] >= 0

    def test_avg_leq_max(self):
        result = self._run_duration(hold_type="quality", record_type="new",
                                    start_date=_START_DATE, end_date=_END_DATE)
        if result["maxReleasedHours"] > 0:
            assert result["avgReleasedHours"] <= result["maxReleasedHours"]
        if result["maxOnHoldHours"] > 0:
            assert result["avgOnHoldHours"] <= result["maxOnHoldHours"]

    def test_empty_spool_returns_zero_avg_max(self):
        import tempfile, duckdb
        from mes_dashboard.services.hold_history_sql_runtime import _attach_spool_view, _query_duration
        duck_cols = [
            "CONTAINERID", "LOT_ID", "PJ_WORKORDER", "PRODUCTNAME",
            "WORKCENTERNAME", "HOLDREASONNAME", "QTY", "HOLDTXNDATE",
            "HOLDEMP", "HOLDCOMMENTS", "RELEASETXNDATE", "RELEASEEMP",
            "RELEASECOMMENTS", "HOLD_HOURS", "NCRID", "FUTUREHOLDCOMMENTS",
            "HOLD_TYPE", "hold_day", "release_day", "RN_HOLD_DAY",
            "RN_FUTURE_REASON", "IS_FUTURE_HOLD", "FUTURE_HOLD_FLAG",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            duck_df = pd.DataFrame(columns=duck_cols)
            path = _write_parquet(duck_df, tmp)
            conn = duckdb.connect(database=":memory:")
            try:
                _attach_spool_view(conn, path)
                result = _query_duration(conn, hold_type="quality", record_type="new",
                                         start_date=_START_DATE, end_date=_END_DATE)
            finally:
                conn.close()
        assert result["avgReleasedHours"] == 0.0
        assert result["maxReleasedHours"] == 0.0
        assert result["avgOnHoldHours"] == 0.0
        assert result["maxOnHoldHours"] == 0.0


class TestRepeatQualityHoldQtyParity:
    """DuckDB _query_trend() repeatQualityHoldQty is consistent and non-negative."""

    @classmethod
    def setup_class(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        rows = _build_sample_rows(30)
        df = pd.DataFrame(rows)
        cls.parquet_path = _write_parquet(df, cls.tmp.name)

    @classmethod
    def teardown_class(cls):
        cls.tmp.cleanup()

    def _run_trend(self):
        import duckdb
        from mes_dashboard.services.hold_history_sql_runtime import _attach_spool_view, _query_trend
        conn = duckdb.connect(database=":memory:")
        try:
            _attach_spool_view(conn, self.parquet_path)
            return _query_trend(conn, start_date=_START_DATE, end_date=_END_DATE)
        finally:
            conn.close()

    def test_each_day_has_repeat_quality_field(self):
        result = self._run_trend()
        for day in result["days"]:
            assert "repeatQualityHoldQty" in day["quality"]
            assert "repeatQualityHoldQty" in day["non_quality"]
            assert "repeatQualityHoldQty" in day["all"]

    def test_repeat_quality_non_negative(self):
        result = self._run_trend()
        for day in result["days"]:
            assert day["quality"]["repeatQualityHoldQty"] >= 0
            assert day["non_quality"]["repeatQualityHoldQty"] == 0  # non-quality can't be quality
            assert day["all"]["repeatQualityHoldQty"] >= 0

    def test_repeat_quality_all_equals_quality_sum(self):
        result = self._run_trend()
        for day in result["days"]:
            assert day["all"]["repeatQualityHoldQty"] == day["quality"]["repeatQualityHoldQty"]
