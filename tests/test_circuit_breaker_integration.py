# -*- coding: utf-8 -*-
"""Task 6.12 — Circuit breaker: repeated timeouts → OPEN → cooldown → HALF_OPEN.

Integration tests for CircuitBreaker / CircuitState from circuit_breaker.py.

Scenarios covered:
  1. Enough failures open the circuit
  2. An OPEN circuit rejects calls without executing the function
  3. Advancing time past reset_timeout moves the breaker to HALF_OPEN
  4. A success in HALF_OPEN closes the circuit
  5. A failure in HALF_OPEN re-opens the circuit
  6. Flask test client receives a 503 envelope when the circuit is OPEN
     (via the DatabaseCircuitOpenError → handle_circuit_open error handler)

The CircuitBreaker is used directly (not via the database layer) so tests have
no DB dependency.  CIRCUIT_BREAKER_ENABLED is patched to True for the duration
of each test because the default for non-production environments is False.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from mes_dashboard.core.circuit_breaker import (
    CIRCUIT_BREAKER_ENABLED,
    CircuitBreaker,
    CircuitState,
)
from mes_dashboard.core.response import CIRCUIT_BREAKER_OPEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cb(
    failure_threshold: int = 3,
    failure_rate_threshold: float = 0.5,
    recovery_timeout: int = 30,
    window_size: int = 6,
) -> CircuitBreaker:
    """Return a fresh CircuitBreaker with test-friendly thresholds."""
    return CircuitBreaker(
        name="test-db",
        failure_threshold=failure_threshold,
        failure_rate_threshold=failure_rate_threshold,
        recovery_timeout=recovery_timeout,
        window_size=window_size,
    )


def _trip(cb: CircuitBreaker, n: int = None) -> None:
    """Record enough failures to open the circuit.

    If n is None, records (failure_threshold) failures which is the minimum
    needed to satisfy both the count and rate thresholds when starting from a
    clean window.
    """
    count = n if n is not None else cb.failure_threshold
    for _ in range(count):
        cb.record_failure()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCircuitBreakerIntegration:
    """Circuit breaker state machine: CLOSED → OPEN → HALF_OPEN → CLOSED."""

    # ------------------------------------------------------------------
    # test_repeated_failures_open_circuit
    # ------------------------------------------------------------------
    def test_repeated_failures_open_circuit(self):
        """Recording failure_threshold failures must transition state to OPEN."""
        with patch("mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED", True):
            cb = _make_cb(failure_threshold=3, failure_rate_threshold=0.5, window_size=6)
            _trip(cb)
            assert cb.state == CircuitState.OPEN, (
                f"expected OPEN after {cb.failure_threshold} failures, got {cb.state}"
            )

    # ------------------------------------------------------------------
    # test_open_circuit_raises_immediately
    # ------------------------------------------------------------------
    def test_open_circuit_raises_immediately(self):
        """allow_request() must return False while the circuit is OPEN."""
        with patch("mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED", True):
            cb = _make_cb(failure_threshold=3, recovery_timeout=9999)
            _trip(cb)
            assert cb.state == CircuitState.OPEN

            fn_called = {"called": False}

            def protected_fn():
                fn_called["called"] = True
                return "result"

            # Mimic caller pattern: check allow_request before calling the function
            allowed = cb.allow_request()
            if allowed:
                protected_fn()

            assert not allowed, "allow_request() must return False when OPEN"
            assert not fn_called["called"], (
                "protected function must not execute when circuit is OPEN"
            )

    # ------------------------------------------------------------------
    # test_cooldown_transitions_to_half_open
    # ------------------------------------------------------------------
    def test_cooldown_transitions_to_half_open(self):
        """After recovery_timeout elapses, state must transition to HALF_OPEN."""
        with patch("mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED", True):
            cb = _make_cb(failure_threshold=3, recovery_timeout=1)
            _trip(cb)
            assert cb.state == CircuitState.OPEN

            # Wait for recovery_timeout to elapse
            time.sleep(1.1)

            # Accessing cb.state triggers the OPEN→HALF_OPEN transition
            state_after = cb.state
            assert state_after == CircuitState.HALF_OPEN, (
                f"expected HALF_OPEN after cooldown, got {state_after}"
            )

    # ------------------------------------------------------------------
    # test_half_open_success_closes_circuit
    # ------------------------------------------------------------------
    def test_half_open_success_closes_circuit(self):
        """A successful call during HALF_OPEN must transition state to CLOSED."""
        with patch("mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED", True):
            cb = _make_cb(failure_threshold=3, recovery_timeout=1)
            _trip(cb)

            # Wait for HALF_OPEN
            time.sleep(1.1)
            assert cb.state == CircuitState.HALF_OPEN

            cb.record_success()

            assert cb.state == CircuitState.CLOSED, (
                f"expected CLOSED after success in HALF_OPEN, got {cb.state}"
            )
            # allow_request must now be True
            assert cb.allow_request() is True

    # ------------------------------------------------------------------
    # test_half_open_failure_reopens_circuit
    # ------------------------------------------------------------------
    def test_half_open_failure_reopens_circuit(self):
        """A failed call during HALF_OPEN must return state to OPEN."""
        with patch("mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED", True):
            cb = _make_cb(failure_threshold=3, recovery_timeout=1)
            _trip(cb)

            time.sleep(1.1)
            assert cb.state == CircuitState.HALF_OPEN

            cb.record_failure()

            # Must go back to OPEN
            with cb._lock:
                raw_state = cb._state
            assert raw_state == CircuitState.OPEN, (
                f"expected OPEN after failure in HALF_OPEN, got {raw_state}"
            )
            assert cb.allow_request() is False

    # ------------------------------------------------------------------
    # test_circuit_breaker_envelope_on_open
    # ------------------------------------------------------------------
    def test_circuit_breaker_envelope_on_open(self, app):
        """Flask test client must receive 503 with CIRCUIT_BREAKER_OPEN envelope.

        Approach:
          - Register a minimal test blueprint that uses the database layer's
            circuit-breaker check pattern (allow_request → raise DatabaseCircuitOpenError).
          - The global error handler in app.py converts DatabaseCircuitOpenError
            → circuit_breaker_error() → 503 with error.code=CIRCUIT_BREAKER_OPEN.
        """
        from mes_dashboard.core.database import DatabaseCircuitOpenError

        # Register a one-shot test route on the existing app
        route_path = "/api/test/cb-open-probe"

        # Avoid duplicate route registration across test parameterisation
        existing_rules = {rule.rule for rule in app.url_map.iter_rules()}
        if route_path not in existing_rules:
            @app.route(route_path, methods=["GET"])
            def _cb_open_probe():
                raise DatabaseCircuitOpenError(
                    "circuit breaker open (test)", retry_after_seconds=30
                )

        with app.test_client() as client:
            rv = client.get(route_path)

        assert rv.status_code == 503, (
            f"expected HTTP 503 from circuit breaker open, got {rv.status_code}"
        )
        body = rv.get_json()
        assert body is not None, "503 response must be JSON"
        assert body.get("success") is False
        error = body.get("error", {})
        assert error.get("code") == CIRCUIT_BREAKER_OPEN, (
            f"expected error.code={CIRCUIT_BREAKER_OPEN!r}, got {error.get('code')!r}"
        )
