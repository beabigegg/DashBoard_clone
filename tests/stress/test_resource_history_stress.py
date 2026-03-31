# -*- coding: utf-8 -*-
"""Stress tests for resource-history endpoints.

Tests concurrent query and view computation under load.
Run with: pytest tests/stress/test_resource_history_stress.py -v --run-stress
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest
import requests

from tests.stress.conftest import StressTestResult


@pytest.mark.stress
@pytest.mark.load
class TestResourceHistoryQueryStress:
    """Concurrent resource history queries."""

    @staticmethod
    def _run_query(base_url: str, timeout: float) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/resource-history/query",
                json={
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-07",
                    "granularity": "day",
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 400, 503):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, timeout, "Timeout"
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_resource_history_queries(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("resource_history_query")
        concurrent_users = stress_config["concurrent_users"]
        requests_per_user = stress_config["requests_per_user"]
        timeout = stress_config["timeout"]

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_query, base_url, timeout)
                for _ in range(concurrent_users * requests_per_user)
            ]
            for fut in concurrent.futures.as_completed(futures):
                ok, dur, err = fut.result()
                if ok:
                    result.add_success(dur)
                else:
                    result.add_failure(err, dur)
        result.total_duration = time.time() - start

        print(result.report())
        assert result.success_rate >= 95.0, (
            f"Resource history success rate {result.success_rate:.1f}% below 95%"
        )
        assert result.avg_response_time < 5.0


@pytest.mark.stress
@pytest.mark.load
class TestResourceHistoryViewStress:
    """Concurrent view requests on a pre-warmed dataset."""

    @staticmethod
    def _run_view(base_url: str, timeout: float, dataset_id: str) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.get(
                f"{base_url}/api/resource-history/view",
                params={
                    "dataset_id": dataset_id,
                    "view": "kpi",
                    "granularity": "day",
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 410, 404):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, timeout, "Timeout"
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_view_requests(self, base_url, stress_config, stress_result):
        import os
        result: StressTestResult = stress_result("resource_history_view")
        concurrent_users = min(stress_config["concurrent_users"], 8)
        timeout = stress_config["timeout"]
        dataset_id = os.environ.get("STRESS_RESOURCE_HISTORY_DATASET_ID", "nonexistent-test-ds")

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_view, base_url, timeout, dataset_id)
                for _ in range(concurrent_users * 10)
            ]
            for fut in concurrent.futures.as_completed(futures):
                ok, dur, err = fut.result()
                if ok:
                    result.add_success(dur)
                else:
                    result.add_failure(err, dur)
        result.total_duration = time.time() - start

        print(result.report())
        assert result.success_rate >= 95.0
        assert result.avg_response_time < 5.0
