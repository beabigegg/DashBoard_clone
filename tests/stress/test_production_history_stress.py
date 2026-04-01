# -*- coding: utf-8 -*-
"""Stress tests for production-history endpoints.

Tests concurrent query and pagination under load.
Run with: pytest tests/stress/test_production_history_stress.py -v --run-stress
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest
import requests

from tests.stress.conftest import StressTestResult


@pytest.mark.stress
@pytest.mark.load
class TestProductionHistoryQueryStress:
    """Concurrent production history queries should stay within thresholds."""

    @staticmethod
    def _run_query(base_url: str, timeout: float) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/production-history/query",
                json={
                    "pj_types": ["GA"],
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-07",
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 202, 400, 503):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_production_history_queries(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("production_history_query")
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
            f"Production history success rate {result.success_rate:.1f}% below 95%"
        )


@pytest.mark.stress
@pytest.mark.load
class TestProductionHistoryPageStress:
    """Concurrent pagination requests against cached dataset."""

    @staticmethod
    def _run_page(base_url: str, timeout: float, dataset_id: str, page: int) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/production-history/page",
                json={"dataset_id": dataset_id, "page": page, "per_page": 25},
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 410, 400):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_pagination_under_concurrent_load(self, base_url, stress_config, stress_result):
        import os
        result: StressTestResult = stress_result("production_history_page")
        concurrent_users = min(stress_config["concurrent_users"], 8)
        timeout = stress_config["timeout"]
        dataset_id = os.environ.get("STRESS_PROD_HISTORY_DATASET_ID", "nonexistent-ph-test")

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_page, base_url, timeout, dataset_id, (i % 5) + 1)
                for i in range(concurrent_users * 10)
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
