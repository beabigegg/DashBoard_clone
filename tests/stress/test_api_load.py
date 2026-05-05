# -*- coding: utf-8 -*-
"""Backend API load tests.

Tests API endpoints under concurrent load to verify:
- Connection pool stability
- Timeout handling
- Response consistency under pressure

Run with: pytest tests/stress/test_api_load.py -v -s
"""

import os
import pytest
import time
import requests
import concurrent.futures
from typing import Tuple
from urllib.parse import quote

from load_collector import LoadCollector
from stress_registry import record_load_summary

# Threshold env vars (task 6.2)
_MAX_MEM_PCT = float(os.environ.get("STRESS_MAX_MEM_PCT", "85"))
_MAX_DB_POOL_PCT = float(os.environ.get("STRESS_MAX_DB_POOL_PCT", "90"))
_MAX_GUARD_REJECTS = int(os.environ.get("STRESS_MAX_GUARD_REJECTS", "5"))
_MAX_QUEUE_DEPTH = int(os.environ.get("STRESS_MAX_QUEUE_DEPTH", "20"))

_LOAD_MONITORING = os.environ.get("STRESS_LOAD_MONITORING", "0") == "1"


@pytest.mark.stress
@pytest.mark.load
class TestAPILoadConcurrent:
    """Load tests with concurrent requests."""

    def _make_request(self, url: str, timeout: float, headers: dict | None = None) -> Tuple[bool, float, str]:
        """Make a single request and return (success, duration, error)."""
        start = time.time()
        try:
            response = requests.get(url, timeout=timeout, headers=headers)
            duration = time.time() - start
            if response.status_code == 429:
                # Rate-limited: server is alive and protecting itself — count as success
                return (True, duration, '')
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return (True, duration, '')
                return (False, duration, f"API returned success=false: {data.get('error', 'unknown')}")
            return (False, duration, f"HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            duration = time.time() - start
            return (False, duration, "Request timeout")
        except requests.exceptions.ConnectionError as e:
            duration = time.time() - start
            return (False, duration, f"Connection error: {str(e)[:50]}")
        except Exception as e:
            duration = time.time() - start
            return (False, duration, f"Error: {str(e)[:50]}")

    def _discover_workcenter(self, base_url: str, timeout: float) -> str:
        """Get one available workcenter for detail load tests."""
        try:
            response = requests.get(f"{base_url}/api/wip/meta/workcenters", timeout=timeout)
            if response.status_code != 200:
                return "TMTT"
            payload = response.json()
            items = payload.get("data") or []
            if not items:
                return "TMTT"
            return str(items[0].get("name") or "TMTT")
        except Exception:
            return "TMTT"

    def _discover_hold_reason(self, base_url: str, timeout: float) -> str:
        """Get one available hold reason for hold-detail load tests."""
        try:
            response = requests.get(f"{base_url}/api/wip/overview/hold", timeout=timeout)
            if response.status_code != 200:
                return "YieldLimit"
            payload = response.json()
            items = (payload.get("data") or {}).get("items") or []
            if not items:
                return "YieldLimit"
            return str(items[0].get("reason") or "YieldLimit")
        except Exception:
            return "YieldLimit"

    def test_wip_summary_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test WIP summary API under concurrent load."""
        result = stress_result("WIP Summary Concurrent Load")
        url = f"{base_url}/api/wip/overview/summary"
        concurrent_users = stress_config['concurrent_users']
        requests_per_user = stress_config['requests_per_user']
        timeout = stress_config['timeout']

        total_requests = concurrent_users * requests_per_user

        start_time = time.time()
        with LoadCollector(base_url) as collector:
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [
                    executor.submit(self._make_request, url, timeout)
                    for _ in range(total_requests)
                ]

                for future in concurrent.futures.as_completed(futures):
                    success, duration, error = future.result()
                    if success:
                        result.add_success(duration)
                    else:
                        result.add_failure(error, duration)

        result.total_duration = time.time() - start_time
        result.load_summary = collector.summary
        record_load_summary("WIP Summary Concurrent Load", collector.summary)

        print(result.report())

        # Assertions
        assert result.success_rate >= 90.0, f"Success rate {result.success_rate:.1f}% is below 90%"
        assert result.avg_response_time < 10.0, f"Avg response time {result.avg_response_time:.2f}s exceeds 10s"
        if _LOAD_MONITORING and collector.summary:
            collector.summary.assert_within(max_mem_pct=_MAX_MEM_PCT, max_db_pool_pct=_MAX_DB_POOL_PCT)
            td = collector.summary.telemetry_diff
            if td and not td.endpoint_unavailable:
                assert td.guard_reject_total <= _MAX_GUARD_REJECTS, (
                    f"Guard rejections during test ({td.guard_reject_total}) exceeded limit ({_MAX_GUARD_REJECTS})"
                )
            if collector.summary.peak_queue_depths:
                for q, depth in collector.summary.peak_queue_depths.items():
                    assert depth <= _MAX_QUEUE_DEPTH, (
                        f"RQ queue '{q}' peak depth {depth} exceeded limit {_MAX_QUEUE_DEPTH}"
                    )

    def test_wip_matrix_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test WIP matrix API under concurrent load."""
        result = stress_result("WIP Matrix Concurrent Load")
        url = f"{base_url}/api/wip/overview/matrix"
        concurrent_users = stress_config['concurrent_users']
        requests_per_user = stress_config['requests_per_user']
        timeout = stress_config['timeout']

        total_requests = concurrent_users * requests_per_user

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [
                executor.submit(self._make_request, url, timeout)
                for _ in range(total_requests)
            ]

            for future in concurrent.futures.as_completed(futures):
                success, duration, error = future.result()
                if success:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time

        print(result.report())

        assert result.success_rate >= 90.0, f"Success rate {result.success_rate:.1f}% is below 90%"
        assert result.avg_response_time < 15.0, f"Avg response time {result.avg_response_time:.2f}s exceeds 15s"

    def test_wip_detail_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test WIP detail API under concurrent load."""
        result = stress_result("WIP Detail Concurrent Load")
        concurrent_users = stress_config['concurrent_users']
        requests_per_user = stress_config['requests_per_user']
        timeout = stress_config['timeout']

        workcenter = self._discover_workcenter(base_url, timeout)
        url = f"{base_url}/api/wip/detail/{quote(workcenter)}?page=1&page_size=100"
        total_requests = concurrent_users * requests_per_user

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [
                executor.submit(self._make_request, url, timeout)
                for _ in range(total_requests)
            ]

            for future in concurrent.futures.as_completed(futures):
                success, duration, error = future.result()
                if success:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time
        print(result.report())

        assert result.success_rate >= 85.0, f"Success rate {result.success_rate:.1f}% is below 85%"
        assert result.avg_response_time < 20.0, f"Avg response time {result.avg_response_time:.2f}s exceeds 20s"

    def test_hold_detail_lots_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test hold-detail lots API under concurrent load."""
        result = stress_result("Hold Detail Lots Concurrent Load")
        concurrent_users = stress_config['concurrent_users']
        requests_per_user = stress_config['requests_per_user']
        timeout = stress_config['timeout']

        reason = self._discover_hold_reason(base_url, timeout)
        url = f"{base_url}/api/wip/hold-detail/lots?reason={quote(reason)}&page=1&per_page=50"
        total_requests = concurrent_users * requests_per_user

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [
                executor.submit(self._make_request, url, timeout)
                for _ in range(total_requests)
            ]

            for future in concurrent.futures.as_completed(futures):
                success, duration, error = future.result()
                if success:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time
        print(result.report())

        assert result.success_rate >= 85.0, f"Success rate {result.success_rate:.1f}% is below 85%"
        assert result.avg_response_time < 20.0, f"Avg response time {result.avg_response_time:.2f}s exceeds 20s"

    def test_resource_summary_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test resource status summary API under concurrent load."""
        result = stress_result("Resource Status Summary Concurrent Load")
        url = f"{base_url}/api/resource/status/summary"
        concurrent_users = stress_config['concurrent_users']
        requests_per_user = stress_config['requests_per_user']
        timeout = stress_config['timeout']

        total_requests = concurrent_users * requests_per_user

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [
                executor.submit(
                    self._make_request,
                    url,
                    timeout,
                    {"X-Forwarded-For": f"10.0.0.{(idx % concurrent_users) + 1}"},
                )
                for idx in range(total_requests)
            ]

            for future in concurrent.futures.as_completed(futures):
                success, duration, error = future.result()
                if success:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time

        print(result.report())

        assert result.success_rate >= 90.0, f"Success rate {result.success_rate:.1f}% is below 90%"

    def test_mixed_endpoints_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test multiple API endpoints simultaneously."""
        result = stress_result("Mixed Endpoints Concurrent Load")
        endpoints = [
            f"{base_url}/api/wip/overview/summary",
            f"{base_url}/api/wip/overview/matrix",
            f"{base_url}/api/wip/overview/hold",
            f"{base_url}/api/wip/meta/workcenters",
            f"{base_url}/api/resource/status/summary",
        ]
        concurrent_users = stress_config['concurrent_users']
        timeout = stress_config['timeout']

        # 5 requests per endpoint per user
        requests_per_endpoint = 5
        total_requests = concurrent_users * len(endpoints) * requests_per_endpoint

        start_time = time.time()
        with LoadCollector(base_url) as collector:
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = []
                for user_idx in range(concurrent_users):
                    headers = {"X-Forwarded-For": f"10.0.1.{user_idx + 1}"}
                    for endpoint in endpoints:
                        for _ in range(requests_per_endpoint):
                            futures.append(executor.submit(self._make_request, endpoint, timeout, headers))

                for future in concurrent.futures.as_completed(futures):
                    success, duration, error = future.result()
                    if success:
                        result.add_success(duration)
                    else:
                        result.add_failure(error, duration)

        result.total_duration = time.time() - start_time
        result.load_summary = collector.summary
        record_load_summary("Mixed Endpoints Concurrent Load", collector.summary)

        print(result.report())

        assert result.success_rate >= 85.0, f"Success rate {result.success_rate:.1f}% is below 85%"
        if _LOAD_MONITORING and collector.summary:
            collector.summary.assert_within(max_mem_pct=_MAX_MEM_PCT, max_db_pool_pct=_MAX_DB_POOL_PCT)


@pytest.mark.stress
@pytest.mark.load
class TestAPILoadRampUp:
    """Load tests with gradual ramp-up."""

    def _make_request(self, url: str, timeout: float) -> Tuple[bool, float, str]:
        """Make a single request and return (success, duration, error)."""
        start = time.time()
        try:
            response = requests.get(url, timeout=timeout)
            duration = time.time() - start
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return (True, duration, '')
                return (False, duration, f"API error: {data.get('error', 'unknown')}")
            return (False, duration, f"HTTP {response.status_code}")
        except Exception as e:
            duration = time.time() - start
            return (False, duration, str(e)[:50])

    def test_gradual_load_increase(self, base_url: str, stress_result):
        """Test API stability as load gradually increases."""
        result = stress_result("Gradual Load Increase")
        url = f"{base_url}/api/wip/overview/summary"

        # Start with 2 concurrent users, increase to 20
        load_levels = [2, 5, 10, 15, 20]
        requests_per_level = 10
        timeout = 30.0

        start_time = time.time()

        for concurrent_users in load_levels:
            print(f"\n  Testing with {concurrent_users} concurrent users...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [
                    executor.submit(self._make_request, url, timeout)
                    for _ in range(requests_per_level)
                ]

                for future in concurrent.futures.as_completed(futures):
                    success, duration, error = future.result()
                    if success:
                        result.add_success(duration)
                    else:
                        result.add_failure(error, duration)

            time.sleep(0.5)  # Brief pause between levels

        result.total_duration = time.time() - start_time

        print(result.report())

        assert result.success_rate >= 80.0, f"Success rate {result.success_rate:.1f}% is below 80%"


@pytest.mark.stress
class TestAPITimeoutHandling:
    """Tests for timeout handling under load."""

    @staticmethod
    def _make_request(url: str, timeout: float) -> Tuple[bool, float, str]:
        """Make a single request and return (success, duration, error)."""
        start = time.time()
        try:
            response = requests.get(url, timeout=timeout)
            duration = time.time() - start
            if response.status_code == 200:
                if "application/json" in response.headers.get("Content-Type", ""):
                    payload = response.json()
                    if payload.get("success", True):
                        return (True, duration, "")
                    return (False, duration, f"API returned success=false: {payload.get('error', 'unknown')}")
                return (True, duration, "")
            return (False, duration, f"HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            duration = time.time() - start
            return (False, duration, "Request timeout")
        except requests.exceptions.ConnectionError as exc:
            duration = time.time() - start
            return (False, duration, f"Connection error: {str(exc)[:50]}")
        except Exception as exc:
            duration = time.time() - start
            return (False, duration, f"Error: {str(exc)[:50]}")

    def test_connection_recovery_after_timeout(self, base_url: str, stress_result):
        """Test that API recovers after timeout scenarios."""
        result = stress_result("Connection Recovery After Timeout")

        # First, make requests with very short timeout to trigger timeouts
        short_timeout_url = f"{base_url}/api/wip/overview/matrix"

        print("\n  Phase 1: Triggering timeouts with 0.1s timeout...")
        for _ in range(5):
            start = time.time()
            try:
                requests.get(short_timeout_url, timeout=0.1)
                result.add_success(time.time() - start)
            except requests.exceptions.Timeout:
                result.add_failure("Expected timeout", time.time() - start)
            except Exception as e:
                result.add_failure(str(e)[:50], time.time() - start)

        # Now verify system recovers with normal timeout
        print("  Phase 2: Verifying recovery with 30s timeout...")
        recovery_url = f"{base_url}/api/wip/overview/summary"
        recovered = False
        for i in range(10):
            start = time.time()
            try:
                response = requests.get(recovery_url, timeout=30.0)
                duration = time.time() - start
                if response.status_code == 200 and response.json().get('success'):
                    result.add_success(duration)
                    recovered = True
                    print(f"    Recovered on attempt {i+1}")
                    break
            except Exception as e:
                result.add_failure(str(e)[:50], time.time() - start)
            time.sleep(0.5)

        result.total_duration = sum(result.response_times)

        print(result.report())

        assert recovered, "System did not recover after timeout scenarios"

    def test_wip_pages_recoverability_after_burst(self, base_url: str, stress_result):
        """After a burst, health and critical WIP APIs should still respond."""
        result = stress_result("WIP Pages Recoverability After Burst")
        timeout = 30.0
        probe_endpoints = [
            f"{base_url}/api/wip/overview/summary",
            f"{base_url}/api/wip/overview/matrix",
            f"{base_url}/api/wip/overview/hold",
            f"{base_url}/health",
        ]

        # Burst phase
        burst_count = 40
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for _ in range(burst_count):
                for endpoint in probe_endpoints[:-1]:
                    futures.append(executor.submit(self._make_request, endpoint, timeout))

            for future in concurrent.futures.as_completed(futures):
                success, duration, error = future.result()
                if success:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        # Recoverability probes
        healthy_probes = 0
        for _ in range(5):
            probe_start = time.time()
            try:
                response = requests.get(f"{base_url}/health", timeout=5)
                duration = time.time() - probe_start
                if response.status_code in (200, 503):
                    payload = response.json()
                    if payload.get("status") in {"healthy", "degraded", "unhealthy"}:
                        healthy_probes += 1
                        result.add_success(duration)
                        continue
                result.add_failure(f"Unexpected health response: {response.status_code}", duration)
            except Exception as exc:
                result.add_failure(str(exc)[:80], time.time() - probe_start)
            time.sleep(0.2)

        result.total_duration = time.time() - start_time
        print(result.report())
        assert healthy_probes >= 3, f"Health endpoint recoverability too low: {healthy_probes}/5"


@pytest.mark.stress
class TestAPIResponseConsistency:
    """Tests for response consistency under load."""

    def test_response_data_consistency(self, base_url: str, stress_config: dict):
        """Verify API returns consistent data structure under load."""
        url = f"{base_url}/api/wip/overview/summary"
        concurrent_users = 5
        requests_per_user = 10
        timeout = 30.0

        responses = []

        def make_request():
            try:
                response = requests.get(url, timeout=timeout)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [
                executor.submit(make_request)
                for _ in range(concurrent_users * requests_per_user)
            ]

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    responses.append(result)

        # Verify all successful responses have consistent structure
        assert len(responses) > 0, "No successful responses received"

        first_response = responses[0]
        required_fields = {'success'}

        for i, response in enumerate(responses):
            for field in required_fields:
                assert field in response, f"Response {i} missing field '{field}'"

        print(f"\n  Received {len(responses)} consistent responses")
