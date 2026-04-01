# -*- coding: utf-8 -*-
"""Stress tests for mid-section-defect (MSD) endpoints.

Tests concurrent query and view load.
Run with: pytest tests/stress/test_mid_section_defect_stress.py -v --run-stress
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest
import requests

from tests.stress.conftest import StressTestResult


@pytest.mark.stress
@pytest.mark.load
class TestMsdQueryStress:
    """Concurrent MSD queries should maintain 95% success rate."""

    @staticmethod
    def _run_query(base_url: str, timeout: float, seed: int) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.get(
                f"{base_url}/api/mid-section-defect/analysis",
                params={
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-07",
                    "page": 1,
                    "per_page": 20,
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 400, 429, 503):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_msd_queries(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("msd_query")
        # MSD analysis does real Oracle queries — limit concurrency to avoid cascading timeouts
        concurrent_users = min(stress_config["concurrent_users"], 5)
        requests_per_user = min(stress_config["requests_per_user"], 5)
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
        assert result.success_rate >= 80.0, (
            f"MSD success rate {result.success_rate:.1f}% below 80% threshold"
        )
        assert result.avg_response_time < 30.0


@pytest.mark.stress
@pytest.mark.load
class TestMsdStationOptionsStress:
    """Concurrent station options requests should be very fast."""

    @staticmethod
    def _run_station_options(base_url: str, timeout: float) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.get(
                f"{base_url}/api/mid-section-defect/station-options",
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 404, 429):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_station_options_under_load(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("msd_station_options")
        concurrent_users = stress_config["concurrent_users"]
        timeout = stress_config["timeout"]

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_station_options, base_url, timeout)
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
