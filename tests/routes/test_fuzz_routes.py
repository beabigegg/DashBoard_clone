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
import unittest
from typing import Any

import pytest

# Add project root to path so we can import fuzz payloads
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routes._fuzz_payloads import MALICIOUS_INPUTS

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
