"""Property: parse_wildcard_tokens is idempotent (PHF-02 §6, AC-5).

For every value `x`, `parse(format(parse(x))) == parse(x)`.

Because the dataclass `WildcardToken` is the canonical form (insertion
order, kind, bound_value), we assert that re-parsing the *emitted* token
representation yields the same list of tokens.

The emitted token representation is `bound_value` with `%` → `*` and
`\\%` / `\\_` unescaped — that is, the original textual form the user
would have typed for the same canonical token.

We test the property in BOTH directions:
  (a) valid grammar inputs: assert no raise + idempotent normalisation
  (b) invalid grammar inputs: assert WildcardValidationError raised
      deterministically (i.e. running twice with the same input raises
      the same way — no order-dependent state).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mes_dashboard.core.request_validation import (
    WildcardToken,
    WildcardValidationError,
    parse_wildcard_tokens,
)


# ── Strategies ───────────────────────────────────────────────────────────────

# A safe alphabet that contains NO meta-chars (', ;, --, /*, */) and NO
# control chars. We deliberately include % and _ so the LIKE-literal
# escape path is exercised. We include * sparingly so multi-star inputs
# are produced naturally.
_safe_alphabet = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"),
    whitelist_characters="-_.%",
)

# Tokens that the parser may or may not accept (grammar may reject).
_arbitrary_token = st.text(alphabet=_safe_alphabet, min_size=0, max_size=20)
# Include an explicit `*` sometimes.
_token_with_star = st.builds(
    lambda base, star_count, pos: (
        base if star_count == 0
        else (base[:pos] + "*" * star_count + base[pos:])
    ),
    base=_arbitrary_token,
    star_count=st.integers(min_value=0, max_value=3),
    pos=st.integers(min_value=0, max_value=10),
)

# A raw multi-line input — list of tokens separated by spaces / commas /
# newlines.
_multi_line_input = st.lists(_token_with_star, min_size=0, max_size=10).map(
    lambda lst: "\n".join(lst)
)

# A list-of-strings input variant.
_list_input = st.lists(_token_with_star, min_size=0, max_size=10)


def _emit(token: WildcardToken) -> str:
    """Emit a textual form that, when re-parsed, yields the same token.

    For `exact` tokens: the bound_value IS the original user text.
    For `pattern` tokens: undo the `* → %` translation and unescape `\\%` / `\\_`.
    """
    if token.kind == "exact":
        return token.bound_value
    # pattern — bound_value has '%' (wildcard) and '\\%' / '\\_' (escaped literals)
    # Reverse: replace unescaped '%' with '*', then strip the escape backslashes.
    out = []
    i = 0
    bv = token.bound_value
    while i < len(bv):
        ch = bv[i]
        if ch == "\\" and i + 1 < len(bv) and bv[i + 1] in ("%", "_"):
            out.append(bv[i + 1])
            i += 2
            continue
        if ch == "%":
            out.append("*")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _emit_all(tokens: list[WildcardToken]) -> list[str]:
    return [_emit(t) for t in tokens]


# ── Properties ──────────────────────────────────────────────────────────────


@pytest.mark.property
@given(raw=_multi_line_input)
@settings(deadline=None)
def test_parser_idempotence_str_input(raw):
    """parse(format(parse(x))) == parse(x) for string inputs."""
    try:
        first = parse_wildcard_tokens("mfg_orders", raw)
    except WildcardValidationError:
        # Determinism: running twice raises the same way.
        with pytest.raises(WildcardValidationError):
            parse_wildcard_tokens("mfg_orders", raw)
        return

    emitted = _emit_all(first)
    second = parse_wildcard_tokens("mfg_orders", emitted)
    assert first == second, (
        f"parser not idempotent:\n  raw={raw!r}\n  first={first!r}\n  "
        f"emitted={emitted!r}\n  second={second!r}"
    )


@pytest.mark.property
@given(raw=_list_input)
@settings(deadline=None)
def test_parser_idempotence_list_input(raw):
    """parse(format(parse(x))) == parse(x) for list-of-strings inputs."""
    try:
        first = parse_wildcard_tokens("lot_ids", raw)
    except WildcardValidationError:
        with pytest.raises(WildcardValidationError):
            parse_wildcard_tokens("lot_ids", raw)
        return

    emitted = _emit_all(first)
    second = parse_wildcard_tokens("lot_ids", emitted)
    assert first == second, (
        f"parser not idempotent:\n  raw={raw!r}\n  first={first!r}\n  "
        f"emitted={emitted!r}\n  second={second!r}"
    )


@pytest.mark.property
@given(raw=_list_input)
@settings(deadline=None)
def test_parser_deterministic_under_repetition(raw):
    """Calling parse_wildcard_tokens twice on the same input yields equal
    results (no order-dependent state, no module-level mutation).
    """
    try:
        first = parse_wildcard_tokens("wafer_lots", raw)
    except WildcardValidationError as exc1:
        with pytest.raises(WildcardValidationError) as exc2:
            parse_wildcard_tokens("wafer_lots", raw)
        assert exc2.value.field == exc1.field
        return

    second = parse_wildcard_tokens("wafer_lots", raw)
    assert first == second
