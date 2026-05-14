# -*- coding: utf-8 -*-
"""Route fuzz tests: MALICIOUS_INPUTS parametrize across all query-accepting endpoints.

Each test case sends one payload from MALICIOUS_INPUTS to a route that accepts
query parameters and asserts:
  - HTTP response is NOT 500
  - Response body is valid UTF-8 JSON
  - If the route validates inputs, error.code == 'VALIDATION_ERROR'

This file is the centralised fuzz coverage for tasks 5.2-5.4.  It covers the
key routes listed in task 5.1 without modifying the existing 28 route test files.

Run with:
    conda run -n mes-dashboard pytest tests/routes/test_fuzz_routes.py -v
"""

from __future__ import annotations

import json
import sys
import os
from typing import Any

import pytest

# Add project root to path so we can import fuzz payloads
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routes._fuzz_payloads import (
    MALICIOUS_INPUTS,
    WILDCARD_CONTROL_CHARS,
    WILDCARD_FIELDS,
    WILDCARD_GRAMMAR_INVALID,
    WILDCARD_META_CHARS,
)

# ---------------------------------------------------------------------------
# Shared app/client fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset rate-limit state between fuzz tests to avoid 429 cross-test bleed."""
    try:
        from mes_dashboard.core import rate_limit as rl_mod
        with rl_mod._RATE_LOCK:
            rl_mod._RATE_ATTEMPTS.clear()
    except Exception:
        pass
    yield


def _make_client():
    from mes_dashboard.app import create_app
    import mes_dashboard.core.database as db
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = {"displayName": "FuzzUser", "employeeNo": "FUZZ001"}
    return client


def _assert_not_500(response, payload, endpoint: str):
    """Assert the response is not an unhandled 500, with informative message."""
    assert response.status_code != 500, (
        f"{endpoint} returned 500 for payload {payload!r}: "
        f"{response.data[:500]}"
    )


def _assert_valid_json(response, endpoint: str):
    """Assert response body is valid UTF-8 JSON (if content-type is JSON)."""
    ct = response.content_type or ""
    if "json" not in ct:
        return
    raw = response.data.decode("utf-8", errors="replace")
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        pytest.fail(f"{endpoint} returned invalid JSON: {exc}\nBody: {raw[:300]}")


def _assert_validation_error(response, payload, endpoint: str):
    """Strict: response must be a 4xx VALIDATION_ERROR envelope.

    Used when the fuzz case MUST be rejected by the route's input validator.
    Combines not-500, status 400/422, JSON body, success=False, and
    error.code == 'VALIDATION_ERROR' into a single assertion.
    """
    raw = response.data[:500]
    assert response.status_code != 500, (
        f"{endpoint} returned 500 for payload {payload!r}: {raw!r}"
    )
    assert response.status_code in (400, 422), (
        f"{endpoint} expected 400/422 for payload {payload!r}, "
        f"got {response.status_code}: {raw!r}"
    )
    body = response.get_json(silent=True)
    assert body is not None, (
        f"{endpoint} non-JSON body for payload {payload!r}: {raw!r}"
    )
    assert body.get("success") is False, (
        f"{endpoint} envelope missing success=False for {payload!r}: {body}"
    )
    err = body.get("error") or {}
    assert err.get("code") == "VALIDATION_ERROR", (
        f"{endpoint} expected error.code=VALIDATION_ERROR for {payload!r}, "
        f"got {err.get('code')!r} (body={body})"
    )


def _payload_to_str(payload: Any) -> str:
    """Convert a payload to a string value for GET params, best-effort."""
    if isinstance(payload, str):
        return payload[:500]  # truncate very long strings for URL safety
    return json.dumps(payload)[:200]


# ---------------------------------------------------------------------------
# Helper: build query string with the fuzz value injected into key params
# ---------------------------------------------------------------------------

def _fuzz_query_string(key: str, payload: Any, extra: dict | None = None) -> str:
    """Build a query string with *key* set to the fuzz payload."""
    params = dict(extra or {})
    params[key] = _payload_to_str(payload)
    return "&".join(f"{k}={v}" for k, v in params.items())


