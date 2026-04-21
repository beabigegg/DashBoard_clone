"""Property: request_validation helpers never raise unexpected exceptions.

Only `str | None` is a valid return type. Callers must never see a raw
`KeyError`, `IndexError`, `AttributeError`, `TypeError`, or `ValueError`.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mes_dashboard.core.request_validation import (
    validate_optional_date_range,
    validate_workcenter_group_filter,
)
from tests.property.strategies import arbitrary_text, arbitrary_date_str

_FORBIDDEN = (KeyError, IndexError, AttributeError, TypeError, ValueError)


@pytest.mark.property
@given(value=arbitrary_text)
def test_workcenter_group_filter_never_raises_untyped(value):
    try:
        result = validate_workcenter_group_filter(value)
        assert result is None or isinstance(result, str)
    except _FORBIDDEN as exc:
        pytest.fail(f"Unexpected exception type {type(exc).__name__}: {exc!r}")


@pytest.mark.property
@given(value=st.one_of(st.just(None), st.just(""), arbitrary_text))
def test_workcenter_group_filter_none_never_raises(value):
    try:
        result = validate_workcenter_group_filter(value)
        assert result is None or isinstance(result, str)
    except _FORBIDDEN as exc:
        pytest.fail(f"Unexpected exception type {type(exc).__name__}: {exc!r}")


@pytest.mark.property
@given(start=arbitrary_date_str, end=arbitrary_date_str)
def test_validate_date_range_never_raises_untyped(start, end):
    try:
        result = validate_optional_date_range(start, end)
        assert result is None or isinstance(result, str)
    except _FORBIDDEN as exc:
        pytest.fail(f"Unexpected exception type {type(exc).__name__}: {exc!r}")


@pytest.mark.property
@given(
    start=arbitrary_date_str,
    end=arbitrary_date_str,
    start_field=arbitrary_text,
    end_field=arbitrary_text,
)
def test_validate_date_range_custom_fields_never_raises(start, end, start_field, end_field):
    try:
        result = validate_optional_date_range(
            start, end, start_field=start_field, end_field=end_field
        )
        assert result is None or isinstance(result, str)
    except _FORBIDDEN as exc:
        pytest.fail(f"Unexpected exception type {type(exc).__name__}: {exc!r}")
