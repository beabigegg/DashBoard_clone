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

    # Expected guardrail error patterns — these indicate the system
    # correctly rejected an oversized query, not a crash.
    _GUARDRAIL_PATTERNS = (
        "RESULT_TOO_LARGE",
        "SERVICE_UNAVAILABLE",
        "超過上限",
        "HTTP 400",
        "HTTP 503",
    )

    @classmethod
    def _is_guardrail_response(cls, error_msg: str) -> bool:
        """Return True if the error is an expected guardrail/backpressure response."""
        return any(pat in error_msg for pat in cls._GUARDRAIL_PATTERNS)

    @staticmethod
    def _poll_async_job(base_url: str, job_id: str, timeout: float) -> tuple[bool, str]:
        """Poll async job until terminal state. Returns (ok, query_id_or_error)."""
        status_url = f"{base_url}/api/reject-history/job/{job_id}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(status_url, timeout=30)
            if resp.status_code != 200:
                return False, f"Job status HTTP {resp.status_code}"
            payload = resp.json()
            status = payload.get("data", payload)
            job_status = status.get("status")
            if job_status in ("completed", "finished"):
                return True, status.get("query_id", "")
            if job_status == "failed":
                return False, f"Job failed: {str(status.get('error', ''))[:120]}"
            time.sleep(3)
        return False, f"Job {job_id} timed out"

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
            payload = response.json()

            if response.status_code == 200:
                data = payload.get("data", payload)
                query_id = data.get("query_id") or payload.get("query_id")
                if payload.get("success") is True and query_id:
                    return True, duration, ""
                return False, duration, f"success={payload.get('success')} error={payload.get('error')}"

            if response.status_code == 202:
                data = payload.get("data", payload)
                job_id = data.get("job_id")
                if not job_id:
                    return False, duration, "202 missing job_id"
                ok, msg = TestRejectHistoryLongRangeStress._poll_async_job(
                    base_url, job_id, timeout - duration,
                )
                total_duration = time.time() - start
                if ok:
                    return True, total_duration, ""
                return False, total_duration, msg

            if response.status_code == 503:
                code = payload.get("code", "")
                return False, duration, f"HTTP 503 ({code})"

            return False, duration, f"HTTP {response.status_code}"
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

        # Classify errors: guardrail responses (backpressure, result-too-large)
        # are expected behaviour, not crashes.
        guardrail_count = sum(
            1 for e in result.errors if self._is_guardrail_response(e)
        )
        unexpected_failures = result.failed_requests - guardrail_count
        handled_rate = (
            (result.successful_requests + guardrail_count) / result.total_requests * 100
            if result.total_requests
            else 0.0
        )

        print(result.report())
        print(f"Guardrail rejections: {guardrail_count}")
        print(f"Unexpected failures:  {unexpected_failures}")
        print(f"Handled rate:         {handled_rate:.2f}%")

        assert result.total_requests == total_requests
        assert handled_rate >= 90.0, (
            f"Handled rate too low: {handled_rate:.2f}% "
            f"(unexpected failures: {unexpected_failures})"
        )

        health_resp = requests.get(f"{base_url}/health", timeout=10)
        assert health_resp.status_code in (200, 503)

        redis_after = self._redis_used_memory_bytes()
        if redis_before is not None and redis_after is not None:
            delta_mb = (redis_after - redis_before) / (1024 * 1024)
            assert delta_mb <= max_redis_delta_mb, (
                f"Redis memory delta too high: {delta_mb:.1f}MB > {max_redis_delta_mb}MB"
            )
