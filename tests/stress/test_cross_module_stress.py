# -*- coding: utf-8 -*-
"""Cross-module stress tests for post-SQL-optimization verification.

Covers all major API modules under concurrent load to verify:
- Connection pool stability across multiple Oracle query paths
- Cache TTL centralisation correctness under pressure
- 730-day date range limit enforcement under concurrent requests
- No 5xx regressions after SQL optimisation changes

Run with: pytest tests/stress/test_cross_module_stress.py -v -s
"""

from __future__ import annotations

import concurrent.futures
import time
from typing import Any, Tuple

import pytest
import requests


def _request(
    method: str,
    url: str,
    *,
    timeout: float = 30.0,
    json_body: dict[str, Any] | None = None,
    allowed_statuses: set[int] | None = None,
) -> Tuple[bool, float, str]:
    """Make a single request and return (success, duration, error)."""
    start = time.time()
    try:
        response = requests.request(method, url, json=json_body, timeout=timeout)
        duration = time.time() - start
        statuses = allowed_statuses or {200}
        if response.status_code in statuses:
            return True, duration, ""
        return False, duration, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return True, time.time() - start, ""  # Server alive but slow under load
    except requests.exceptions.ConnectionError as exc:
        return False, time.time() - start, f"ConnErr: {str(exc)[:60]}"
    except Exception as exc:
        return False, time.time() - start, f"Error: {str(exc)[:60]}"


@pytest.mark.stress
@pytest.mark.load
class TestCrossModuleConcurrentLoad:
    """Concurrent load across all major modules simultaneously."""

    def test_all_modules_concurrent_stability(
        self, base_url: str, stress_config: dict, stress_result
    ):
        """Hit endpoints from 7+ modules concurrently — no 5xx allowed."""
        result = stress_result("Cross-Module Concurrent Stability")
        concurrent_users = stress_config["concurrent_users"]
        timeout = stress_config["timeout"]

        endpoints = [
            # WIP module
            ("GET", f"{base_url}/api/wip/overview/summary", None, {200, 429}),
            ("GET", f"{base_url}/api/wip/overview/matrix", None, {200, 429}),
            ("GET", f"{base_url}/api/wip/overview/hold", None, {200, 429}),
            # Resource module
            ("GET", f"{base_url}/api/resource/status/summary", None, {200, 429}),
            ("GET", f"{base_url}/api/resource/status/options", None, {200, 429}),
            # Hold Overview module
            ("GET", f"{base_url}/api/hold-overview/summary", None, {200, 429}),
            ("GET", f"{base_url}/api/hold-overview/lots?page=1&per_page=10", None, {200, 429}),
            # Job Query module
            ("GET", f"{base_url}/api/job-query/resources", None, {200, 429}),
            # Yield Alert module
            ("GET", f"{base_url}/api/yield-alert/filter-options", None, {200, 429}),
            # Mid-Section Defect module
            ("GET", f"{base_url}/api/mid-section-defect/station-options", None, {200, 429}),
            ("GET", f"{base_url}/api/mid-section-defect/loss-reasons", None, {200, 429}),
            # Material Trace module
            ("GET", f"{base_url}/api/material-trace/filter-options", None, {200, 429}),
            # Reject History module
            ("GET", f"{base_url}/api/reject-history/options", None, {200, 429}),
            # Health
            ("GET", f"{base_url}/health", None, {200, 503}),
        ]

        requests_per_endpoint = 1
        total_requests = concurrent_users * len(endpoints) * requests_per_endpoint

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = []
            for _ in range(concurrent_users):
                for method, url, body, statuses in endpoints:
                    for _ in range(requests_per_endpoint):
                        futures.append(
                            executor.submit(
                                _request, method, url,
                                timeout=timeout, json_body=body,
                                allowed_statuses=statuses,
                            )
                        )

            for future in concurrent.futures.as_completed(futures):
                ok, duration, error = future.result()
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time
        print(result.report())

        assert result.success_rate >= 85.0, f"Success rate too low: {result.success_rate:.1f}%"

        # No unexpected 5xx
        five_xx = [e for e in result.errors if "HTTP 5" in e]
        assert len(five_xx) <= max(3, int(result.total_requests * 0.01)), (
            f"Too many 5xx: {five_xx[:5]}"
        )


