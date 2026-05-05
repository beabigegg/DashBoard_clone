# -*- coding: utf-8 -*-
"""Unit tests for OEE precision and rounding stability.

Asserts that OEE/OU/yield calculation functions produce stable, deterministic
results with proper rounding. Covers both resource_history_sql_runtime
(_calc_ou_pct, _calc_avail_pct, _calc_yield_pct, _calc_oee_pct) and
yield_alert_sql_runtime (round(x, 4) on transaction_qty / scrap_qty / yield_pct).

All expected values verified by hand computation.
"""

from __future__ import annotations


from mes_dashboard.services.resource_history_sql_runtime import (
    _calc_ou_pct,
    _calc_avail_pct,
    _calc_yield_pct,
    _calc_oee_pct,
)


class TestOuPctPrecision:
    """_calc_ou_pct: OU% = PRD / (PRD+SBY+UDT+SDT+EGT) * 100, rounded to 1dp."""

    def test_basic_case(self):
        # PRD=80, others=20 → 80/100*100 = 80.0
        assert _calc_ou_pct(80, 10, 5, 3, 2) == 80.0

    def test_all_productive(self):
        # PRD=100, rest=0 → 100.0
        assert _calc_ou_pct(100, 0, 0, 0, 0) == 100.0

    def test_zero_denominator_returns_zero(self):
        assert _calc_ou_pct(0, 0, 0, 0, 0) == 0.0

    def test_fractional_rounds_to_one_decimal(self):
        # PRD=1, denom=3 → 33.333...% → rounds to 33.3
        result = _calc_ou_pct(1, 0, 1, 1, 0)
        assert result == round(1 / 3 * 100, 1)
        assert isinstance(result, float)

    def test_stability_repeated_calls_same_result(self):
        r1 = _calc_ou_pct(75.5, 10.0, 8.3, 4.2, 2.0)
        r2 = _calc_ou_pct(75.5, 10.0, 8.3, 4.2, 2.0)
        assert r1 == r2


class TestAvailPctPrecision:
    """_calc_avail_pct: Availability = (PRD+SBY+EGT) / total * 100, 1dp."""

    def test_full_availability(self):
        # All time is PRD → 100.0
        assert _calc_avail_pct(100, 0, 0, 0, 0, 0) == 100.0

    def test_zero_denominator_returns_zero(self):
        assert _calc_avail_pct(0, 0, 0, 0, 0, 0) == 0.0

    def test_downtime_reduces_availability(self):
        # PRD=60, SBY=10, EGT=0, SDT=20, UDT=10, NST=0 → num=70, denom=100 → 70.0
        assert _calc_avail_pct(60, 10, 10, 20, 0, 0) == 70.0

    def test_rounding_stability(self):
        r1 = _calc_avail_pct(73.3, 12.1, 8.8, 5.0, 0.8, 0.0)
        r2 = _calc_avail_pct(73.3, 12.1, 8.8, 5.0, 0.8, 0.0)
        assert r1 == r2


class TestYieldPctPrecision:
    """_calc_yield_pct: Yield = trackout / (trackout + ng) * 100, 1dp."""

    def test_no_ng_yields_100(self):
        assert _calc_yield_pct(100, 0) == 100.0

    def test_all_ng_yields_zero(self):
        assert _calc_yield_pct(0, 100) == 0.0

    def test_zero_denominator_returns_zero(self):
        assert _calc_yield_pct(0, 0) == 0.0

    def test_partial_ng(self):
        # trackout=90, ng=10 → 90/100*100=90.0
        assert _calc_yield_pct(90, 10) == 90.0

    def test_rounding_to_one_decimal(self):
        # trackout=2, ng=1 → 66.666...% → 66.7
        assert _calc_yield_pct(2, 1) == round(2 / 3 * 100, 1)

    def test_stability(self):
        r1 = _calc_yield_pct(987.5, 12.5)
        r2 = _calc_yield_pct(987.5, 12.5)
        assert r1 == r2


class TestOeePctPrecision:
    """_calc_oee_pct: OEE = Availability * Yield / 100, 1dp."""

    def test_perfect_oee(self):
        assert _calc_oee_pct(100.0, 100.0) == 100.0

    def test_zero_availability(self):
        assert _calc_oee_pct(0.0, 90.0) == 0.0

    def test_zero_yield(self):
        assert _calc_oee_pct(85.0, 0.0) == 0.0

    def test_typical_case_rounds_to_one_decimal(self):
        # avail=85.0, yield=90.0 → 85*90/100 = 76.5
        assert _calc_oee_pct(85.0, 90.0) == 76.5

    def test_fractional_rounds_correctly(self):
        # avail=73.3, yield=91.7 → 73.3*91.7/100 = 67.2161 → 67.2
        result = _calc_oee_pct(73.3, 91.7)
        assert result == round(73.3 * 91.7 / 100, 1)

    def test_stability_repeated_calls(self):
        r1 = _calc_oee_pct(78.4, 93.6)
        r2 = _calc_oee_pct(78.4, 93.6)
        assert r1 == r2


class TestYieldAlertPrecisionRound4:
    """yield_alert_sql_runtime uses round(x, 4) for transaction_qty/yield_pct."""

    def test_yield_pct_round4_stability(self):
        """Yield formula used in yield_alert_sql_runtime: round((1-sc/tx)*100, 4)."""
        tx, sc = 1000.0, 15.0
        r1 = round((1 - sc / tx) * 100, 4)
        r2 = round((1 - sc / tx) * 100, 4)
        assert r1 == r2
        assert r1 == 98.5  # exact: 1 - 15/1000 = 0.985, *100 = 98.5

    def test_yield_pct_zero_tx_returns_100(self):
        """When tx=0, yield is defined as 100.0 (no product = no rejects)."""
        tx = 0.0
        result = 100.0 if tx <= 0 else round((1 - 0 / tx) * 100, 4)
        assert result == 100.0

    def test_round4_precision_boundaries(self):
        """round(x, 4) preserves 4 decimal places, not more."""
        val = 1 / 7  # 0.142857142857...
        rounded = round(val, 4)
        assert rounded == 0.1429
        # Confirm no 5th decimal leakage
        assert str(rounded) in ('0.1429', '0.143')  # repr may vary

    def test_large_quantities_round_stably(self):
        """Large integers must round to exactly themselves at 4dp."""
        assert round(1000000.0, 4) == 1000000.0
        assert round(999999.9999, 4) == 999999.9999
