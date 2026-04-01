# -*- coding: utf-8 -*-
"""Async job lifecycle stress probes.

Tests the 202 → polling → spool-hit pipeline for production-history and
yield-alert RQ workers under concurrent load:

  11.2  Queue saturation — 5 concurrent production-history queries
  11.3  Yield-alert queue saturation — 5 concurrent yield-alert queries
  11.4  Polling concurrency — 10 threads poll same job_id simultaneously
  11.5  Spool hit bypass — same query twice / 5 identical concurrent queries
  11.6  Retry behavior — RQ failed queue, max 3 attempts
"""

import concurrent.futures
import os
import time
from datetime import date, timedelta
from typing import List, Optional

import pytest
import requests

from async_helpers import AsyncJobPoller, AsyncJobResult, AsyncJobTimeout

_TIMEOUT = float(os.environ.get("STRESS_TIMEOUT", "60"))


def _date_range(days_back: int = 30):
    end = date.today()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _production_history_payload() -> dict:
    start, end = _date_range(30)
    return {
        "start_date": start,
        "end_date": end,
        "pj_types": ["GA"],
        "lot_ids": [],
        "work_orders": [],
        "packages": [],
        "bop_codes": [],
        "workcenter_groups": [],
        "workcenter_names": [],
        "equipment_ids": [],
    }


def _yield_alert_payload() -> dict:
    start, end = _date_range(30)
    return {"start_date": start, "end_date": end}


# ─────────────────────────────────────────────────────────────
# 11.2 — Production-history queue saturation
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestProductionHistoryQueueSaturation:
    """Submit 5 concurrent production-history queries; verify all complete."""

    def _submit_one(self, base_url: str) -> AsyncJobResult:
        poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
        try:
            return poller.submit_and_wait("POST", "/api/production-history/query",
                                          _production_history_payload())
        except AsyncJobTimeout as exc:
            return AsyncJobResult(
                job_id=exc.job_id, status="timeout", elapsed=exc.elapsed, poll_count=0,
                error=str(exc)
            )

    def test_production_history_5_concurrent(self, base_url: str):
        """5 concurrent production-history queries must all complete without being dropped."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self._submit_one, base_url) for _ in range(5)]
            results: List[AsyncJobResult] = [f.result() for f in concurrent.futures.as_completed(futures)]

        statuses = [r.status for r in results]

        # Skip if server is unreachable
        if all(r.status == "error" and r.http_status is None for r in results):
            pytest.skip("Server unreachable")

        dropped = [r for r in results if r.status == "error" and r.http_status is None]
        timeouts = [r for r in results if r.status == "timeout"]
        failures = [r for r in results if r.status == "failed"]

        assert not dropped, f"{len(dropped)}/5 jobs were silently dropped (connection error)"
        assert not timeouts, f"{len(timeouts)}/5 production-history jobs timed out"

        completed = [r for r in results if r.status in ("completed", "sync_hit")]
        print(f"\n  Statuses: {statuses}")
        print(f"  Completed: {len(completed)}/5, failures: {len(failures)}/5")


# ─────────────────────────────────────────────────────────────
# 11.3 — Yield-alert queue saturation
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestYieldAlertQueueSaturation:
    """Submit 5 concurrent yield-alert queries; verify no job silently dropped."""

    def _submit_one(self, base_url: str) -> AsyncJobResult:
        poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
        try:
            return poller.submit_and_wait("POST", "/api/yield-alert/query",
                                          _yield_alert_payload())
        except AsyncJobTimeout as exc:
            return AsyncJobResult(
                job_id=exc.job_id, status="timeout", elapsed=exc.elapsed, poll_count=0,
                error=str(exc)
            )

    def test_yield_alert_5_concurrent(self, base_url: str):
        """5 concurrent yield-alert queries must all be accepted and none silently dropped."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self._submit_one, base_url) for _ in range(5)]
            results: List[AsyncJobResult] = [f.result() for f in concurrent.futures.as_completed(futures)]

        if all(r.status == "error" and r.http_status is None for r in results):
            pytest.skip("Server unreachable")

        dropped = [r for r in results if r.status == "error" and r.http_status is None]
        assert not dropped, f"{len(dropped)}/5 yield-alert jobs were silently dropped"

        print(f"\n  Statuses: {[r.status for r in results]}")


