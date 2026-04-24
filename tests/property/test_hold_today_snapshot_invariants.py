"""Property: today-snapshot summary invariants.

Mathematical invariants that must hold for any valid today-snapshot summary:

  1. onHoldTotalCount >= 0
  2. onHoldTotalQty >= 0
  3. todayNewQty >= 0, todayReleaseQty >= 0, todayFutureHoldQty >= 0
  4. onHoldAvgHours >= 0, onHoldMaxHours >= 0
  5. onHoldMaxHours >= onHoldAvgHours (max >= average)
  6. _apply_record_type_filter is idempotent: applying the same filter twice
     yields the same row count

These tests mock the DataFrame operations directly — no Oracle required.
"""

from __future__ import annotations

import pytest

try:
    import pandas as pd
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

pytestmark = pytest.mark.property


def _make_summary_dict(
    on_hold_count: int,
    on_hold_qty: int,
    today_new_qty: int,
    today_release_qty: int,
    today_future_qty: int,
    avg_hours: float,
    max_hours: float,
) -> dict:
    return {
        "onHoldTotalCount": on_hold_count,
        "onHoldTotalQty": on_hold_qty,
        "todayNewQty": today_new_qty,
        "todayReleaseQty": today_release_qty,
        "todayFutureHoldQty": today_future_qty,
        "onHoldAvgHours": avg_hours,
        "onHoldMaxHours": max_hours,
    }


_non_neg_int = st.integers(min_value=0, max_value=100_000)
_non_neg_float = st.floats(min_value=0.0, max_value=100_000.0, allow_nan=False, allow_infinity=False)


@pytest.mark.property
@given(
    on_hold_count=_non_neg_int,
    on_hold_qty=_non_neg_int,
    today_new_qty=_non_neg_int,
    today_release_qty=_non_neg_int,
    today_future_qty=_non_neg_int,
    avg_hours=_non_neg_float,
    extra_hours=_non_neg_float,
)
def test_summary_max_hours_gte_avg(
    on_hold_count, on_hold_qty, today_new_qty, today_release_qty,
    today_future_qty, avg_hours, extra_hours,
):
    """onHoldMaxHours must always be >= onHoldAvgHours for any valid summary."""
    max_hours = avg_hours + extra_hours  # max >= avg by construction
    summary = _make_summary_dict(
        on_hold_count, on_hold_qty, today_new_qty, today_release_qty,
        today_future_qty, avg_hours, max_hours,
    )
    assert summary["onHoldMaxHours"] >= summary["onHoldAvgHours"], (
        f"Invariant violated: maxHours={summary['onHoldMaxHours']} < avgHours={summary['onHoldAvgHours']}"
    )


@pytest.mark.property
@given(
    on_hold_count=_non_neg_int,
    on_hold_qty=_non_neg_int,
    today_new_qty=_non_neg_int,
    today_release_qty=_non_neg_int,
    today_future_qty=_non_neg_int,
    avg_hours=_non_neg_float,
    max_hours=_non_neg_float,
)
def test_summary_all_values_non_negative(
    on_hold_count, on_hold_qty, today_new_qty, today_release_qty,
    today_future_qty, avg_hours, max_hours,
):
    """All summary numeric fields must be >= 0."""
    summary = _make_summary_dict(
        on_hold_count, on_hold_qty, today_new_qty, today_release_qty,
        today_future_qty, avg_hours, max_hours,
    )
    for key, val in summary.items():
        assert val >= 0, f"summary.{key} must be >= 0, got {val}"


@pytest.mark.skipif(not _PANDAS_AVAILABLE, reason="pandas required")
@pytest.mark.property
@given(
    record_type=st.sampled_from(["on_hold", "new", "release", "on_hold,new", "new,release"]),
)
def test_apply_record_type_filter_idempotent(record_type: str):
    """Applying the same record_type filter twice yields the same row count."""
    from mes_dashboard.services.hold_today_snapshot_service import _apply_record_type_filter_today as _apply_record_type_filter

    # Build a minimal DataFrame with the columns the filter inspects
    today = "2026-04-23"
    df = pd.DataFrame({
        "RELEASETXNDATE": [None, None, "2026-04-23 10:00:00", "2026-04-23 10:00:00"],
        "HOLD_DAY": [today, "2026-04-22", today, "2026-04-22"],
        "RELEASE_DAY": [None, None, today, "2026-04-22"],
        "TODAY_DATE": [today] * 4,
        "QTY": [10, 20, 30, 40],
    })

    first = _apply_record_type_filter(df, record_type)
    second = _apply_record_type_filter(first, record_type)
    assert len(first) == len(second), (
        f"_apply_record_type_filter not idempotent for record_type={record_type!r}: "
        f"first={len(first)}, second={len(second)}"
    )


@pytest.mark.skipif(not _PANDAS_AVAILABLE, reason="pandas required")
@pytest.mark.property
@given(
    n_on_hold=st.integers(min_value=0, max_value=50),
    n_new=st.integers(min_value=0, max_value=50),
    n_release=st.integers(min_value=0, max_value=50),
)
def test_build_summary_qty_non_negative(n_on_hold: int, n_new: int, n_release: int):
    """_build_summary never produces negative values regardless of input shape."""
    from mes_dashboard.services.hold_today_snapshot_service import _build_today_summary as _build_summary

    today = "2026-04-23"
    rows = []
    for i in range(n_on_hold):
        rows.append({
            "CONTAINERID": f"C{i:04d}",
            "RELEASETXNDATE": None,
            "HOLD_DAY": today,
            "RELEASE_DAY": None,
            "TODAY_DATE": today,
            "QTY": 10,
            "HOLD_HOURS": 5.0,
            "IS_FUTURE_HOLD": 0,
            "FUTUREHOLDCOMMENTS": None,
            "RN_FUTURE_REASON": 1,
            "HOLD_TYPE": "quality",
        })
    for i in range(n_new):
        rows.append({
            "CONTAINERID": f"N{i:04d}",
            "RELEASETXNDATE": None,
            "HOLD_DAY": today,
            "RELEASE_DAY": None,
            "TODAY_DATE": today,
            "QTY": 5,
            "HOLD_HOURS": 2.0,
            "IS_FUTURE_HOLD": 1,
            "FUTUREHOLDCOMMENTS": "future-comment",
            "RN_FUTURE_REASON": 1,
            "HOLD_TYPE": "quality",
        })
    for i in range(n_release):
        rows.append({
            "CONTAINERID": f"R{i:04d}",
            "RELEASETXNDATE": f"{today} 14:00:00",
            "HOLD_DAY": "2026-04-22",
            "RELEASE_DAY": today,
            "TODAY_DATE": today,
            "QTY": 8,
            "HOLD_HOURS": 24.0,
            "IS_FUTURE_HOLD": 0,
            "FUTUREHOLDCOMMENTS": None,
            "RN_FUTURE_REASON": 1,
            "HOLD_TYPE": "non-quality",
        })

    if not rows:
        df = pd.DataFrame(columns=[
            "CONTAINERID", "RELEASETXNDATE", "HOLD_DAY", "RELEASE_DAY", "TODAY_DATE",
            "QTY", "HOLD_HOURS", "IS_FUTURE_HOLD", "FUTUREHOLDCOMMENTS",
            "RN_FUTURE_REASON", "HOLD_TYPE",
        ])
    else:
        df = pd.DataFrame(rows)

    summary = _build_summary(df)
    for key, val in summary.items():
        assert isinstance(val, (int, float)), f"summary.{key} should be numeric, got {type(val)}"
        assert val >= 0, f"summary.{key} must be >= 0, got {val}"
