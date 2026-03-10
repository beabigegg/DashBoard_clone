# -*- coding: utf-8 -*-
"""Stress tests for reject-history half-year query stability."""

from __future__ import annotations

import concurrent.futures
import os
import time

import pytest
import requests

try:
    import redis
except Exception:  # pragma: no cover - optional runtime dependency
    redis = None


@pytest.mark.stress
@pytest.mark.load
@pytest.mark.skipif(
    os.environ.get("RUN_LONG_STRESS") != "1",
    reason="Long-range reject-history stress disabled; set RUN_LONG_STRESS=1 to run.",
)
class TestRejectHistoryLongRangeStress:
    """Concurrent half-year reject-history queries should stay recoverable."""

    @staticmethod
    def _redis_used_memory_bytes() -> int | None:
        if redis is None:
            return None
        redis_url = os.environ.get("STRESS_REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        try:
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            info = client.info("memory")
            used = info.get("used_memory")
            return int(used) if used is not None else None
        except Exception:
            return None

    @staticmethod
    def _run_query(base_url: str, timeout: float, seed: int) -> tuple[bool, float, str]:
        start = time.time()
        try:
            start_date = os.environ.get("STRESS_REJECT_HISTORY_START_DATE")
            end_date = os.environ.get("STRESS_REJECT_HISTORY_END_DATE")
            if not start_date or not end_date:
                year = 2024 + (seed % 2)
                start_date = f"{year}-01-01"
                end_date = f"{year}-07-09"
            response = requests.post(
                f"{base_url}/api/reject-history/query",
                json={
                    "mode": "date_range",
                    "start_date": start_date,
                    "end_date": end_date,
                    "exclude_material_scrap": True,
                    "exclude_pb_diode": True,
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if response.status_code != 200:
                return False, duration, f"HTTP {response.status_code}"
            payload = response.json()
            if payload.get("success") is True and payload.get("query_id"):
                return True, duration, ""
            return False, duration, f"success={payload.get('success')} error={payload.get('error')}"
        except Exception as exc:  # pragma: no cover - runtime/network dependent
            return False, time.time() - start, str(exc)[:180]

    def test_concurrent_190_day_queries_no_crash(self, base_url: str, stress_result):
        result = stress_result("Reject History Long-Range Concurrent")
        timeout = float(os.environ.get("STRESS_REJECT_HISTORY_TIMEOUT", "420"))
        concurrent_users = int(os.environ.get("STRESS_REJECT_HISTORY_CONCURRENCY", "3"))
        rounds = int(os.environ.get("STRESS_REJECT_HISTORY_ROUNDS", "2"))
        max_redis_delta_mb = int(os.environ.get("STRESS_REJECT_REDIS_MAX_DELTA_MB", "256"))
        total_requests = concurrent_users * rounds
        redis_before = self._redis_used_memory_bytes()

        started = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [
                executor.submit(self._run_query, base_url, timeout, idx)
                for idx in range(total_requests)
            ]
            for future in concurrent.futures.as_completed(futures):
                ok, duration, error = future.result()
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(error, duration)
        result.total_duration = time.time() - started

        print(result.report())
        assert result.total_requests == total_requests
        assert result.success_rate >= 90.0, f"Success rate too low: {result.success_rate:.2f}%"

        health_resp = requests.get(f"{base_url}/health", timeout=10)
        assert health_resp.status_code in (200, 503)

        redis_after = self._redis_used_memory_bytes()
        if redis_before is not None and redis_after is not None:
            delta_mb = (redis_after - redis_before) / (1024 * 1024)
            assert delta_mb <= max_redis_delta_mb, (
                f"Redis memory delta too high: {delta_mb:.1f}MB > {max_redis_delta_mb}MB"
            )
