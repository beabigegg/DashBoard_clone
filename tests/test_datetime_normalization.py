# -*- coding: utf-8 -*-
"""Unit tests for datetime normalization and `today` semantics.

The MES Dashboard runs on a server anchored to Asia/Taipei (UTC+8).
These tests assert that:
- `date.today()` references are mockable and produce deterministic results
- Default date-range helpers produce YYYY-MM-DD strings in correct order
- Date validation (start ≤ end, format check) behaves consistently
- Relative-date offsets (e.g. 29-day window) are computed correctly

Note: the server's system clock is expected to be set to Asia/Taipei time.
Since TZ is a system concern, we mock `date.today()` to eliminate
flakiness and pin the reference date for all assertions.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest


# ── Helpers under test ────────────────────────────────────────────────────────

def _import_reject_default():
    from mes_dashboard.routes.reject_history_routes import _default_date_range
    return _default_date_range


def _import_yield_default():
    from mes_dashboard.routes.yield_alert_routes import _default_date_range
    return _default_date_range


def _import_validate():
    from mes_dashboard.routes.reject_history_routes import _validate_primary_query_date_range
    return _validate_primary_query_date_range


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDefaultDateRange:
    """_default_date_range in reject_history_routes and yield_alert_routes."""

    def test_end_date_equals_today(self):
        """end_date must match today's date."""
        fake_today = date(2024, 6, 15)
        default_range = _import_reject_default()

        with patch('mes_dashboard.routes.reject_history_routes.date') as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.fromisoformat = date.fromisoformat
            start_str, end_str = default_range()

        assert end_str == "2024-06-15"

    def test_start_date_is_29_days_before_today(self):
        """start_date must be today minus 29 days (30-day window inclusive)."""
        fake_today = date(2024, 6, 15)
        default_range = _import_reject_default()

        with patch('mes_dashboard.routes.reject_history_routes.date') as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.fromisoformat = date.fromisoformat
            start_str, end_str = default_range()

        assert start_str == "2024-05-17"  # 2024-06-15 - 29 = 2024-05-17

    def test_start_before_end(self):
        """start_date must always be before end_date."""
        fake_today = date(2024, 1, 1)
        default_range = _import_reject_default()

        with patch('mes_dashboard.routes.reject_history_routes.date') as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.fromisoformat = date.fromisoformat
            start_str, end_str = default_range()

        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        assert start < end

    def test_format_is_iso_yyyy_mm_dd(self):
        """Both returned strings must match YYYY-MM-DD format."""
        import re
        fake_today = date(2024, 3, 5)
        default_range = _import_reject_default()

        with patch('mes_dashboard.routes.reject_history_routes.date') as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.fromisoformat = date.fromisoformat
            start_str, end_str = default_range()

        iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        assert iso_pattern.match(start_str), f"start_date not ISO: {start_str!r}"
        assert iso_pattern.match(end_str), f"end_date not ISO: {end_str!r}"

    def test_yield_alert_same_30day_window(self):
        """yield_alert_routes also uses a 30-day (29-day offset) default window."""
        fake_today = date(2024, 6, 15)
        default_range = _import_yield_default()

        with patch('mes_dashboard.routes.yield_alert_routes.date') as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.fromisoformat = date.fromisoformat
            start_str, end_str = default_range()

        assert end_str == "2024-06-15"
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        assert (end - start).days == 29  # 30-day window


class TestDateRangeValidation:
    """_validate_primary_query_date_range in reject_history_routes."""

    def test_valid_range_returns_none(self):
        validate = _import_validate()
        assert validate("2024-01-01", "2024-01-31") is None

    def test_end_before_start_returns_error(self):
        validate = _import_validate()
        result = validate("2024-02-01", "2024-01-01")
        assert result is not None
        assert isinstance(result, str)

    def test_invalid_format_returns_error(self):
        validate = _import_validate()
        result = validate("01/01/2024", "31/01/2024")
        assert result is not None

    def test_same_start_and_end_is_valid(self):
        """Single-day query must be allowed (1 day range)."""
        validate = _import_validate()
        assert validate("2024-06-15", "2024-06-15") is None

    def test_large_range_returns_error(self):
        """Ranges exceeding the configured maximum must be rejected."""
        validate = _import_validate()
        result = validate("2024-01-01", "2025-12-31")  # ~730 days, well over limit
        assert result is not None


class TestDateArithmetic:
    """Verify date arithmetic is stable and doesn't drift across month/year boundaries."""

    def test_end_of_year_window(self):
        """29-day offset spanning year boundary is computed correctly."""
        today = date(2024, 1, 10)
        start = today - timedelta(days=29)
        assert start == date(2023, 12, 12)

    def test_end_of_month_rollover(self):
        """Offset across month boundary produces correct start date."""
        today = date(2024, 3, 5)
        start = today - timedelta(days=29)
        assert start == date(2024, 2, 5)

    def test_leap_year_feb_window(self):
        """Date arithmetic over Feb 29 in a leap year is handled correctly."""
        today = date(2024, 3, 1)  # 2024 is a leap year
        start = today - timedelta(days=29)
        assert start == date(2024, 2, 1)  # 2024-03-01 - 29 days = 2024-02-01

    def test_iso_format_round_trip(self):
        """date.fromisoformat(d.strftime('%Y-%m-%d')) must produce the same date."""
        for d in [date(2024, 1, 1), date(2024, 12, 31), date(2024, 2, 29)]:
            assert date.fromisoformat(d.strftime('%Y-%m-%d')) == d