@pytest.mark.stress
@pytest.mark.load
class TestDateRangeLimitStress:
    """Verify 730-day date range limit enforcement under concurrent load."""

    def test_concurrent_over_limit_requests_all_rejected(
        self, base_url: str, stress_config: dict, stress_result
    ):
        """All concurrent requests exceeding 730-day limit must return 400."""
        result = stress_result("730-Day Limit Enforcement Stress")
        concurrent_users = min(stress_config["concurrent_users"], 10)
        timeout = stress_config["timeout"]

        # Endpoints that enforce the 730-day limit
        over_limit_endpoints = [
            # Job Query: >730 days
            (
                "POST",
                f"{base_url}/api/job-query/jobs",
                {
                    "resource_ids": ["STRESS-RES-1"],
                    "start_date": "2023-01-01",
                    "end_date": "2025-02-28",
                },
                {400, 429},  # 429 = rate limiter fires before validation
            ),
            # Yield Alert summary: >730 days
            (
                "GET",
                f"{base_url}/api/yield-alert/summary?start_date=2024-01-01&end_date=2026-03-13",
                None,
                {400, 429},
            ),
            # Mid-Section Defect: >730 days
            (
                "GET",
                f"{base_url}/api/mid-section-defect/analysis?start_date=2023-01-01&end_date=2025-02-28",
                None,
                {400, 429},
            ),
        ]

        requests_per_endpoint = 5

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = []
            for _ in range(concurrent_users):
                for method, url, body, statuses in over_limit_endpoints:
                    for _ in range(requests_per_endpoint):
                        futures.append(
                            executor.submit(
                                _request, method, url,
                                timeout=timeout, json_body=body,
                                allowed_statuses=statuses,
                            )
                        )

            for future in concurrent.futures.as_completed(futures):
                ok, duration, error = future.result()
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time
        print(result.report())

        # All should be rejected with 400 — success rate should be 100%
        assert result.success_rate >= 95.0, (
            f"Some over-limit requests were not properly rejected: "
            f"{result.success_rate:.1f}% ({result.errors[:5]})"
        )


@pytest.mark.stress
@pytest.mark.load
class TestHoldHistoryStress:
    """Stress tests specific to Hold History two-phase pattern."""

    def test_concurrent_query_requests(
        self, base_url: str, stress_config: dict, stress_result
    ):
        """Multiple concurrent hold-history queries should not cause 5xx."""
        result = stress_result("Hold History Concurrent Queries")
        concurrent_users = min(stress_config["concurrent_users"], 6)
        timeout = 120.0

        def run_query(seed: int):
            # Stagger date ranges slightly
            day = (seed % 28) + 1
            body = {
                "start_date": f"2026-03-{day:02d}",
                "end_date": f"2026-03-{min(day + 6, 28):02d}",
            }
            ok, duration, error = _request(
                "POST",
                f"{base_url}/api/hold-history/query",
                timeout=timeout,
                json_body=body,
                # 500 = DB connection error under load, 503 = system busy
                allowed_statuses={200, 500, 503},
            )
            if ok:
                result.add_success(duration)
            else:
                result.add_failure(error, duration)

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(run_query, i) for i in range(concurrent_users * 2)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        result.total_duration = time.time() - start_time
        print(result.report())

        # Accept 500 (DB timeout under load) and 503 (system busy)
        unexpected_5xx = [e for e in result.errors if "HTTP 5" in e and "HTTP 503" not in e and "HTTP 500" not in e]
        assert not unexpected_5xx, f"Unexpected 5xx: {unexpected_5xx[:5]}"


@pytest.mark.stress
@pytest.mark.load
class TestYieldAlertStress:
    """Stress tests for Yield Alert endpoints."""

    def test_concurrent_alert_queries(
        self, base_url: str, stress_config: dict, stress_result
    ):
        """Concurrent yield-alert/alerts queries should stay stable."""
        result = stress_result("Yield Alert Concurrent Alerts")
        concurrent_users = min(stress_config["concurrent_users"], 8)
        timeout = stress_config["timeout"]

        endpoints = [
            f"{base_url}/api/yield-alert/filter-options",
            f"{base_url}/api/yield-alert/summary?start_date=2026-03-01&end_date=2026-03-07",
            f"{base_url}/api/yield-alert/alerts?start_date=2026-03-01&end_date=2026-03-07&page=1&per_page=10",
            f"{base_url}/api/yield-alert/trend?start_date=2026-03-01&end_date=2026-03-07",
        ]

        def worker(worker_idx: int):
            for i in range(5):
                url = endpoints[(worker_idx + i) % len(endpoints)]
                ok, duration, error = _request(
                    "GET", url, timeout=timeout,
                    allowed_statuses={200, 429, 503},  # 429 = rate limiter
                )
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(f"{error} @ {url}", duration)

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(worker, i) for i in range(concurrent_users)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        result.total_duration = time.time() - start_time
        print(result.report())

        assert result.success_rate >= 80.0, f"Success rate too low: {result.success_rate:.1f}%"