# ---------------------------------------------------------------------------
# Reject History routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_reject_history_options_rejects_malicious_start_date(payload):
    client = _make_client()
    qs = _fuzz_query_string("start_date", payload, {"end_date": "2026-01-07"})
    r = client.get(f"/api/reject-history/options?{qs}")
    _assert_validation_error(r, payload, "/api/reject-history/options")


@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_reject_history_query_rejects_malicious_payload(payload):
    client = _make_client()
    body: dict
    if isinstance(payload, dict):
        body = payload
    else:
        body = {"start_date": _payload_to_str(payload), "end_date": "2026-01-07"}
    r = client.post(
        "/api/reject-history/query",
        json=body,
        content_type="application/json",
    )
    _assert_validation_error(r, payload, "/api/reject-history/query")


# ---------------------------------------------------------------------------
# Query Tool routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_query_tool_resolve_rejects_malicious_input(payload):
    client = _make_client()
    body: dict
    if isinstance(payload, dict):
        body = {"input_type": "lot", **payload}
    else:
        body = {"input_type": "lot", "lots": _payload_to_str(payload)}
    r = client.post(
        "/api/query-tool/resolve",
        json=body,
        content_type="application/json",
    )
    _assert_validation_error(r, payload, "/api/query-tool/resolve")


@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_query_tool_query_rejects_malicious_date(payload):
    client = _make_client()
    body: dict
    if isinstance(payload, dict):
        body = {"query_type": "lot", **payload}
    else:
        body = {
            "query_type": "lot",
            "lots": "LOT-001",
            "start_date": _payload_to_str(payload),
            "end_date": "2026-01-07",
        }
    r = client.post(
        "/api/query-tool/lot-equipment-lookup",
        json=body,
        content_type="application/json",
    )
    _assert_validation_error(r, payload, "/api/query-tool/lot-equipment-lookup")


# ---------------------------------------------------------------------------
# Hold History routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_hold_history_rejects_malicious_date(payload):
    client = _make_client()
    qs = _fuzz_query_string("start_date", payload, {"end_date": "2026-01-07"})
    r = client.get(f"/api/hold-history/view?{qs}")
    _assert_validation_error(r, payload, "/api/hold-history/view")


# ---------------------------------------------------------------------------
# Hold History today-snapshot route
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_hold_today_snapshot_rejects_malicious_hold_type(payload):
    client = _make_client()
    r = client.post(
        "/api/hold-history/today-snapshot",
        json={"hold_type": payload, "record_type": "on_hold"},
        content_type="application/json",
    )
    assert r.status_code != 500, f"500 on hold_type={payload!r}"
    body = r.data.decode("utf-8")
    json.loads(body)  # must be valid JSON


@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_hold_today_snapshot_rejects_malicious_record_type(payload):
    client = _make_client()
    r = client.post(
        "/api/hold-history/today-snapshot",
        json={"record_type": payload},
        content_type="application/json",
    )
    assert r.status_code != 500, f"500 on record_type={payload!r}"
    json.loads(r.data.decode("utf-8"))


@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_hold_today_snapshot_rejects_malicious_reason(payload):
    client = _make_client()
    r = client.post(
        "/api/hold-history/today-snapshot",
        json={"reason": payload, "record_type": "on_hold"},
        content_type="application/json",
    )
    assert r.status_code != 500, f"500 on reason={payload!r}"
    json.loads(r.data.decode("utf-8"))


# ---------------------------------------------------------------------------
# Hold Overview routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_hold_overview_rejects_malicious_filter(payload):
    client = _make_client()
    qs = _fuzz_query_string("workcenter_group", payload)
    r = client.get(f"/api/hold-overview/summary?{qs}")
    _assert_validation_error(r, payload, "/api/hold-overview/summary")


