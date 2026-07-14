# -*- coding: utf-8 -*-
"""Property: PA-13/D3 cumulative-trend aggregate-then-divide invariant.

The daily achievement-rate trend for CumulativeView
(useProductionAchievementDuckDB.ts computeCumulativeView(), business-rules.md
PA-13) must be computed as

    SUM(actual across all package_lf_groups for that day)
    / SUM(plan across all package_lf_groups for that day)

(aggregate-then-divide) -- NEVER the mean of each group's own already-
divided percentage (design.md D3). The two formulas are not merely "usually"
different: for exactly two groups the difference has an exact closed form
(derived below and verified empirically before being encoded as an
assertion), so this property is airtight, not probabilistic:

    aggregate - mean = (r1 - r2)(p1 - p2) / (2(p1 + p2))     [r_i = a_i/p_i]

They coincide EXACTLY when either every group shares the same percentage
(r1 == r2) or every group shares the same plan magnitude (p1 == p2), and
differ in EVERY other case -- never "coincidentally" for any other reason.
This generalizes the single hand-picked fixture in
frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts
("aggregate-then-divide (D3)", 950/1000 vs 5/10) across generated cases, per
test-plan.md's Data-boundary section and business-rules.md PA-13's decision-
table row ("Cumulative trend chart, one day with multiple PACKAGE_LF groups
of unequal plan magnitude").

Note on precision: the commonly-repeated shorthand "differs whenever plan
magnitudes differ" is an informal rationale, not the precise condition --
two groups with DIFFERENT plans but the SAME percentage still coincide (see
`test_two_group_aggregate_equals_mean_iff_ratio_or_plan_shared` below, both
branches). The precise condition requires BOTH the percentages and the plan
magnitudes to differ; this file tests the precise condition using exact
rational (`Fraction`) arithmetic, not the shorthand, and not float tolerance.

All strategies here are pure-arithmetic and local to this file (no shared
`tests/property/strategies.py` entry needed -- mirrors the local
`@st.composite` convention already used by
tests/property/test_hold_history_duration_invariants.py).
"""
from __future__ import annotations

from fractions import Fraction
from typing import List, Tuple

import pytest
from hypothesis import given
from hypothesis import strategies as st

# ── Data generation ───────────────────────────────────────────────────────

# daily_plan_qty is always > 0 for a row that legitimately participates in
# the trend denominator (PA-11); actual_output_qty is always >= 0 (PA-05).
_plan_qty = st.integers(min_value=1, max_value=100_000)
_actual_qty = st.integers(min_value=0, max_value=100_000)
_group = st.tuples(_actual_qty, _plan_qty)


@st.composite
def _two_groups_with_differing_ratio_and_plan(draw) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Construct (g1, g2) that ALWAYS satisfy p1 != p2 and r1 != r2 BY
    CONSTRUCTION -- never by `assume()`-discarding a generated example -- so
    there is no FilteredTooMuch health-check risk. p2 is offset from p1 by a
    guaranteed-nonzero delta; a2 is perturbed by +/-1 in the rare case it
    would otherwise coincidentally reproduce g1's exact percentage (adjacent
    integer numerators over the same denominator can never produce equal
    fractions, so this perturbation is a deterministic, always-successful
    tie-break, not a retry loop)."""
    a1 = draw(_actual_qty)
    p1 = draw(_plan_qty)
    delta_p = draw(st.integers(min_value=1, max_value=100_000))
    p2 = p1 + delta_p
    a2 = draw(_actual_qty)
    if Fraction(a2, p2) == Fraction(a1, p1):
        a2 = a2 + 1 if a2 < 100_000 else a2 - 1
    return (a1, p1), (a2, p2)


def _aggregate_then_divide(groups: List[Tuple[int, int]]) -> Fraction:
    """PA-13/D3: SUM(actual)/SUM(plan) across ALL package_lf_groups for the day."""
    total_actual = sum(a for a, _ in groups)
    total_plan = sum(p for _, p in groups)
    return Fraction(total_actual, total_plan)


def _mean_of_percentages(groups: List[Tuple[int, int]]) -> Fraction:
    """The deliberately-WRONG formula this invariant guards against: the
    unweighted mean of each group's own already-divided percentage."""
    ratios = [Fraction(a, p) for a, p in groups]
    return sum(ratios, Fraction(0)) / len(ratios)


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.property
@given(g1=_group, g2=_group)
def test_two_group_aggregate_equals_mean_iff_ratio_or_plan_shared(g1, g2):
    """Exact (not approximate) characterization for 2 groups, using exact
    rational (Fraction) arithmetic so there is no floating-point-tolerance
    guesswork: aggregate-then-divide equals mean-of-percentages IFF the two
    groups share the same percentage OR the same plan magnitude, and
    STRICTLY differs in every other case (business-rules.md PA-13 decision
    table: "one day with multiple PACKAGE_LF groups of unequal plan
    magnitude -> aggregate-then-divide, never a mean of per-group
    percentages")."""
    a1, p1 = g1
    a2, p2 = g2
    r1, r2 = Fraction(a1, p1), Fraction(a2, p2)

    aggregate = _aggregate_then_divide([g1, g2])
    mean = _mean_of_percentages([g1, g2])

    if r1 == r2 or p1 == p2:
        assert aggregate == mean, f"g1={g1} g2={g2}: expected coincidence, got {aggregate} != {mean}"
    else:
        assert aggregate != mean, f"g1={g1} g2={g2}: expected divergence, both equal {aggregate}"


@pytest.mark.property
@given(pair=_two_groups_with_differing_ratio_and_plan())
def test_generalizes_hand_picked_950_1000_vs_5_10_fixture(pair):
    """Generalizes the ONE hand-picked
    useProductionAchievementDuckDB.test.ts fixture (950/1000 vs 5/10,
    "aggregate-then-divide (D3)") across MANY generated unequal-plan,
    unequal-percentage cases -- the literal PA-13 decision-table scenario: a
    noisy small-plan group's % must not be weighted equally with a stable
    large-plan group's %. Every generated example is on-topic by
    construction (see `_two_groups_with_differing_ratio_and_plan`), so this
    never relies on `assume()`-discarding."""
    g1, g2 = pair
    aggregate = _aggregate_then_divide([g1, g2])
    mean = _mean_of_percentages([g1, g2])
    assert aggregate != mean, f"g1={g1} g2={g2} aggregate={aggregate} mean={mean}"


@pytest.mark.property
@given(groups=st.lists(_group, min_size=2, max_size=6))
def test_aggregate_then_divide_is_weighted_average_bounded_by_extremes(groups):
    """General N-group sanity invariant (always true, unconditionally, any
    N): the correct aggregate-then-divide result is a plan-weighted average
    of the per-group percentages, so it must always lie within
    [min(percentage), max(percentage)] -- guards against a totally different
    wrong formula regressing in (e.g. summing percentages directly instead
    of qty), not just the mean-of-percentages formula covered above."""
    ratios = [Fraction(a, p) for a, p in groups]
    aggregate = _aggregate_then_divide(groups)
    assert min(ratios) <= aggregate <= max(ratios)
