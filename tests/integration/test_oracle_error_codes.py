# -*- coding: utf-8 -*-
"""
Integration tests: Oracle ORA-* error code handling.

Injects exceptions with ORA-* messages and verifies:
  - _extract_ora_code parses the code correctly
  - Response envelope error code maps correctly
  - Circuit breaker failure counter increments (when enabled)
  - Retry-After header present for circuit-breaker-open responses

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_oracle_error_codes.py -v
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ora_error(ora_code: str, message: str = "") -> Exception:
    """Return an exception whose str() includes the ORA-NNNNN code.

    We use a plain RuntimeError with the ORA code embedded in the message.
    This is sufficient because _extract_ora_code() only parses str(exc).
    """
    text = f"ORA-{ora_code}: {message or 'mock Oracle error'}"
    return RuntimeError(text)


def _reset_circuit_breaker() -> None:
    """Reset the singleton circuit breaker to closed state between tests."""
    try:
        from mes_dashboard.core.circuit_breaker import get_database_circuit_breaker, CircuitState
        cb = get_database_circuit_breaker()
        with cb._lock:
            cb._state = CircuitState.CLOSED
            cb._results.clear()
            cb._last_failure_time = 0.0
    except Exception:
        pass


def _make_minimal_app():
    """Create a minimal Flask app with test routes that simulate ORA-* errors."""
    from flask import Flask
    from mes_dashboard.core import response as resp_module

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/test-ora-01017")
    def test_ora_01017():
        exc = _make_ora_error("01017", "invalid username/password")
        return resp_module.db_connection_error(details=str(exc))

    @app.route("/test-ora-12514")
    def test_ora_12514():
        exc = _make_ora_error("12514", "TNS: listener does not know of service")
        return resp_module.db_connection_error(details=str(exc))

    return app


# ---------------------------------------------------------------------------
# ORA code extraction
# ---------------------------------------------------------------------------

class TestOraCodeExtraction:
    """Verify _extract_ora_code parses ORA-NNNNN from exception strings."""

    def test_extracts_01017(self):
        from mes_dashboard.core.database import _extract_ora_code
        exc = _make_ora_error("01017", "invalid username/password")
        assert _extract_ora_code(exc) == "01017"

    def test_extracts_12514(self):
        from mes_dashboard.core.database import _extract_ora_code
        exc = _make_ora_error("12514", "TNS: no listener")
        assert _extract_ora_code(exc) == "12514"

    def test_extracts_01555(self):
        from mes_dashboard.core.database import _extract_ora_code
        exc = _make_ora_error("01555", "snapshot too old")
        assert _extract_ora_code(exc) == "01555"

    def test_returns_unknown_for_non_ora_error(self):
        from mes_dashboard.core.database import _extract_ora_code
        assert _extract_ora_code(RuntimeError("no ora code here")) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Circuit breaker failure counting (forced enabled via env patch)
# ---------------------------------------------------------------------------

class TestCircuitBreakerFailureCount:
    """Circuit breaker must increment failure count when CIRCUIT_BREAKER_ENABLED=true."""

    def test_record_failure_increments_counter(self, monkeypatch):
        monkeypatch.setenv("CIRCUIT_BREAKER_ENABLED", "true")
        _reset_circuit_breaker()

        import mes_dashboard.core.circuit_breaker as cb_mod
        original_enabled = cb_mod.CIRCUIT_BREAKER_ENABLED
        monkeypatch.setattr(cb_mod, "CIRCUIT_BREAKER_ENABLED", True)

        try:
            cb = cb_mod.get_database_circuit_breaker()
            # Reset the specific instance too
            with cb._lock:
                cb._results.clear()

            before = list(cb._results).count(False)
            cb.record_failure()
            after = list(cb._results).count(False)
            assert after == before + 1
        finally:
            monkeypatch.setattr(cb_mod, "CIRCUIT_BREAKER_ENABLED", original_enabled)

    def test_multiple_failures_approach_threshold(self, monkeypatch):
        import mes_dashboard.core.circuit_breaker as cb_mod
        monkeypatch.setattr(cb_mod, "CIRCUIT_BREAKER_ENABLED", True)
        cb = cb_mod.get_database_circuit_breaker()
        with cb._lock:
            cb._results.clear()

        for _ in range(3):
            cb.record_failure()

        assert list(cb._results).count(False) == 3
        monkeypatch.setattr(cb_mod, "CIRCUIT_BREAKER_ENABLED", False)


# ---------------------------------------------------------------------------
# Response envelope error codes
# ---------------------------------------------------------------------------

class TestResponseEnvelopeErrorCodes:
    """API response envelopes must carry correct error codes for DB failures."""

    def test_db_connection_error_returns_503_with_correct_code(self):
        from mes_dashboard.core import response as resp_module
        app = _make_minimal_app()
        with app.test_client() as client:
            r = client.get("/test-ora-01017")
        assert r.status_code == 503
        data = r.get_json()
        assert data["success"] is False
        assert data["error"]["code"] == resp_module.DB_CONNECTION_FAILED

    def test_db_connection_error_12514_returns_503(self):
        from mes_dashboard.core import response as resp_module
        app = _make_minimal_app()
        with app.test_client() as client:
            r = client.get("/test-ora-12514")
        assert r.status_code == 503
        data = r.get_json()
        assert data["success"] is False
        assert data["error"]["code"] == resp_module.DB_CONNECTION_FAILED

    def test_circuit_breaker_open_includes_retry_after_header(self):
        from mes_dashboard.core import response as resp_module
        app = _make_minimal_app()
        with app.app_context():
            resp_obj, status = resp_module.circuit_breaker_error(retry_after_seconds=30)
        assert status == 503
        assert resp_obj.headers.get("Retry-After") == "30"

    def test_error_envelope_is_valid_json_structure(self):
        app = _make_minimal_app()
        with app.test_client() as client:
            r = client.get("/test-ora-01017")
        data = r.get_json()
        assert "success" in data
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "meta" in data
