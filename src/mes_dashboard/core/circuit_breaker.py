# -*- coding: utf-8 -*-
"""Circuit breaker implementation for database protection.

Prevents cascading failures by temporarily stopping requests to a failing service.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures exceeded threshold, requests are rejected immediately
- HALF_OPEN: Testing if service has recovered, limited requests allowed
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Optional

logger = logging.getLogger('mes_dashboard.circuit_breaker')

# ============================================================
# Configuration
# ============================================================

CIRCUIT_BREAKER_ENABLED = os.getenv(
    'CIRCUIT_BREAKER_ENABLED', 'false'
).lower() == 'true'

# Minimum failures before circuit can open
FAILURE_THRESHOLD = int(os.getenv('CIRCUIT_BREAKER_FAILURE_THRESHOLD', '5'))

# Failure rate threshold (0.0 - 1.0)
FAILURE_RATE_THRESHOLD = float(os.getenv('CIRCUIT_BREAKER_FAILURE_RATE', '0.5'))

# Seconds to wait in OPEN state before trying HALF_OPEN
RECOVERY_TIMEOUT = int(os.getenv('CIRCUIT_BREAKER_RECOVERY_TIMEOUT', '30'))

# Sliding window size for counting successes/failures
WINDOW_SIZE = int(os.getenv('CIRCUIT_BREAKER_WINDOW_SIZE', '10'))


# ============================================================
# Types
# ============================================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerStatus:
    """Circuit breaker status information."""
    state: str
    failure_count: int
    success_count: int
    total_count: int
    failure_rate: float
    last_failure_time: Optional[str]
    open_until: Optional[str]
    enabled: bool


# ============================================================
# Circuit Breaker Implementation
# ============================================================

class CircuitBreaker:
    """Circuit breaker for protecting database operations.

    Thread-safe implementation using a sliding window to track
    successes and failures.

    Usage:
        cb = CircuitBreaker("database")

        if not cb.allow_request():
            return error_response(CIRCUIT_BREAKER_OPEN, "Service degraded")

        try:
            result = execute_query()
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure()
            raise
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = FAILURE_THRESHOLD,
        failure_rate_threshold: float = FAILURE_RATE_THRESHOLD,
        recovery_timeout: int = RECOVERY_TIMEOUT,
        window_size: int = WINDOW_SIZE
    ):
        """Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker.
            failure_threshold: Minimum failures before opening.
            failure_rate_threshold: Failure rate to trigger opening (0.0-1.0).
            recovery_timeout: Seconds to wait before half-open.
            window_size: Size of sliding window for tracking.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_rate_threshold = failure_rate_threshold
        self.recovery_timeout = recovery_timeout
        self.window_size = window_size

        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()

        # Sliding window: True = success, False = failure
        self._results: Deque[bool] = deque(maxlen=window_size)

        self._last_failure_time: Optional[float] = None
        self._open_time: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, handling state transitions."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if we should transition to HALF_OPEN
                if self._open_time and time.time() - self._open_time >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if request should proceed, False if circuit is open.
        """
        if not CIRCUIT_BREAKER_ENABLED:
            return True

        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.HALF_OPEN:
            # Allow limited requests in half-open state
            return True
        else:  # OPEN
            return False

    def record_success(self) -> None:
        """Record a successful operation."""
        if not CIRCUIT_BREAKER_ENABLED:
            return

        with self._lock:
            self._results.append(True)

            if self._state == CircuitState.HALF_OPEN:
                # Success in half-open means we can close
                self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed operation."""
        if not CIRCUIT_BREAKER_ENABLED:
            return

        with self._lock:
            self._results.append(False)
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open means back to open
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                # Check if we should open
                self._check_and_open()

    def _check_and_open(self) -> None:
        """Check failure rate and open circuit if needed.

        Must be called with lock held.
        """
        if len(self._results) < self.failure_threshold:
            return

        failure_count = sum(1 for r in self._results if not r)
        failure_rate = failure_count / len(self._results)

        if (failure_count >= self.failure_threshold and
                failure_rate >= self.failure_rate_threshold):
            self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging.

        Must be called with lock held.
        """
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.OPEN:
            self._open_time = time.time()
            logger.warning(
                f"Circuit breaker '{self.name}' OPENED: "
                f"state {old_state.value} -> {new_state.value}, "
                f"failures: {sum(1 for r in self._results if not r)}/{len(self._results)}"
            )
        elif new_state == CircuitState.HALF_OPEN:
            logger.info(
                f"Circuit breaker '{self.name}' entering HALF_OPEN: "
                f"testing service recovery..."
            )
        elif new_state == CircuitState.CLOSED:
            self._open_time = None
            self._results.clear()
            logger.info(
                f"Circuit breaker '{self.name}' CLOSED: "
                f"service recovered"
            )

    def get_status(self) -> CircuitBreakerStatus:
        """Get current status information."""
        with self._lock:
            # Use _state directly to avoid deadlock (self.state would try to acquire lock again)
            current_state = self._state
            failure_count = sum(1 for r in self._results if not r)
            success_count = sum(1 for r in self._results if r)
            total = len(self._results)
            failure_rate = failure_count / total if total > 0 else 0.0

            open_until = None
            if current_state == CircuitState.OPEN and self._open_time:
                open_until_time = self._open_time + self.recovery_timeout
                from datetime import datetime
                open_until = datetime.fromtimestamp(open_until_time).isoformat()

            last_failure = None
            if self._last_failure_time:
                from datetime import datetime
                last_failure = datetime.fromtimestamp(self._last_failure_time).isoformat()

            return CircuitBreakerStatus(
                state=current_state.value,
                failure_count=failure_count,
                success_count=success_count,
                total_count=total,
                failure_rate=failure_rate,
                last_failure_time=last_failure,
                open_until=open_until,
                enabled=CIRCUIT_BREAKER_ENABLED
            )

    def reset(self) -> None:
        """Reset the circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._results.clear()
            self._last_failure_time = None
            self._open_time = None
            logger.info(f"Circuit breaker '{self.name}' reset")


# ============================================================
# Global Database Circuit Breaker
# ============================================================

_DATABASE_CIRCUIT_BREAKER: Optional[CircuitBreaker] = None


def get_database_circuit_breaker() -> CircuitBreaker:
    """Get or create the global database circuit breaker."""
    global _DATABASE_CIRCUIT_BREAKER
    if _DATABASE_CIRCUIT_BREAKER is None:
        _DATABASE_CIRCUIT_BREAKER = CircuitBreaker("database")
    return _DATABASE_CIRCUIT_BREAKER


def get_circuit_breaker_status() -> dict:
    """Get current circuit breaker status as a dictionary.

    Returns:
        Dictionary with circuit breaker status information.
    """
    cb = get_database_circuit_breaker()
    status = cb.get_status()
    return {
        "state": status.state,
        "failure_count": status.failure_count,
        "success_count": status.success_count,
        "total_count": status.total_count,
        "failure_rate": round(status.failure_rate, 2),
        "last_failure_time": status.last_failure_time,
        "open_until": status.open_until,
        "enabled": status.enabled
    }
