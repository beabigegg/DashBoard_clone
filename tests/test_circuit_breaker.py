# -*- coding: utf-8 -*-
"""Unit tests for circuit breaker module."""

import os
import pytest
import time
from unittest.mock import patch

# Set circuit breaker enabled for tests
os.environ['CIRCUIT_BREAKER_ENABLED'] = 'true'

from mes_dashboard.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_database_circuit_breaker,
    get_circuit_breaker_status,
    CIRCUIT_BREAKER_ENABLED
)


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_allow_request_when_closed(self):
        """Requests are allowed when circuit is CLOSED."""
        cb = CircuitBreaker("test")
        assert cb.allow_request() is True

    def test_record_success_keeps_closed(self):
        """Recording success keeps circuit CLOSED."""
        cb = CircuitBreaker("test")
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_failure_threshold(self):
        """Circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=3,
            failure_rate_threshold=0.5,
            window_size=5
        )

        # Record enough failures to open
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_deny_request_when_open(self):
        """Requests are denied when circuit is OPEN."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4
        )

        # Force open
        for _ in range(4):
            cb.record_failure()

        assert cb.allow_request() is False

    def test_transition_to_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4,
            recovery_timeout=1  # 1 second for fast test
        )

        # Force open
        for _ in range(4):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Accessing state should transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_request(self):
        """Requests are allowed in HALF_OPEN state for testing."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4,
            recovery_timeout=1
        )

        # Force open
        for _ in range(4):
            cb.record_failure()

        # Wait for recovery timeout
        time.sleep(1.1)

        assert cb.allow_request() is True

    def test_success_in_half_open_closes(self):
        """Success in HALF_OPEN state closes the circuit."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4,
            recovery_timeout=1
        )

        # Force open
        for _ in range(4):
            cb.record_failure()

        # Wait for recovery timeout
        time.sleep(1.1)

        # Force HALF_OPEN check
        _ = cb.state

        # Record success
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens(self):
        """Failure in HALF_OPEN state reopens the circuit."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4,
            recovery_timeout=1
        )

        # Force open
        for _ in range(4):
            cb.record_failure()

        # Wait for recovery timeout
        time.sleep(1.1)

        # Force HALF_OPEN check
        _ = cb.state

        # Record failure
        cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_reset_clears_state(self):
        """Reset returns circuit to initial state."""
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4
        )

        # Force open
        for _ in range(4):
            cb.record_failure()

        cb.reset()

        assert cb.state == CircuitState.CLOSED
        status = cb.get_status()
        assert status.total_count == 0


class TestCircuitBreakerStatus:
    """Test circuit breaker status reporting."""

    def test_get_status_returns_correct_info(self):
        """Status includes all expected fields."""
        cb = CircuitBreaker("test")

        cb.record_success()
        cb.record_success()
        cb.record_failure()

        status = cb.get_status()

        assert status.state == "CLOSED"
        assert status.success_count == 2
        assert status.failure_count == 1
        assert status.total_count == 3
        assert 0.3 <= status.failure_rate <= 0.34

    def test_get_circuit_breaker_status_dict(self):
        """Global function returns status as dictionary."""
        status = get_circuit_breaker_status()

        assert "state" in status
        assert "failure_count" in status
        assert "success_count" in status
        assert "enabled" in status


class TestCircuitBreakerDisabled:
    """Test circuit breaker when disabled."""

    def test_allow_request_when_disabled(self):
        """Requests always allowed when circuit breaker is disabled."""
        with patch('mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED', False):
            cb = CircuitBreaker("test", failure_threshold=1, window_size=1)

            # Record failures
            cb.record_failure()
            cb.record_failure()

            # Should still allow (disabled)
            assert cb.allow_request() is True


class TestCircuitBreakerLogging:
    """Verify transition logs are emitted without lock-held I/O."""

    def test_transition_emits_open_log_and_preserves_state(self):
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4,
        )

        with patch.object(cb, "_emit_transition_log") as mock_emit:
            for _ in range(4):
                cb.record_failure()

        assert cb.state == CircuitState.OPEN
        mock_emit.assert_called_once()
        level, message = mock_emit.call_args.args
        assert level is not None
        assert "OPENED" in message

    def test_transition_logging_executes_outside_lock(self):
        cb = CircuitBreaker(
            "test",
            failure_threshold=2,
            failure_rate_threshold=0.5,
            window_size=4,
        )

        lock_states: list[bool] = []

        def _capture(_level, _message):
            lock_states.append(cb._lock.locked())

        with patch.object(cb, "_emit_transition_log", side_effect=_capture):
            for _ in range(4):
                cb.record_failure()

        assert lock_states
        assert all(not state for state in lock_states)
