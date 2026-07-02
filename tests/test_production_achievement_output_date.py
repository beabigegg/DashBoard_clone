# -*- coding: utf-8 -*-
"""Unit tests for the Python mirror of output_date attribution (PA-03/PA-04).

PA-03 (two-shift regime): the N-shift tail (00:00:00-07:29:59) attributes to
the PREVIOUS calendar day. Confirmed example: 4/26 19:30 - 4/27 07:29 is
entirely N-shift, output_date=4/26 for the whole span.

PA-04 (three-shift regime, UNVERIFIED ASSUMPTION): by analogy, the C-shift
tail (00:00:00-07:59:59) is ASSUMED to attribute to the previous calendar day.
Not a verified acceptance target -- documented as an assumption only.
"""

from __future__ import annotations

from datetime import date, datetime

from mes_dashboard.services.production_achievement_service import compute_output_date


class TestTwoShiftOutputDate:
    def test_two_shift_n_tail_attributes_prev_day(self):
        """00:00:00-07:29:59 (N-shift tail) -> output_date = TRUNC(ts) - 1."""
        ts = datetime(2026, 4, 27, 3, 0, 0)
        assert compute_output_date(ts) == date(2026, 4, 26)

    def test_two_shift_d_and_late_n_attribute_same_day(self):
        """07:30:00-23:59:59 -> output_date = TRUNC(ts) unchanged."""
        ts_d = datetime(2026, 4, 27, 10, 0, 0)
        ts_late_n = datetime(2026, 4, 27, 20, 0, 0)
        assert compute_output_date(ts_d) == date(2026, 4, 27)
        assert compute_output_date(ts_late_n) == date(2026, 4, 27)

    def test_confirmed_0426_0427_cross_midnight_case(self):
        """4/26 19:30 - 4/27 07:29 is entirely N-shift; output_date=4/26 throughout."""
        span = [
            datetime(2026, 4, 26, 19, 30, 0),
            datetime(2026, 4, 26, 23, 59, 59),
            datetime(2026, 4, 27, 0, 0, 0),
            datetime(2026, 4, 27, 7, 29, 59),
        ]
        for ts in span:
            assert compute_output_date(ts) == date(2026, 4, 26), ts

        # 07:30:00 rolls into the D-shift for 4/27 -> output_date flips to 4/27
        assert compute_output_date(datetime(2026, 4, 27, 7, 30, 0)) == date(2026, 4, 27)

    def test_three_shift_c_tail_assumption_documented(self):
        """PA-04 UNVERIFIED ASSUMPTION: C-tail (00:00:00-07:59:59) -> prev day."""
        ts_c_tail = datetime(2020, 2, 15, 5, 0, 0)
        assert compute_output_date(ts_c_tail) == date(2020, 2, 14)

        # 08:00:00-23:59:59 (A/B bands) -> output_date unchanged
        ts_a = datetime(2020, 2, 15, 10, 0, 0)
        ts_b = datetime(2020, 2, 15, 18, 0, 0)
        assert compute_output_date(ts_a) == date(2020, 2, 15)
        assert compute_output_date(ts_b) == date(2020, 2, 15)
