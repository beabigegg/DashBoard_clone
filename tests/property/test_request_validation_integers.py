"""Property: integer boundary handling in request validation.

`validate_workcenter_group_filter` converts any value via `str()` before
processing. Integer arguments must therefore:
  - Never raise an unexpected exception
  - Return a string error message (str) or None
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mes_dashboard.core.request_validation import validate_workcenter_group_filter
from tests.property.strategies import arbitrary_int

_FORBIDDEN = (KeyError, IndexError, AttributeError, TypeError, ValueError)


@pytest.mark.property
@given(value=arbitrary_int)
def test_integer_input_never_raises(value):
    """Integers passed where text is expected must not raise raw exceptions."""
    try:
        result = validate_workcenter_group_filter(value)
        assert result is None or isinstance(result, str)
    except _FORBIDDEN as exc:
        pytest.fail(f"Unexpected {type(exc).__name__}: {exc!r}")


@pytest.mark.property
@given(value=st.one_of(st.floats(allow_nan=False), arbitrary_int, st.booleans()))
def test_non_string_types_handled_safely(value):
    """Non-string scalar inputs must be coerced safely, never crash."""
    try:
        result = validate_workcenter_group_filter(value)
        assert result is None or isinstance(result, str)
    except _FORBIDDEN as exc:
        pytest.fail(f"Unexpected {type(exc).__name__} for {value!r}: {exc!r}")
