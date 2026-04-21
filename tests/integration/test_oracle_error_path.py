# -*- coding: utf-8 -*-
"""
Integration tests: Oracle error handling through the REAL Flask request path.

Sibling ``test_oracle_error_codes.py`` covers the helpers (``_extract_ora_code``,
response helpers, circuit-breaker counter) using a synthetic minimal Flask
app.  That is good for helper-level correctness but does NOT prove that a
real route → service → Oracle path actually converts a thrown exception into
the spec-required envelope.

This file closes that gap:

- Build a real ``create_app('testing')`` + test client via the project-wide
  ``app`` / ``client`` fixtures (tests/conftest.py).
- Exercise real blueprints (resource-history, query-tool).
- Monkeypatch the service call **as imported by the route module** to raise
  the target exception — service-boundary patching, no Oracle required.
- Assert on HTTP status, envelope, ``error.code``, and ``Retry-After``
  header.

Findings surfaced by this file:

1. ``@app.errorhandler(DatabasePoolExhaustedError)`` and
   ``@app.errorhandler(DatabaseCircuitOpenError)`` in
   ``src/mes_dashboard/app.py:1351-1367`` DO reach a route that does not use
   ``@map_service_errors`` — proving the handlers are wired.  Covered by
   ``TestDegradedContractViaResourceHistoryRoute``.

2. Query-tool routes now propagate ``DatabaseDegradedError`` subclasses so
   app-level handlers return degraded envelopes (503 + code + Retry-After).
   Covered by ``TestMapServiceErrorsPropagatesDegradedErrors``.

3. ORA-coded Oracle driver errors are mapped at the app boundary:
   ORA-01017/12514 map to connection-failure contracts, ORA-01555 maps to
   timeout, and unknown ORA codes remain database-originated (non-generic).

Run with::

    conda run -n mes-dashboard pytest --run-integration-real \\
        tests/integration/test_oracle_error_path.py -v
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ora_error(code: str, message: str = "") -> Exception:
    """Build an ORA-coded exception matching what oracledb would raise.

    Falls back to RuntimeError if oracledb is unavailable — extraction is
    string-based (regex ``ORA-(\\d+)``) so either shape works.
    """
    text = f"ORA-{code}: {message or 'injected mock'}"
    try:
        import oracledb  # type: ignore
        return oracledb.DatabaseError(text)
    except Exception:
        return RuntimeError(text)


def _valid_lot_equipment_body():
    """Minimum body that satisfies the pre-service validators in the route."""
    return {
        "input_type": "lot_id",
        "values": ["LOT-TEST-001"],
        "workcenter_groups": ["test-group"],
    }


def _assert_503_envelope(resp, expected_code: str, expected_retry_after: int):
    assert resp.status_code == 503, (
        f"expected 503, got {resp.status_code}: {resp.data[:500]!r}"
    )
    body = resp.get_json(silent=True) or {}
    assert body.get("success") is False, f"envelope missing success=False: {body!r}"
    err = body.get("error") or {}
    assert err.get("code") == expected_code, (
        f"expected error.code={expected_code!r}, got {err.get('code')!r}: {body!r}"
    )
    retry_after = resp.headers.get("Retry-After")
    assert retry_after == str(expected_retry_after), (
        f"expected Retry-After={expected_retry_after!s}, got {retry_after!r}"
    )


def _assert_500_generic(resp, hint: str):
    """Pin the current fallthrough behaviour: generic 500 / INTERNAL_ERROR.

    ``hint`` is a human-readable reason included in the assertion message,
    so when a follow-up change fixes the gap and this test starts failing
    the reader immediately knows which gap was closed.
    """
    assert resp.status_code == 500, (
        f"expected 500 (pinning), got {resp.status_code}: {resp.data[:500]!r}. "
        f"Gap under test: {hint}"
    )
    body = resp.get_json(silent=True) or {}
    assert body.get("success") is False, f"envelope missing success=False: {body!r}"
    err = body.get("error") or {}
    assert err.get("code") == "INTERNAL_ERROR", (
        f"expected error.code=INTERNAL_ERROR (pinning), got {err.get('code')!r}. "
        f"If a proper mapping landed, rewrite this test to assert the new "
        f"envelope. Gap under test: {hint}"
    )


# ---------------------------------------------------------------------------
# Wired degraded-response handlers (via a route without @map_service_errors)
# ---------------------------------------------------------------------------

class TestDegradedContractViaResourceHistoryRoute:
    """Prove ``@app.errorhandler(DatabasePoolExhaustedError)`` and
    ``@app.errorhandler(DatabaseCircuitOpenError)`` still reach the response
    layer when a route does NOT swallow them.

    ``/api/resource/history/options`` is the chosen probe because its handler
    has no decorator that catches ``Exception``; the raised error propagates
    directly to the Flask app-level error handlers.
    """

    def test_pool_exhausted_returns_503_with_retry_after(self, client, monkeypatch):
        from mes_dashboard.core.database import DatabasePoolExhaustedError
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise DatabasePoolExhaustedError(
                "pool empty (injected)", retry_after_seconds=5
            )

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        # Bypass the route's pre-service cache read so the patched service
        # is actually invoked.
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        _assert_503_envelope(resp, expected_code="DB_POOL_EXHAUSTED", expected_retry_after=5)

    def test_circuit_open_returns_503_with_retry_after(self, client, monkeypatch):
        from mes_dashboard.core.database import DatabaseCircuitOpenError
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise DatabaseCircuitOpenError(
                "circuit open (injected)", retry_after_seconds=30
            )

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        _assert_503_envelope(resp, expected_code="CIRCUIT_BREAKER_OPEN", expected_retry_after=30)


# ---------------------------------------------------------------------------
# Contract tests — query-tool routes propagate degraded errors
# ---------------------------------------------------------------------------

class TestMapServiceErrorsPropagatesDegradedErrors:
    """Query-tool routes should let degraded DB exceptions reach app handlers."""

    def test_pool_exhausted_propagates_to_503(self, client, monkeypatch):
        from mes_dashboard.core.database import DatabasePoolExhaustedError
        from mes_dashboard.routes import query_tool_routes as qt_routes

        def _raise(*args, **kwargs):
            raise DatabasePoolExhaustedError(
                "pool empty (injected)", retry_after_seconds=5
            )

        monkeypatch.setattr(qt_routes, "resolve_lot_equipment", _raise)

        resp = client.post(
            "/api/query-tool/lot-equipment-lookup",
            json=_valid_lot_equipment_body(),
        )
        _assert_503_envelope(resp, expected_code="DB_POOL_EXHAUSTED", expected_retry_after=5)

    def test_circuit_open_propagates_to_503(self, client, monkeypatch):
        from mes_dashboard.core.database import DatabaseCircuitOpenError
        from mes_dashboard.routes import query_tool_routes as qt_routes

        def _raise(*args, **kwargs):
            raise DatabaseCircuitOpenError(
                "circuit open (injected)", retry_after_seconds=30
            )

        monkeypatch.setattr(qt_routes, "resolve_lot_equipment", _raise)

        resp = client.post(
            "/api/query-tool/lot-equipment-lookup",
            json=_valid_lot_equipment_body(),
        )
        _assert_503_envelope(resp, expected_code="CIRCUIT_BREAKER_OPEN", expected_retry_after=30)


# ---------------------------------------------------------------------------
# Contract tests — ORA-* errors map to stable DB contracts
# ---------------------------------------------------------------------------

class TestMappedOraCodesAtAppBoundary:
    """Resource-history route should apply ORA-code-aware app-level mapping."""

    def test_ora_01017_invalid_credential_returns_connection_failed(self, client, monkeypatch):
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise _ora_error("01017", "invalid username/password")

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        body = resp.get_json(silent=True) or {}
        err = body.get("error") or {}
        assert resp.status_code == 503
        assert err.get("code") == "DB_CONNECTION_FAILED"
        assert resp.headers.get("Retry-After") is None

    def test_ora_12514_listener_returns_retryable_connection_failed(self, client, monkeypatch):
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise _ora_error("12514", "TNS: listener does not know of service")

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        body = resp.get_json(silent=True) or {}
        err = body.get("error") or {}
        assert resp.status_code == 503
        assert err.get("code") == "DB_CONNECTION_FAILED"
        assert resp.headers.get("Retry-After") == "30"

    def test_ora_01555_snapshot_returns_db_query_timeout(self, client, monkeypatch):
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise _ora_error("01555", "snapshot too old")

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        body = resp.get_json(silent=True) or {}
        err = body.get("error") or {}
        assert resp.status_code == 504
        assert err.get("code") == "DB_QUERY_TIMEOUT"
        assert resp.headers.get("Retry-After") is None

    def test_ora_00028_session_kill_returns_retryable_connection_failed(self, client, monkeypatch):
        """ORA-00028 (session killed by DBA) maps to DB_CONNECTION_FAILED 503 + Retry-After.

        Session kill is a connection-layer event; the client should retry rather
        than treating it as a query-logic failure (500).

        Mutation check: removing "00028" from retryable_connection_codes in app.py
        causes this to return 500 DB_QUERY_ERROR instead of 503 DB_CONNECTION_FAILED.
        """
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise _ora_error("00028", "your session has been killed")

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        body = resp.get_json(silent=True) or {}
        err = body.get("error") or {}
        assert resp.status_code == 503
        assert err.get("code") == "DB_CONNECTION_FAILED"
        assert resp.headers.get("Retry-After") == "30"

    def test_unknown_ora_returns_db_query_error_not_internal_error(self, client, monkeypatch):
        from mes_dashboard.routes import resource_history_routes as rh_routes

        def _raise(*args, **kwargs):
            raise _ora_error("29999", "unexpected driver condition")

        monkeypatch.setattr(rh_routes, "get_filter_options", _raise)
        monkeypatch.setattr(rh_routes, "cache_get", lambda *a, **k: None)

        resp = client.get("/api/resource/history/options")
        body = resp.get_json(silent=True) or {}
        err = body.get("error") or {}
        assert resp.status_code == 500
        assert err.get("code") == "DB_QUERY_ERROR"
