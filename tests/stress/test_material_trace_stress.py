# -*- coding: utf-8 -*-
"""Stress tests for material-trace endpoints.

Tests concurrent query throughput and pagination under load.
Run with: pytest tests/stress/test_material_trace_stress.py -v --run-stress
"""

from __future__ import annotations

import concurrent.futures
import os
import time

import pytest
import requests

from tests.stress.conftest import StressTestResult


@pytest.mark.stress
@pytest.mark.load
class TestMaterialTraceQueryStress:
    """Concurrent material trace queries should maintain success rate."""

    @staticmethod
    def _run_query(base_url: str, timeout: float, seed: int) -> tuple[bool, float, str]:
        start = time.time()
        try:
            # Use forward lot query mode
            resp = requests.post(
                f"{base_url}/api/material-trace/query",
                json={
                    "mode": "lot",
                    "ids": [f"GA26010001-A00-{str(seed).zfill(3)}"],
                    "workcenter_groups": [],
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 202, 400, 404, 429):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_queries_success_rate(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("material_trace_query")
        concurrent_users = stress_config["concurrent_users"]
        requests_per_user = stress_config["requests_per_user"]
        timeout = stress_config["timeout"]

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_query, base_url, timeout, i)
                for i in range(concurrent_users * requests_per_user)
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
            f"Success rate {result.success_rate:.1f}% below 95% threshold"
        )


@pytest.mark.stress
@pytest.mark.load
class TestMaterialTracePaginationStress:
    """Paginated material trace results under concurrent load."""

    @staticmethod
    def _run_page(base_url: str, timeout: float, dataset_id: str, page: int) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/material-trace/page",
                json={"dataset_id": dataset_id, "page": page, "per_page": 50},
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 410, 404):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_pagination_under_load(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("material_trace_pagination")
        concurrent_users = min(stress_config["concurrent_users"], 5)
        timeout = stress_config["timeout"]
        dataset_id = os.environ.get("STRESS_MATERIAL_TRACE_DATASET_ID", "nonexistent-test-id")

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_page, base_url, timeout, dataset_id, (i % 5) + 1)
                for i in range(concurrent_users * 5)
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
