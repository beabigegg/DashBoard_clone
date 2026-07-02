# -*- coding: utf-8 -*-
"""Unit tests for the Python mirror of shift_code classification (PA-01/PA-02).

business-rules.md PA-01 (two-shift current regime): boundary seconds
07:29:59/07:30:00/19:29:59/19:30:00, date cutoffs outside 2020/01/01-2020/03/29.
PA-02 (three-shift historical regime): boundary seconds for A/B/C bands within
the 2020/01/01-2020/03/29 historical window.

This Python mirror is NOT on the Oracle query hot path (grouping happens
server-side via SQL CASE per design.md) -- it exists purely for unit-test
boundary assertions.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from mes_dashboard.services.production_achievement_service import compute_shift_code


class TestTwoShiftBoundarySeconds:
    """PA-01: two-shift current regime, dates outside the historical window."""

    @pytest.mark.parametrize(
        "ts, expected",
        [
            (datetime(2026, 4, 27, 0, 0, 0), "N"),
            (datetime(2026, 4, 27, 7, 29, 59), "N"),
            (datetime(2026, 4, 27, 7, 30, 0), "D"),
            (datetime(2026, 4, 27, 19, 29, 59), "D"),
            (datetime(2026, 4, 27, 19, 30, 0), "N"),
            (datetime(2026, 4, 27, 23, 59, 59), "N"),
        ],
    )
    def test_two_shift_boundary_seconds(self, ts, expected):
        assert compute_shift_code(ts) == expected

    @pytest.mark.parametrize(
        "ts",
        [
            datetime(2019, 12, 31, 12, 0, 0),
            datetime(2020, 3, 30, 12, 0, 0),
            datetime(2020, 3, 31, 12, 0, 0),
        ],
    )
    def test_two_shift_date_cutoff_inclusive_exclusive(self, ts):
        """20191231 and >= 20200330 use two-shift regime (PA-01)."""
        result = compute_shift_code(ts)
        assert result in ("N", "D")


class TestThreeShiftBoundarySeconds:
    """PA-02: three-shift historical regime, 2020/01/01-2020/03/29 inclusive."""

    @pytest.mark.parametrize(
        "ts, expected",
        [
            (datetime(2020, 2, 15, 0, 0, 0), "C"),
            (datetime(2020, 2, 15, 7, 59, 59), "C"),
            (datetime(2020, 2, 15, 8, 0, 0), "A"),
            (datetime(2020, 2, 15, 15, 59, 59), "A"),
            (datetime(2020, 2, 15, 16, 0, 0), "B"),
            (datetime(2020, 2, 15, 23, 59, 59), "B"),
        ],
    )
    def test_three_shift_window_boundary_seconds(self, ts, expected):
        assert compute_shift_code(ts) == expected

    @pytest.mark.parametrize(
        "ts, expected",
        [
            (datetime(2020, 1, 1, 8, 0, 0), "A"),
            (datetime(2020, 3, 29, 23, 59, 59), "B"),
        ],
    )
    def test_three_shift_date_window_edges_20200101_20200329(self, ts, expected):
        """2020/01/01 and 2020/03/29 are the inclusive window edges (PA-02)."""
        assert compute_shift_code(ts) == expected
