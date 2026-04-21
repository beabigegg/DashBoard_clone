"""Property: pagination clamping never crashes and stays within bounds.

The pagination pattern used across yield_alert_service and similar services:
  normalized = min(max(1, int(per_page or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)

Any integer input must:
  - Produce a result >= 1
  - Produce a result <= MAX_PAGE_SIZE
  - Never raise an exception
"""

import pytest
from hypothesis import given

from mes_dashboard.config.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from tests.property.strategies import size_int, page_int


def _clamp_page_size(per_page) -> int:
    """Mirror the clamping logic used in yield_alert_service and routes."""
    return min(max(1, int(per_page or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)


def _clamp_page_number(page) -> int:
    """Mirror the page clamping logic: negative/zero → 1."""
    return max(1, int(page or 1))


@pytest.mark.property
@given(per_page=size_int)
def test_page_size_clamp_stays_in_bounds(per_page):
    result = _clamp_page_size(per_page)
    assert 1 <= result <= MAX_PAGE_SIZE, (
        f"Clamped size {result} out of bounds [1, {MAX_PAGE_SIZE}] for input {per_page}"
    )


@pytest.mark.property
@given(per_page=size_int)
def test_page_size_clamp_never_raises(per_page):
    try:
        result = _clamp_page_size(per_page)
        assert isinstance(result, int)
    except Exception as exc:
        pytest.fail(f"Unexpected {type(exc).__name__}: {exc!r}")


@pytest.mark.property
@given(page=page_int)
def test_page_number_clamp_stays_positive(page):
    result = _clamp_page_number(page)
    assert result >= 1, f"Clamped page {result} is not >= 1 for input {page}"


@pytest.mark.property
@given(per_page=size_int)
def test_oversized_page_size_clamped_to_max(per_page):
    """Any input larger than MAX_PAGE_SIZE is clamped, not rejected."""
    result = _clamp_page_size(per_page)
    assert result <= MAX_PAGE_SIZE
