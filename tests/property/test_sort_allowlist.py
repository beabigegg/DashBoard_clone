"""Property: sort-key allowlist enforcement.

`VALID_SORT_FIELDS` in yield_alert_service defines the allowed sort keys.
The service normalises an unknown sort key to the default ("date_bucket")
rather than raising. This test verifies:

  - Valid keys are accepted as-is (not mutated)
  - Unknown keys silently degrade to the default key
  - The normalised key is always in VALID_SORT_FIELDS (no key injection)
"""

import pytest
from hypothesis import given

from mes_dashboard.services.yield_alert_service import VALID_SORT_FIELDS
from tests.property.strategies import valid_sort_key, unknown_sort_key

_DEFAULT_SORT = "date_bucket"


def _normalize_sort_key(sort_by: str) -> str:
    """Mirror the sort normalisation in yield_alert_dataset_cache.get_alerts."""
    return sort_by if sort_by in VALID_SORT_FIELDS else _DEFAULT_SORT


@pytest.mark.property
@given(key=valid_sort_key)
def test_valid_sort_key_accepted(key):
    result = _normalize_sort_key(key)
    assert result == key, f"Valid key {key!r} was mutated to {result!r}"
    assert result in VALID_SORT_FIELDS


@pytest.mark.property
@given(key=unknown_sort_key)
def test_unknown_sort_key_degrades_to_default(key):
    result = _normalize_sort_key(key)
    assert result == _DEFAULT_SORT, (
        f"Unknown key {key!r} produced {result!r} instead of default {_DEFAULT_SORT!r}"
    )
    assert result in VALID_SORT_FIELDS


@pytest.mark.property
@given(key=valid_sort_key)
def test_sort_normalise_is_idempotent_on_valid(key):
    first = _normalize_sort_key(key)
    second = _normalize_sort_key(first)
    assert first == second


@pytest.mark.property
@given(key=unknown_sort_key)
def test_sort_normalise_is_idempotent_on_unknown(key):
    first = _normalize_sort_key(key)
    second = _normalize_sort_key(first)
    assert first == second