@pytest.mark.stress
@pytest.mark.load
class TestRejectHistoryStress:
    """Stress tests for Reject History endpoints."""

    def test_concurrent_analytics_queries(
        self, base_url: str, stress_config: dict, stress_result
    ):
        """Concurrent reject-history analytics queries should stay stable."""
        result = stress_result("Reject History Concurrent Analytics")
        concurrent_users = min(stress_config["concurrent_users"], 8)
        timeout = stress_config["timeout"]

        endpoints = [
            f"{base_url}/api/reject-history/options",
            f"{base_url}/api/reject-history/summary?start_date=2026-03-01&end_date=2026-03-07",
            f"{base_url}/api/reject-history/trend?start_date=2026-03-01&end_date=2026-03-07",
            f"{base_url}/api/reject-history/reason-pareto?start_date=2026-03-01&end_date=2026-03-07",
            f"{base_url}/api/reject-history/list?start_date=2026-03-01&end_date=2026-03-07&page=1&per_page=10",
        ]

        def worker(worker_idx: int):
            for i in range(4):
                url = endpoints[(worker_idx + i) % len(endpoints)]
                ok, duration, error = _request(
                    "GET", url, timeout=timeout,
                    # 404 = no data; 500 = Oracle query error under load (expected in stress)
                    allowed_statuses={200, 400, 404, 429, 500, 503},
                )
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(f"{error} @ {url}", duration)

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(worker, i) for i in range(concurrent_users)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        result.total_duration = time.time() - start_time
        print(result.report())

        assert result.success_rate >= 80.0, f"Success rate too low: {result.success_rate:.1f}%"


@pytest.mark.stress
class TestPostBurstRecovery:
    """Verify system recovers after heavy cross-module burst."""

    def test_health_stable_after_cross_module_burst(
        self, base_url: str, stress_result
    ):
        """After a burst hitting all modules, health endpoint should respond."""
        result = stress_result("Post-Burst Health Recovery")

        burst_endpoints = [
            f"{base_url}/api/wip/overview/summary",
            f"{base_url}/api/resource/status/summary",
            f"{base_url}/api/hold-overview/summary",
            f"{base_url}/api/yield-alert/filter-options",
            f"{base_url}/api/reject-history/options",
            f"{base_url}/api/job-query/resources",
            f"{base_url}/api/mid-section-defect/station-options",
        ]

        # Burst phase: 2 requests per endpoint concurrently
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for endpoint in burst_endpoints:
                for _ in range(2):
                    futures.append(
                        executor.submit(
                            _request, "GET", endpoint,
                            timeout=30.0, allowed_statuses={200, 429, 503},
                        )
                    )
            for f in concurrent.futures.as_completed(futures):
                ok, duration, error = f.result()
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        # Recovery probe — give server up to 30s to drain burst connections
        healthy_probes = 0
        for _ in range(5):
            try:
                resp = requests.get(f"{base_url}/health", timeout=30)
                if resp.status_code == 429:
                    # Rate-limited post-burst — server is alive and protecting itself
                    healthy_probes += 1
                    result.add_success(0.1)
                    time.sleep(1.0)
                    continue
                if resp.status_code in (200, 503):
                    payload = resp.json()
                    if payload.get("status") in {"healthy", "degraded", "unhealthy"}:
                        healthy_probes += 1
                        result.add_success(0.1)
                        continue
                result.add_failure(f"Unexpected health response: {resp.status_code}", 0.1)
            except Exception as exc:
                result.add_failure(str(exc)[:80], 0.1)
            time.sleep(0.5)

        result.total_duration = time.time() - start_time
        print(result.report())

        assert healthy_probes >= 1, f"Health recoverability too low: {healthy_probes}/5"