# ---------------------------------------------------------------------------
# Production History routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_production_history_rejects_malicious_date(payload):
    client = _make_client()
    body: dict
    if isinstance(payload, dict):
        body = payload
    else:
        body = {"start_date": _payload_to_str(payload), "end_date": "2026-01-07", "type": "daily"}
    r = client.post(
        "/api/production-history/query",
        json=body,
        content_type="application/json",
    )
    _assert_validation_error(r, payload, "/api/production-history/query")


# ---------------------------------------------------------------------------
# Resource History routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_resource_history_rejects_malicious_date(payload):
    client = _make_client()
    qs = _fuzz_query_string("start_date", payload, {"end_date": "2026-01-07"})
    r = client.get(f"/api/resource/history/view?{qs}")
    _assert_validation_error(r, payload, "/api/resource/history/view")


# ---------------------------------------------------------------------------
# Yield Alert routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_yield_alert_rejects_malicious_date(payload):
    client = _make_client()
    qs = _fuzz_query_string("start_date", payload, {"end_date": "2026-01-07"})
    r = client.get(f"/api/yield-alert/alerts?{qs}")
    _assert_validation_error(r, payload, "/api/yield-alert/alerts")


# ---------------------------------------------------------------------------
# Material Trace routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_material_trace_rejects_malicious_lot_id(payload):
    client = _make_client()
    if isinstance(payload, dict):
        body = payload
    else:
        body = {"lot_id": _payload_to_str(payload)}
    r = client.post(
        "/api/material-trace/query",
        json=body,
        content_type="application/json",
    )
    _assert_validation_error(r, payload, "/api/material-trace/query")


# ---------------------------------------------------------------------------
# Mid Section Defect routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_mid_section_defect_rejects_malicious_date(payload):
    client = _make_client()
    qs = _fuzz_query_string("start_date", payload, {"end_date": "2026-01-07"})
    r = client.get(f"/api/mid-section-defect/analysis?{qs}")
    _assert_validation_error(r, payload, "/api/mid-section-defect/analysis")


# ---------------------------------------------------------------------------
# WIP routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_wip_rejects_malicious_filter(payload):
    client = _make_client()
    qs = _fuzz_query_string("workcenter_group", payload)
    r = client.get(f"/api/wip/overview/summary?{qs}")
    _assert_validation_error(r, payload, "/api/wip/overview/summary")


# ---------------------------------------------------------------------------
# Production History — wildcard input fuzz
# (change `prod-history-first-tier-cache-filters`, PHF-02 / PHF-06)
# ---------------------------------------------------------------------------
#
# `validate_query_params` performs `pj_types` and date validation BEFORE
# parse_wildcard_tokens. So every wildcard fuzz request MUST carry the
# minimal valid pj_types + date envelope; otherwise the route would 400 on
# an unrelated field and we'd never exercise the wildcard path.
# ---------------------------------------------------------------------------

_PROD_HISTORY_QUERY_URL = "/api/production-history/query"


def _base_prod_history_body() -> dict:
    return {
        "pj_types": ["DEMO_TYPE"],
        "start_date": "2026-01-01",
        "end_date": "2026-01-07",
    }


