"""Property: request_validation helpers are idempotent.

validate(validate(x)) == validate(x):
  - For `validate_workcenter_group_filter`: if the first call returns None
    (valid), re-validating the input must also return None.
  - For `validate_optional_date_range`: if both dates are valid ISO dates
    that satisfy the range constraint, calling twice must return the same result.
"""

import pytest
from hypothesis import given

from mes_dashboard.core.request_validation import (
    validate_optional_date_range,
    validate_workcenter_group_filter,
)
from tests.property.strategies import arbitrary_text, valid_date_str


@pytest.mark.property
@given(value=arbitrary_text)
def test_workcenter_group_filter_idempotent_on_valid(value):
    first = validate_workcenter_group_filter(value)
    if first is not None:
        return  # input was rejected — skip idempotence check
    # If it passed once, re-validating the same input must also pass
    second = validate_workcenter_group_filter(value)
    assert second is None, (
        f"Idempotence violated: first pass returned None but second returned {second!r} for {value!r}"
    )


@pytest.mark.property
@given(start=valid_date_str, end=valid_date_str)
def test_validate_date_range_idempotent_on_valid_dates(start, end):
    first = validate_optional_date_range(start, end)
    second = validate_optional_date_range(start, end)
    assert first == second, (
        f"validate_optional_date_range is not deterministic: {first!r} != {second!r}"
    )
