"""Property: filter normalisation is idempotent.

normalize(normalize(F)) == normalize(F)

`_normalize_tokens` strips whitespace, removes empty strings, and deduplicates.
A second pass over already-normalized tokens should be a no-op.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mes_dashboard.services.yield_alert_service import _normalize_tokens
from tests.property.strategies import filter_dict

_token_list = st.lists(st.text(max_size=50), max_size=20)


@pytest.mark.property
@given(tokens=_token_list)
def test_normalize_tokens_is_idempotent(tokens):
    first = _normalize_tokens(tokens)
    second = _normalize_tokens(first)
    assert first == second, (
        f"_normalize_tokens is not idempotent:\n  first={first!r}\n  second={second!r}"
    )


@pytest.mark.property
@given(tokens=st.just(None))
def test_normalize_tokens_none_is_idempotent(tokens):
    first = _normalize_tokens(tokens)
    second = _normalize_tokens(first)
    assert first == second


@pytest.mark.property
@given(filters=filter_dict)
def test_normalize_filter_values_idempotent(filters):
    """Normalizing a filter dict twice yields the same result."""
    from mes_dashboard.services.yield_alert_dataset_cache import _normalize_filter_values

    first = _normalize_filter_values(filters)
    second = _normalize_filter_values(first)
    assert first == second, (
        f"_normalize_filter_values is not idempotent:\n  first={first!r}\n  second={second!r}"
    )
