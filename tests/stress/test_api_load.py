# -*- coding: utf-8 -*-
"""Backend API load tests.

Tests API endpoints under concurrent load to verify:
- Connection pool stability
- Timeout handling
- Response consistency under pressure

Run with: pytest tests/stress/test_api_load.py -v -s
"""

import pytest
import time
import requests
import concurrent.futures
from typing import List, Tuple

# Import from local conftest via pytest fixtures


@pytest.mark.stress
@pytest.mark.load
class TestAPILoadConcurrent:
    """Load tests with concurrent requests."""

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

    def test_wip_summary_concurrent_load(self, base_url: str, stress_config: dict, stress_result):
        """Test WIP summary API under concurrent load."""
        result = stress_result("WIP Summary Concurrent Load")
        url = f"{base_url}/api/wip/overview/summary"
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

        # Assertions
        assert result.success_rate >= 90.0, f"Success rate {result.success_rate:.1f}% is below 90%"
        assert result.avg_response_time < 10.0, f"Avg response time {result.avg_response_time:.2f}s exceeds 10s"

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = []
            for _ in range(concurrent_users):
                for endpoint in endpoints:
                    for _ in range(requests_per_endpoint):
                        futures.append(executor.submit(self._make_request, endpoint, timeout))

            for future in concurrent.futures.as_completed(futures):
                success, duration, error = future.result()
                if success:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)

        result.total_duration = time.time() - start_time

        print(result.report())

        assert result.success_rate >= 85.0, f"Success rate {result.success_rate:.1f}% is below 85%"


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
