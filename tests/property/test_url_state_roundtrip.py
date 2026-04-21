"""Property: URL state round-trip via urllib.parse.

NOTE: The full URL state codec is implemented in frontend JavaScript
(query-tool/App.vue). This module tests the Python-side of URL state
handling: encoding a dict of state parameters to a query string and
decoding it back must produce semantically equivalent state.

This uses `urllib.parse.urlencode` / `urllib.parse.parse_qs`, which is what
any Flask `request.args` parsing builds on.
"""

import pytest
from urllib.parse import urlencode, parse_qs, quote, unquote
from hypothesis import given, assume
from hypothesis import strategies as st

from tests.property.strategies import url_state


def _encode_state(state: dict) -> str:
    """Encode a state dict to a query string."""
    params = []
    for key, value in state.items():
        if isinstance(value, list):
            for item in value:
                params.append((key, str(item)))
        else:
            params.append((key, str(value)))
    return urlencode(params)


def _decode_state(qs: str) -> dict:
    """Decode a query string back to a state dict."""
    parsed = parse_qs(qs, keep_blank_values=True)
    result = {}
    for key, values in parsed.items():
        result[key] = values if len(values) > 1 else values[0]
    return result


@pytest.mark.property
@given(state=url_state)
def test_url_state_encode_decode_roundtrip(state):
    """Structured state must survive encode → decode with no data loss."""
    encoded = _encode_state(state)
    decoded = _decode_state(encoded)

    for key, value in state.items():
        if isinstance(value, list):
            if not value:
                # Empty lists produce no query-string entries; key is absent in decoded
                assert key not in decoded or decoded[key] == [], (
                    f"Expected no entry for empty list key {key!r}"
                )
                continue
            assert key in decoded, f"Key {key!r} lost after round-trip"
            recovered = decoded[key] if isinstance(decoded[key], list) else [decoded[key]]
            assert recovered == [str(v) for v in value], (
                f"List values for {key!r} changed: {value!r} → {recovered!r}"
            )
        else:
            assert key in decoded, f"Key {key!r} lost after round-trip"
            recovered = decoded[key] if not isinstance(decoded[key], list) else decoded[key][0]
            assert recovered == str(value), (
                f"Value for {key!r} changed: {value!r} → {recovered!r}"
            )


@pytest.mark.property
@given(state=url_state)
def test_url_state_encode_produces_valid_url(state):
    """Encoded state must be a valid (decodable) query string."""
    encoded = _encode_state(state)
    # If it can be decoded without error it's structurally valid
    decoded = parse_qs(encoded)
    assert isinstance(decoded, dict)


@pytest.mark.property
@given(state=url_state)
def test_url_state_encode_is_deterministic(state):
    """Encoding the same state twice must yield the same query string."""
    assert _encode_state(state) == _encode_state(state)
