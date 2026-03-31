# -*- coding: utf-8 -*-
"""Stress tests for yield-alert endpoints.

Tests concurrent query, summary, and alerts requests under load.
Run with: pytest tests/stress/test_yield_alert_stress.py -v --run-stress
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest
import requests

from tests.stress.conftest import StressTestResult


@pytest.mark.stress
@pytest.mark.load
class TestYieldAlertSummaryStress:
    """Concurrent /summary requests should sustain 95% success rate."""

    @staticmethod
    def _run_summary(base_url: str, timeout: float) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.get(
                f"{base_url}/api/yield-alert/summary",
                params={"start_date": "2026-03-01", "end_date": "2026-03-07"},
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 503):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, timeout, "Timeout"
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_summary_requests(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("yield_alert_summary")
        concurrent_users = stress_config["concurrent_users"]
        requests_per_user = stress_config["requests_per_user"]
        timeout = stress_config["timeout"]

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_summary, base_url, timeout)
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
            f"Yield-alert summary success rate {result.success_rate:.1f}% below 95%"
        )
        assert result.avg_response_time < 5.0


@pytest.mark.stress
@pytest.mark.load
class TestYieldAlertAlertsStress:
    """Concurrent /alerts requests with pagination."""

    @staticmethod
    def _run_alerts(base_url: str, timeout: float, page: int) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.get(
                f"{base_url}/api/yield-alert/alerts",
                params={
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-07",
                    "page": page,
                    "per_page": 50,
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 503):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, timeout, "Timeout"
        except Exception as exc:
            return False, time.time() - start, str(exc)[:80]

    def test_concurrent_alerts_pagination(self, base_url, stress_config, stress_result):
        result: StressTestResult = stress_result("yield_alert_alerts")
        concurrent_users = stress_config["concurrent_users"]
        timeout = stress_config["timeout"]

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._run_alerts, base_url, timeout, (i % 3) + 1)
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
        assert result.avg_response_time < 5.0