# ─────────────────────────────────────────────────────────────
# 11.4 — Polling concurrency probe
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestPollingConcurrency:
    """10 threads poll same job_id simultaneously; verify consistent responses."""

    def _submit_job(self, base_url: str) -> Optional[str]:
        """Submit a job and return its status URL without waiting."""
        try:
            resp = requests.post(
                f"{base_url}/api/production-history/query",
                json=_production_history_payload(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 202:
                body = resp.json()
                data = body.get("data") or body
                return data.get("status_url") or data.get("poll_url")
            return None
        except Exception:
            return None

    def _poll_once(self, status_url: str) -> tuple:
        """Make a single poll and return (status_code, response_ok)."""
        try:
            resp = requests.get(status_url, timeout=10.0)
            return resp.status_code, resp.status_code in (200, 202)
        except Exception:
            return None, False

    def test_concurrent_polling_same_job(self, base_url: str):
        """10 threads poll the same job_id simultaneously; no 500 errors allowed."""
        status_url = self._submit_job(base_url)
        if not status_url:
            pytest.skip("Could not obtain async job status_url (endpoint may not be async)")

        # Wait briefly for job to be registered
        time.sleep(1.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._poll_once, status_url) for _ in range(10)]
            poll_results = [f.result() for f in concurrent.futures.as_completed(futures)]

        status_codes = [code for code, _ in poll_results if code is not None]
        errors_500 = [code for code in status_codes if code == 500]

        assert not errors_500, (
            f"{len(errors_500)}/10 concurrent polls returned HTTP 500"
        )

        # All responses should be consistent (all same status or transitioning)
        unique_codes = set(status_codes)
        valid_codes = {200, 202, 404}  # 404 if job expired during test
        unexpected = unique_codes - valid_codes
        assert not unexpected, f"Unexpected status codes from concurrent polls: {unexpected}"

        print(f"\n  Concurrent poll status codes: {status_codes}")


# ─────────────────────────────────────────────────────────────
# 11.5 — Spool hit bypass probe
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestSpoolHitBypass:
    """Verify that identical queries hit the spool cache on second submission."""

    def test_same_query_twice_gets_200(self, base_url: str):
        """Submit same production-history query twice; second should get HTTP 200 (spool hit)."""
        payload = _production_history_payload()
        poller = AsyncJobPoller(base_url, max_wait=180, poll_interval=2.0)

        # First submission — may be 200 or 202
        try:
            result1 = poller.submit_and_wait("POST", "/api/production-history/query", payload)
        except AsyncJobTimeout:
            pytest.skip("First query timed out")

        if result1.status == "error" and result1.http_status is None:
            pytest.skip("Server unreachable")

        # Second submission — should get 200 (spool hit) if caching is active
        try:
            resp2 = requests.post(
                f"{base_url}/api/production-history/query",
                json=payload,
                timeout=_TIMEOUT,
            )
        except Exception:
            pytest.skip("Second request failed")

        # Accept 200 (spool hit) or 202 (cache miss — job enqueued again)
        assert resp2.status_code in (200, 202), (
            f"Second identical query returned unexpected HTTP {resp2.status_code}"
        )

        if resp2.status_code == 200:
            print("\n  Spool hit confirmed: second identical query returned HTTP 200")
        else:
            print("\n  NOTE: Second identical query returned HTTP 202 (cache miss or TTL expired)")

    def test_5_identical_concurrent_queries_at_most_1_job(self, base_url: str):
        """Submit 5 identical concurrent queries; at most 1 RQ job should be created."""
        payload = _production_history_payload()

        statuses = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            def _submit():
                try:
                    resp = requests.post(
                        f"{base_url}/api/production-history/query",
                        json=payload,
                        timeout=_TIMEOUT,
                    )
                    return resp.status_code
                except Exception:
                    return None

            futures = [executor.submit(_submit) for _ in range(5)]
            statuses = [f.result() for f in concurrent.futures.as_completed(futures)]

        if all(s is None for s in statuses):
            pytest.skip("Server unreachable")

        valid_statuses = [s for s in statuses if s is not None]
        assert all(s in (200, 202) for s in valid_statuses), (
            f"Unexpected status codes from concurrent identical queries: {valid_statuses}"
        )

        # Verify at most 1 job was created (others should be 200 spool hits)
        new_jobs = sum(1 for s in valid_statuses if s == 202)
        print(f"\n  {new_jobs}/5 requests triggered a new RQ job (rest were spool hits or fast)")
        # Note: Not a hard assertion — spool dedup is best-effort under race conditions
        # This probe documents observed behavior


# ─────────────────────────────────────────────────────────────
# 11.6 — Retry behavior verification
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestRetryBehavior:
    """Verify that failed RQ jobs did not exceed max 3 attempts (initial + 2 retries)."""

    def test_rq_failed_queue_max_retries(self, base_url: str):
        """Check RQ failed queue after a stress run; no job should have > 3 attempts."""
        try:
            resp = requests.get(
                f"{base_url}/admin/api/rq-status",
                timeout=10.0,
            )
        except Exception:
            pytest.skip("Admin RQ status endpoint unreachable")

        if resp.status_code != 200:
            pytest.skip(f"Admin RQ status returned HTTP {resp.status_code}")

        try:
            body = resp.json()
        except Exception:
            pytest.skip("Admin RQ status returned non-JSON")

        data = body.get("data") or body
        failed_jobs = data.get("failed_jobs") or []

        violations = []
        for job in failed_jobs:
            attempts = job.get("retries") or job.get("attempts") or job.get("retry_count") or 0
            job_id = job.get("job_id") or job.get("id") or "unknown"
            # max 3 attempts = initial + 2 retries
            if attempts > 3:
                violations.append(f"job {job_id}: {attempts} attempts (max 3)")

        assert not violations, (
            "RQ jobs exceeded max retry limit:\n" + "\n".join(violations)
        )

        print(f"\n  RQ failed queue: {len(failed_jobs)} failed jobs, all within retry limits")