def _assert_wildcard_field_in_error(response, field: str, payload) -> None:
    """Assert the error envelope mentions the offending wildcard field name.

    `parse_wildcard_tokens` raises WildcardValidationError whose message is
    prefixed with the field name (e.g. "mfg_orders 含有不允許的字元 …").
    The route layer surfaces it via error_response(VALIDATION_ERROR, str(exc)),
    so the field name MUST appear in error.message (data-shape §error).
    """
    body = response.get_json(silent=True) or {}
    err = body.get("error") or {}
    msg = str(err.get("message") or "")
    assert field in msg, (
        f"wildcard error envelope must mention field={field!r} for payload "
        f"{payload!r}; got message={msg!r} (body={body})"
    )


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
@pytest.mark.parametrize("token", WILDCARD_META_CHARS)
def test_main_query_wildcard_meta_char_rejection(field, token):
    """PHF-06: SQL meta-chars in any wildcard field MUST 400 with field context."""
    client = _make_client()
    body = _base_prod_history_body()
    body[field] = [token]
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    _assert_validation_error(r, token, _PROD_HISTORY_QUERY_URL)
    _assert_wildcard_field_in_error(r, field, token)


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
@pytest.mark.parametrize("ctrl", WILDCARD_CONTROL_CHARS)
def test_main_query_wildcard_param_control_char_rejection(field, ctrl):
    """PHF-06: control chars \\x00–\\x1f (except \\t \\n \\r) MUST 400."""
    client = _make_client()
    body = _base_prod_history_body()
    # Embed control char mid-token so the splitter can't drop it as whitespace.
    body[field] = [f"AB{ctrl}CD"]
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    _assert_validation_error(r, repr(ctrl), _PROD_HISTORY_QUERY_URL)
    _assert_wildcard_field_in_error(r, field, repr(ctrl))


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
@pytest.mark.parametrize("token", WILDCARD_GRAMMAR_INVALID)
def test_wildcard_multi_star_rejected(field, token):
    """PHF-02 grammar: multi-`*`, pure-`*`, single-char tokens MUST 400."""
    client = _make_client()
    body = _base_prod_history_body()
    body[field] = [token]
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    _assert_validation_error(r, token, _PROD_HISTORY_QUERY_URL)
    _assert_wildcard_field_in_error(r, field, token)


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
def test_main_query_oversized_wildcard_input_token_count_capped(field):
    """PHF-02 §5: per-field 100-token cap. 101 tokens MUST 400 mentioning 100."""
    client = _make_client()
    body = _base_prod_history_body()
    # 101 distinct valid exact tokens. parse_wildcard_tokens caps at 100.
    body[field] = [f"LO{idx:05d}" for idx in range(101)]
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    _assert_validation_error(r, f"101 tokens for {field}", _PROD_HISTORY_QUERY_URL)
    body_json = r.get_json(silent=True) or {}
    msg = str((body_json.get("error") or {}).get("message") or "")
    assert "100" in msg, (
        f"cap-violation error MUST mention 100; got message={msg!r}"
    )
    _assert_wildcard_field_in_error(r, field, "101 tokens")


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
def test_main_query_oversized_wildcard_input_single_huge_token_accepted(field):
    """No per-token length cap exists today (R1 recommendation in
    dependency-security-reviewer.yml). Document the actual behaviour: a
    10 KB single token survives the parser and reaches the route as a bind
    value. The route MAY then 400 for *unrelated* reasons (oracledb backend
    rejection in real prod), but MUST NOT 500. Body-bytes cap is 262144
    (MAX_JSON_BODY_BYTES default), so a 10 KB token is under the body cap.
    """
    client = _make_client()
    body = _base_prod_history_body()
    body[field] = ["A" * 10_000]
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    # The parser does NOT reject 10 KB tokens. We assert no 500; the route
    # may proceed to Oracle (returning 200/202/503 depending on test-mode
    # backend) but must not produce a wildcard-field VALIDATION_ERROR.
    _assert_not_500(r, "10KB single token", _PROD_HISTORY_QUERY_URL)
    _assert_valid_json(r, _PROD_HISTORY_QUERY_URL)
    # If the route does 400, it must NOT be because of the wildcard parser
    # (would require a per-token length cap, which is currently absent).
    if r.status_code in (400, 422):
        body_json = r.get_json(silent=True) or {}
        msg = str((body_json.get("error") or {}).get("message") or "")
        assert "萬用字元" not in msg or "上限" not in msg, (
            f"10KB single token must not be rejected with a per-token "
            f"length cap message; got: {msg!r}"
        )


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
def test_main_query_oversized_payload_body_bytes_capped(field):
    """MAX_JSON_BODY_BYTES = 262144 (~256 KB). 100 KB payload MUST NOT 500.

    Build a list of 100-byte tokens at the 100-token cap, plus a 90 KB
    junk filler — well under the 256 KB body cap but large enough to
    exercise the JSON parser path.
    """
    client = _make_client()
    body = _base_prod_history_body()
    body[field] = [f"L{i:099d}" for i in range(100)]  # 100 tokens × 100 bytes
    body["filler_for_payload_size"] = "X" * 90_000
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    _assert_not_500(r, "100KB payload", _PROD_HISTORY_QUERY_URL)
    _assert_valid_json(r, _PROD_HISTORY_QUERY_URL)


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
def test_wildcard_oracle_hostile_concat_passes_as_literal(field):
    """`||` and DBMS_*/UTL_* names are NOT rejected (defense-in-depth bind
    binding) — dependency-security-reviewer §3 confirms. Confirm empirically
    that the parser does not raise and the route does not 500.
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "src"))
    from mes_dashboard.core.request_validation import parse_wildcard_tokens

    # First — direct parser confidence: these reach a bound value, never raise.
    for token in ("AA||BB", "DBMS_OUTPUT.PUT_LINE", "UTL_HTTP.REQUEST"):
        tokens = parse_wildcard_tokens(field, [token])
        assert tokens and tokens[0].kind == "exact"
        assert tokens[0].bound_value == token

    # Second — route-level: must not 500 even when these reach the SQL layer.
    client = _make_client()
    body = _base_prod_history_body()
    body[field] = ["AA||BB", "DBMS_OUTPUT.PUT_LINE"]
    r = client.post(_PROD_HISTORY_QUERY_URL, json=body, content_type="application/json")
    _assert_not_500(r, "concat/DBMS literals", _PROD_HISTORY_QUERY_URL)
    _assert_valid_json(r, _PROD_HISTORY_QUERY_URL)


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
@pytest.mark.parametrize(
    "token,expected",
    [
        ("AB​CD", "pass"),    # ZWSP — literal
        ("AB‮CD", "pass"),    # RTL override — literal
        ("A１B", "pass"),       # full-width digit — literal
        ("AB\x00CD", "reject"),    # null byte — control char rejected
    ],
)
def test_wildcard_unicode_handling(field, token, expected):
    """Unicode invisibles pass through as literal binds (per
    dependency-security-reviewer §8); only the control-char class \\x00–\\x1f
    is rejected (PHF-06).
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "src"))
    from mes_dashboard.core.request_validation import parse_wildcard_tokens, WildcardValidationError

    if expected == "pass":
        tokens = parse_wildcard_tokens(field, [token])
        assert tokens and tokens[0].kind == "exact"
        assert tokens[0].bound_value == token  # passed through verbatim
    else:
        with pytest.raises(WildcardValidationError) as exc_info:
            parse_wildcard_tokens(field, [token])
        assert exc_info.value.field == field


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
def test_high_cardinality_lot_in_list_at_cap_accepted(field):
    """Submit exactly 100 tokens — the cap boundary. Parser MUST accept."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "src"))
    from mes_dashboard.core.request_validation import parse_wildcard_tokens

    tokens = parse_wildcard_tokens(field, [f"LO{i:05d}" for i in range(100)])
    assert len(tokens) == 100
    assert all(t.kind == "exact" for t in tokens)


@pytest.mark.parametrize("field", WILDCARD_FIELDS)
def test_wildcard_textarea_paste_with_carriage_returns(field):
    """PHF-02 §4: multi-line paste (CRLF + tabs + extra whitespace) is
    parsed deterministically — dedup + trim + normalize all separators.
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "src"))
    from mes_dashboard.core.request_validation import parse_wildcard_tokens

    raw = "MA\r\nMB\r\n  MC\r\n\tMA\r\n,MD"
    tokens = parse_wildcard_tokens(field, raw)
    # Dedup case-insensitive — duplicate MA should collapse.
    values = [t.bound_value for t in tokens]
    assert values == ["MA", "MB", "MC", "MD"], (
        f"CRLF/tab/comma paste did not normalise: got {values!r}"
    )
    assert all(t.kind == "exact" for t in tokens)
