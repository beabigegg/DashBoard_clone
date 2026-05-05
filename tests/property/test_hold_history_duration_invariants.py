# -*- coding: utf-8 -*-
"""Property-based tests for hold-history duration metrics invariants.

Invariants verified:
  - avgReleasedHours >= 0
  - avgOnHoldHours >= 0
  - maxReleasedHours >= 0
  - maxOnHoldHours >= 0
  - avgReleasedHours <= maxReleasedHours (when maxReleasedHours > 0)
  - avgOnHoldHours <= maxOnHoldHours (when maxOnHoldHours > 0)
  - repeatQualityHoldQty >= 0 for all trend days
"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import duckdb
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ── Hypothesis settings ───────────────────────────────────────────────────────

settings.load_profile("ci")


# ── Data generation ───────────────────────────────────────────────────────────

_QUALITY_REASONS = ["QUALITY_CHECK", "YIELD_FAIL"]
_NON_QUALITY_REASONS = ["MATERIAL", "EQUIPMENT"]


def _make_hold_df(rows_data: List[dict]) -> pd.DataFrame:
    """Build a minimal Parquet-compatible DataFrame from raw row dicts."""
    if not rows_data:
        return pd.DataFrame(columns=[
            "CONTAINERID", "LOT_ID", "PJ_WORKORDER", "PRODUCTNAME", "WORKCENTERNAME",
            "HOLDREASONNAME", "QTY", "HOLDTXNDATE", "HOLDEMP", "HOLDCOMMENTS",
            "RELEASETXNDATE", "RELEASEEMP", "RELEASECOMMENTS", "HOLD_HOURS",
            "NCRID", "FUTUREHOLDCOMMENTS", "HOLD_TYPE", "hold_day", "release_day",
            "RN_HOLD_DAY", "RN_FUTURE_REASON", "IS_FUTURE_HOLD", "FUTURE_HOLD_FLAG",
        ])
    return pd.DataFrame(rows_data)


@st.composite
def hold_rows(draw, max_rows=20):
    n = draw(st.integers(min_value=0, max_value=max_rows))
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for i in range(n):
        hold_hours = draw(st.floats(min_value=0.01, max_value=500.0, allow_nan=False))
        released = draw(st.booleans())
        hold_type = draw(st.sampled_from(["quality", "non-quality"]))
        rn_future = draw(st.integers(min_value=1, max_value=5))
        hold_dt = base + timedelta(days=i % 7)
        release_dt = hold_dt + timedelta(hours=hold_hours) if released else None
        rows.append({
            "CONTAINERID": f"C{i:04d}",
            "LOT_ID": f"L{i:04d}",
            "PJ_WORKORDER": f"WO{i:04d}",
            "PRODUCTNAME": "PROD",
            "WORKCENTERNAME": "WC1",
            "HOLDREASONNAME": _QUALITY_REASONS[i % 2] if hold_type == "quality" else _NON_QUALITY_REASONS[i % 2],
            "QTY": draw(st.integers(min_value=1, max_value=500)),
            "HOLDTXNDATE": pd.Timestamp(hold_dt),
            "HOLDEMP": "EMP01",
            "HOLDCOMMENTS": "test",
            "RELEASETXNDATE": pd.Timestamp(release_dt) if release_dt else pd.NaT,
            "RELEASEEMP": "EMP02" if released else None,
            "RELEASECOMMENTS": "done" if released else None,
            "HOLD_HOURS": hold_hours if released else hold_hours + 10.0,
            "NCRID": None,
            "FUTUREHOLDCOMMENTS": None,
            "HOLD_TYPE": hold_type,
            "hold_day": hold_dt.strftime("%Y-%m-%d"),
            "release_day": release_dt.strftime("%Y-%m-%d") if release_dt else None,
            "RN_HOLD_DAY": 1,
            "RN_FUTURE_REASON": rn_future,
            "IS_FUTURE_HOLD": 0,
            "FUTURE_HOLD_FLAG": 1,
        })
    return rows


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.property
class TestDurationAvgMaxInvariants:
    """AVG/MAX duration fields satisfy non-negativity and AVG ≤ MAX."""

    def _run(self, rows, hold_type="quality"):
        from mes_dashboard.services.hold_history_sql_runtime import _attach_spool_view, _query_duration
        df = _make_hold_df(rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "hold.parquet")
            df.to_parquet(path, index=False, engine="pyarrow")
            conn = duckdb.connect(":memory:")
            try:
                _attach_spool_view(conn, path)
                return _query_duration(
                    conn, hold_type=hold_type, record_type="new",
                    start_date="2026-01-01", end_date="2026-01-07",
                )
            finally:
                conn.close()

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_avg_released_non_negative(self, rows):
        result = self._run(rows)
        assert result["avgReleasedHours"] >= 0

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_max_released_non_negative(self, rows):
        result = self._run(rows)
        assert result["maxReleasedHours"] >= 0

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_avg_on_hold_non_negative(self, rows):
        result = self._run(rows)
        assert result["avgOnHoldHours"] >= 0

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_avg_leq_max_released(self, rows):
        result = self._run(rows)
        if result["maxReleasedHours"] > 0:
            assert result["avgReleasedHours"] <= result["maxReleasedHours"] + 1e-9

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_avg_leq_max_on_hold(self, rows):
        result = self._run(rows)
        if result["maxOnHoldHours"] > 0:
            assert result["avgOnHoldHours"] <= result["maxOnHoldHours"] + 1e-9

    @given(hold_rows(max_rows=0))
    @settings(max_examples=5, deadline=None)
    def test_empty_set_returns_zeros(self, rows):
        result = self._run(rows)
        assert result["avgReleasedHours"] == 0.0
        assert result["maxReleasedHours"] == 0.0
        assert result["avgOnHoldHours"] == 0.0
        assert result["maxOnHoldHours"] == 0.0


@pytest.mark.property
class TestRepeatQualityInvariants:
    """repeatQualityHoldQty is non-negative and non-quality section is always 0."""

    def _run_trend(self, rows):
        from mes_dashboard.services.hold_history_sql_runtime import _attach_spool_view, _query_trend
        df = _make_hold_df(rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "hold.parquet")
            df.to_parquet(path, index=False, engine="pyarrow")
            conn = duckdb.connect(":memory:")
            try:
                _attach_spool_view(conn, path)
                return _query_trend(conn, start_date="2026-01-01", end_date="2026-01-07")
            finally:
                conn.close()

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_repeat_quality_non_negative(self, rows):
        result = self._run_trend(rows)
        for day in result["days"]:
            assert day["quality"]["repeatQualityHoldQty"] >= 0

    @given(hold_rows())
    @settings(max_examples=50, deadline=None)
    def test_non_quality_repeat_always_zero(self, rows):
        result = self._run_trend(rows)
        for day in result["days"]:
            assert day["non_quality"]["repeatQualityHoldQty"] == 0
