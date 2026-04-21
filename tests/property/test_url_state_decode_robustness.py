"""Property: URL state decode never crashes on arbitrary input.

NOTE: The full URL state codec is frontend JavaScript. This tests the Python
`urllib.parse.parse_qs` layer that underlies `flask.request.args`, verifying
that arbitrary URL-safe strings either produce a valid dict or raise only the
declared exception types (`ValueError` from malformed percent-encoding).
"""

import pytest
from urllib.parse import parse_qs
from hypothesis import given

from tests.property.strategies import url_safe_text, arbitrary_text


def _safe_decode(qs: str) -> dict | None:
    """Return parsed dict or None if the input cannot be decoded."""
    try:
        return parse_qs(qs, keep_blank_values=True)
    except ValueError:
        return None


@pytest.mark.property
@given(qs=url_safe_text)
def test_decode_url_safe_string_never_crashes(qs):
    """parse_qs on any URL-safe string must not raise unexpected exceptions."""
    result = _safe_decode(qs)
    assert result is None or isinstance(result, dict)


@pytest.mark.property
@given(qs=arbitrary_text)
def test_decode_arbitrary_string_never_crashes(qs):
    """parse_qs should not raise anything beyond ValueError."""
    try:
        result = parse_qs(qs, keep_blank_values=True)
        assert isinstance(result, dict)
    except ValueError:
        pass  # Declared exception — malformed percent-encoding
    except Exception as exc:
        pytest.fail(f"Unexpected {type(exc).__name__}: {exc!r} for input {qs!r}")
