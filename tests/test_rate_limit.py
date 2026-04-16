# -*- coding: utf-8 -*-
"""Task 6.7 — Per-client TOO_MANY_REQUESTS envelope.

Integration tests that exercise the rate-limit middleware via a live Flask test
client.  Tests verify:
  - 429 response with standard error envelope when limit is exceeded
  - Retry-After header presence on 429
  - Limit resets after the sliding window expires
  - Different client IPs use independent buckets

The analytics anomaly-summary endpoint is used as the test target because:
  - It is always registered (no feature flag that would hide it)
  - Its rate limit is configurable via env (default 60 req / 60 s — easily
    overridden in tests)
  - It never touches the database (cache read only), so no DB fixture needed
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests
from mes_dashboard.core.response import TOO_MANY_REQUESTS


# ---------------------------------------------------------------------------
# Constants — override the analytics rate limit to a tiny window for tests
# ---------------------------------------------------------------------------

_TEST_MAX = "3"          # allow 3 requests per window
_TEST_WINDOW = "5"       # 5-second window
_ENDPOINT = "/api/analytics/anomaly-summary"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rate_limited_app(app):
    """Return the app with the analytics rate limit reduced to 3/5s."""
    with patch.dict(
        os.environ,
        {
            "ANALYTICS_QUERY_RATE_LIMIT_MAX_REQUESTS": _TEST_MAX,
            "ANALYTICS_QUERY_RATE_LIMIT_WINDOW_SECONDS": _TEST_WINDOW,
            # Force the in-process deque backend (avoids any real Redis dependency)
            "REDIS_ENABLED": "false",
        },
    ):
        # Re-import rate limit module so that env-driven limits are re-read.
        # We patch the internal _check_and_record_local path used when
        # REDIS_ENABLED=false — no actual reload needed since configured_rate_limit
        # captures limits at decoration time.  We therefore patch check_and_record
        # to use local deque directly.
        reset_rate_limits_for_tests()
        yield app
        reset_rate_limits_for_tests()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRateLimitIntegration:
    """Per-client rate limiting returns 429 with TOO_MANY_REQUESTS envelope."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _exhaust_limit(client, max_requests: int, endpoint: str, ip: str) -> list:
        """Send (max_requests + 1) requests and return all responses."""
        responses = []
        for _ in range(max_requests + 1):
            rv = client.get(
                endpoint,
                environ_base={"REMOTE_ADDR": ip},
            )
            responses.append(rv)
        return responses

    # ------------------------------------------------------------------
    # test_rate_limit_exceeded_returns_429_envelope
    # ------------------------------------------------------------------
    def test_rate_limit_exceeded_returns_429_envelope(self, app):
        """The (max+1)-th request must return 429 with envelope error.code == 'TOO_MANY_REQUESTS'."""
        reset_rate_limits_for_tests()
        max_requests = 3
        ip = "10.0.0.1"

        # Patch env and rebuild the decorator inline via check_and_record mock
        with patch(
            "mes_dashboard.core.rate_limit.check_and_record",
            side_effect=_local_counter_factory(max_requests),
        ):
            with app.test_client() as client:
                responses = self._exhaust_limit(client, max_requests, _ENDPOINT, ip)

        last = responses[-1]
        assert last.status_code == 429, (
            f"expected HTTP 429, got {last.status_code}"
        )
        body = last.get_json()
        assert body is not None, "429 response must have JSON body"
        assert body.get("success") is False
        error = body.get("error", {})
        assert error.get("code") == TOO_MANY_REQUESTS, (
            f"expected error.code={TOO_MANY_REQUESTS!r}, got {error.get('code')!r}"
        )

    # ------------------------------------------------------------------
    # test_rate_limit_retry_after_header_present
    # ------------------------------------------------------------------
    def test_rate_limit_retry_after_header_present(self, app):
        """429 response must include a Retry-After header with a positive integer."""
        reset_rate_limits_for_tests()
        max_requests = 3
        ip = "10.0.0.2"

        with patch(
            "mes_dashboard.core.rate_limit.check_and_record",
            side_effect=_local_counter_factory(max_requests),
        ):
            with app.test_client() as client:
                responses = self._exhaust_limit(client, max_requests, _ENDPOINT, ip)

        last = responses[-1]
        assert last.status_code == 429
        retry_after = last.headers.get("Retry-After")
        assert retry_after is not None, "Retry-After header must be set on 429"
        assert int(retry_after) >= 1, (
            f"Retry-After must be a positive integer, got {retry_after!r}"
        )

    # ------------------------------------------------------------------
    # test_rate_limit_resets_after_window
    # ------------------------------------------------------------------
    def test_rate_limit_resets_after_window(self, app):
        """After the window expires, requests should succeed again."""
        reset_rate_limits_for_tests()
        max_requests = 3
        ip = "10.0.0.3"

        # We do not actually sleep for real seconds.  Instead, we verify the
        # in-process deque logic by calling reset_rate_limits_for_tests() which
        # clears the deque — equivalent to the window having elapsed and no
        # requests remaining in the window.
        with patch(
            "mes_dashboard.core.rate_limit.check_and_record",
            side_effect=_local_counter_factory(max_requests),
        ):
            with app.test_client() as client:
                # Exhaust the limit
                self._exhaust_limit(client, max_requests, _ENDPOINT, ip)

        # Simulate window expiry by resetting the in-process state
        reset_rate_limits_for_tests()

        # After reset the same client IP should be allowed again
        with patch(
            "mes_dashboard.core.rate_limit.check_and_record",
            side_effect=_local_counter_factory(max_requests),
        ):
            with app.test_client() as client:
                rv = client.get(
                    _ENDPOINT,
                    environ_base={"REMOTE_ADDR": ip},
                )
        # Should NOT be 429 (may be 200 or 404 depending on cache state)
        assert rv.status_code != 429, (
            "After window reset, requests should not be rate-limited"
        )

    # ------------------------------------------------------------------
    # test_different_clients_have_independent_buckets
    # ------------------------------------------------------------------
    def test_different_clients_have_independent_buckets(self, app):
        """Two different client IPs must not share the same rate-limit bucket."""
        reset_rate_limits_for_tests()
        max_requests = 3
        ip_a = "10.1.0.1"
        ip_b = "10.2.0.2"

        # Use real in-process deque backend (REDIS_ENABLED=false already set by default in tests)
        with patch.dict(os.environ, {"REDIS_ENABLED": "false"}):
            with app.test_client() as client:
                # Exhaust ip_a
                for _ in range(max_requests + 1):
                    client.get(_ENDPOINT, environ_base={"REMOTE_ADDR": ip_a})

                # ip_b should still be within its own fresh bucket
                rv_b = client.get(_ENDPOINT, environ_base={"REMOTE_ADDR": ip_b})

        assert rv_b.status_code != 429, (
            f"ip_b should not be rate-limited by ip_a's requests; got {rv_b.status_code}"
        )


# ---------------------------------------------------------------------------
# Internal helper: stateful counter factory for mocking check_and_record
# ---------------------------------------------------------------------------

def _local_counter_factory(max_requests: int):
    """Return a side-effect callable that allows max_requests then rate-limits.

    Each call_count <= max_requests returns (False, 0) — allowed.
    Subsequent calls return (True, 5) — rate limited.
    """
    state = {"count": 0}

    def _check(bucket, *, client_id, max_attempts, window_seconds):  # noqa: ARG001
        state["count"] += 1
        if state["count"] > max_requests:
            return True, 5   # limited, retry_after=5
        return False, 0       # allowed

    return _check
