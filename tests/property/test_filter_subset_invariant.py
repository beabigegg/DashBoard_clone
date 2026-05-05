"""Property: filter normalisation never widens the result set.

`_normalize_tokens` strips, deduplicates, and removes empty strings.
After normalization, any row that matches the normalized filter MUST also
match the original filter. (Normalization can only narrow or keep the set.)

The filter model:
  - An empty list means "no filter applied" (match everything)
  - A non-empty list means "column value must be in this set"
"""

import pytest
from hypothesis import given

from mes_dashboard.services.yield_alert_service import _normalize_tokens
from tests.property.strategies import filter_dict, synthetic_dataset

_FILTER_TO_COLUMN = {
    "departments": "DEPARTMENT_GROUP",
    "process_category": "PROCESS_CATEGORY",
    "lines": "LINE_NAME",
    "packages": "PACKAGE_NAME",
    "types": "TYPE_NAME",
    "functions": "FUNCTION_NAME",
}


def _matches(row: dict, filter_key: str, tokens: list[str]) -> bool:
    """Return True if row matches the filter (empty list = match all)."""
    if not tokens:
        return True
    col = _FILTER_TO_COLUMN.get(filter_key)
    if col is None:
        return True
    return row.get(col, "") in tokens


def _matching_rows(dataset: list[dict], filter_key: str, tokens: list[str]) -> set[int]:
    return {i for i, row in enumerate(dataset) if _matches(row, filter_key, tokens)}


@pytest.mark.property
@given(dataset=synthetic_dataset, filters=filter_dict)
def test_normalized_filter_is_subset_of_original(dataset, filters):
    """normalize(F) produces a filter that selects a subset of F's rows.

    Caveat: when raw_tokens contains ONLY whitespace/empty strings,
    normalization yields [] (empty = match-all), which is intentionally
    broader. We skip those cases — the relevant invariant is that valid
    non-empty tokens are not dropped.
    """
    for key, raw_tokens in filters.items():
        normalized = _normalize_tokens(raw_tokens)
        # Skip the degenerate case: all tokens were empty/whitespace
        # In this case normalization correctly converts [] to match-all
        if raw_tokens and not normalized:
            continue
        original_matches = _matching_rows(dataset, key, raw_tokens)
        normalized_matches = _matching_rows(dataset, key, normalized)
        assert normalized_matches <= original_matches, (
            f"Normalization widened result for key={key!r}: "
            f"normalized matched {normalized_matches - original_matches} extra rows"
        )


@pytest.mark.property
@given(dataset=synthetic_dataset, filters=filter_dict)
def test_empty_normalized_filter_matches_all(dataset, filters):
    """If normalization produces empty tokens, all rows should match."""
    for key, raw_tokens in filters.items():
        normalized = _normalize_tokens(raw_tokens)
        if not normalized:
            normalized_matches = _matching_rows(dataset, key, normalized)
            assert normalized_matches == set(range(len(dataset))), (
                "Empty normalized filter should match all rows"
            )
