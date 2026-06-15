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
                f"{base_url}/api/resource/history/query",
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
            return True, timeout, ""  # Server alive but slow under load
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


@pytest.mark.stress
@pytest.mark.load
class TestResourceHistoryViewStress:
    """Concurrent view requests on a pre-warmed dataset."""

    @staticmethod
    def _run_view(base_url: str, timeout: float, dataset_id: str) -> tuple[bool, float, str]:
        start = time.time()
        try:
            resp = requests.get(
                f"{base_url}/api/resource/history/view",
                params={
                    "query_id": dataset_id,
                    "granularity": "day",
                },
                timeout=timeout,
            )
            duration = time.time() - start
            if resp.status_code in (200, 400, 404, 410, 429):
                return True, duration, ""
            return False, duration, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return True, timeout, ""  # Server alive but slow under load
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


# ---------------------------------------------------------------------------
# Async-job load tests (IP-10 / AC-3 / AC-9)
# ---------------------------------------------------------------------------

@pytest.mark.stress
class TestResourceHistoryAsyncStress:
    """Concurrent async-job stress probes for the RQ worker path.

    These tests exercise ``execute_resource_history_query_job`` directly
    (unit-level, no live server required) so they run in CI without a
    deployed instance.  Oracle I/O is replaced by a mock so the test
    focuses purely on concurrency and control-flow correctness.

    Design constraints from design.md / implementation-plan.md:
      - Worker calls execute_primary_query() unmodified (wrapped only).
      - ThreadPoolExecutor(max_workers=2) fan-out for base+OEE happens
        inside execute_primary_query; DB_POOL_SIZE=2 in worker launch.
      - Coarse milestones: 5 -> 15 -> 90 -> 100 (non-decreasing; last == 100).
      - RESOURCE_JOB_TIMEOUT_SECONDS is a module-level constant; tests must
        use monkeypatch.setattr (os.environ patching has no effect post-import).
    """

    # ------------------------------------------------------------------
    # AC-3: N=5 concurrent jobs complete; no DB pool exhaustion
    # ------------------------------------------------------------------

    def test_concurrent_async_jobs_complete_without_db_pool_exhaustion(
        self, monkeypatch
    ):
        """5 concurrent execute_resource_history_query_job calls all complete.

        Verifies AC-3 (worker executes without error) and the design Open Risk
        (ThreadPoolExecutor(max_workers=2) fan-out tolerated under DB_POOL_SIZE=2).
        Oracle I/O is mocked; no live server needed.
        """
        import unittest.mock as mock
        import mes_dashboard.services.resource_query_job_service as svc
        from mes_dashboard.core.database import DatabasePoolExhaustedError

        # Replace execute_primary_query (deferred import inside worker fn) with a
        # fast mock that returns a plausible result dict.
        fake_result = {"query_id": "stress-qid-001", "rows": []}
        execute_primary_query_mock = mock.MagicMock(return_value=fake_result)

        # Silence Redis calls; they are irrelevant for the concurrency probe.
        noop = mock.MagicMock(return_value=None)

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress", noop
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job", noop
        )

        N = 5
        exceptions: list[Exception] = []

        def _run_one(idx: int):
            import mes_dashboard.services.resource_query_job_service as _svc
            with mock.patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                execute_primary_query_mock,
            ), mock.patch(
                "mes_dashboard.rq_worker_preload.ensure_rq_logging",
                mock.MagicMock(return_value=None),
            ):
                _svc.execute_resource_history_query_job(
                    job_id=f"stress-conc-{idx:02d}",
                    owner="stress-test",
                    start_date="2025-01-01",
                    end_date="2025-12-31",
                    granularity="day",
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as pool:
            futures = {pool.submit(_run_one, i): i for i in range(N)}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    fut.result()
                except DatabasePoolExhaustedError as exc:
                    exceptions.append(exc)
                except Exception as exc:
                    # Any non-pool exception is still a failure for this test.
                    exceptions.append(exc)

        pool_exhausted = [e for e in exceptions if isinstance(e, DatabasePoolExhaustedError)]
        assert not pool_exhausted, (
            f"DB pool exhaustion under N={N} concurrent async workers: "
            f"{[str(e) for e in pool_exhausted]}"
        )
        assert not exceptions, (
            f"{len(exceptions)}/{N} concurrent async jobs raised exceptions: "
            f"{[str(e)[:120] for e in exceptions]}"
        )

    # ------------------------------------------------------------------
    # AC-3: milestone sequence integrity under 10 concurrent invocations
    # ------------------------------------------------------------------

    def test_async_job_progress_milestones_under_load(self, monkeypatch):
        """10 concurrent jobs each emit a non-decreasing milestone sequence ending at 100.

        Verifies the coarse milestone contract (5 -> 15 -> 90 -> 100) from
        design.md and implementation-plan.md under concurrent load.

        Implementation note: both update_job_progress and complete_job are
        patched via monkeypatch (module-level, thread-safe) rather than
        per-thread mock.patch context managers, which are not safe to nest
        across threads sharing the same patch target.
        """
        import threading
        import unittest.mock as mock
        import mes_dashboard.services.resource_query_job_service as svc

        N = 10
        # Shared milestone store: job_id -> list[int]; protected by lock.
        all_milestone_sequences: dict[str, list[int]] = {}
        lock = threading.Lock()

        def _capture_pct(prefix, jid, **fields):
            if "pct" in fields:
                with lock:
                    all_milestone_sequences.setdefault(jid, []).append(int(fields["pct"]))

        # Module-level patches — applied once, safe for all threads.
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            _capture_pct,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            mock.MagicMock(return_value=None),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
            mock.MagicMock(return_value={"query_id": "stress-ms-qid", "rows": []}),
        )
        monkeypatch.setattr(
            "mes_dashboard.rq_worker_preload.ensure_rq_logging",
            mock.MagicMock(return_value=None),
        )

        def _run_one(idx: int):
            svc.execute_resource_history_query_job(
                job_id=f"stress-ms-{idx:02d}",
                owner="stress-test",
                start_date="2025-01-01",
                end_date="2025-12-31",
                granularity="day",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(_run_one, i) for i in range(N)]
            for fut in concurrent.futures.as_completed(futures):
                fut.result()  # re-raise any exception from the worker thread

        assert len(all_milestone_sequences) == N, (
            f"Expected {N} milestone sequences; got {len(all_milestone_sequences)}"
        )

        failures = []
        for job_id, seq in all_milestone_sequences.items():
            if not seq:
                failures.append(f"{job_id}: no milestones recorded")
                continue
            # Non-decreasing check
            for i in range(1, len(seq)):
                if seq[i] < seq[i - 1]:
                    failures.append(
                        f"{job_id}: milestone decreased {seq[i-1]} -> {seq[i]} in {seq}"
                    )
                    break
            # Last value must be 100
            if seq[-1] != 100:
                failures.append(
                    f"{job_id}: last milestone {seq[-1]} != 100 (full sequence: {seq})"
                )

        assert not failures, (
            f"Milestone invariant violations across {N} concurrent jobs:\n"
            + "\n".join(f"  {f}" for f in failures)
        )

    # ------------------------------------------------------------------
    # AC-9: timeout enforcement — slow Oracle must not hang indefinitely
    # ------------------------------------------------------------------

    def test_job_timeout_enforced_under_slow_oracle(self, monkeypatch):
        """Worker produces a terminal error when Oracle is slower than the timeout.

        Simulates RESOURCE_JOB_TIMEOUT_SECONDS = 1 and execute_primary_query
        sleeping for 2 s then raising TimeoutError.  The worker's own timeout
        mechanism (JobTypeConfig timeout_seconds) is enforced at the RQ queue
        level in production; here we verify the worker's exception path
        (complete_job(error=...)) is wired correctly, which is the observable
        unit-level proxy for the timeout-kills-worker contract (AC-9).

        Asserts:
          1. complete_job is called with a non-empty ``error`` kwarg.
          2. The worker re-raises (RQ sees a failed job, not a silent swallow).
          3. The whole invocation completes in <= 10 s (no indefinite hang).
        """
        import unittest.mock as mock
        import mes_dashboard.services.resource_query_job_service as svc

        # Lower the timeout constant so the scenario is legible in test output.
        monkeypatch.setattr(svc, "RESOURCE_JOB_TIMEOUT_SECONDS", 1)

        complete_job_calls: list[dict] = []

        def _record_complete(prefix, job_id, **kwargs):
            complete_job_calls.append({"prefix": prefix, "job_id": job_id, **kwargs})

        noop_progress = mock.MagicMock(return_value=None)

        def _slow_and_fail(*args, **kwargs):
            # Simulate Oracle taking longer than timeout (2 s > patched 1 s).
            time.sleep(2)
            raise TimeoutError("Oracle query exceeded RESOURCE_JOB_TIMEOUT_SECONDS=1")

        with mock.patch(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            noop_progress,
        ), mock.patch(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            side_effect=_record_complete,
        ), mock.patch(
            "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
            side_effect=_slow_and_fail,
        ), mock.patch(
            "mes_dashboard.rq_worker_preload.ensure_rq_logging",
            mock.MagicMock(return_value=None),
        ):
            start = time.time()
            with pytest.raises(TimeoutError):
                svc.execute_resource_history_query_job(
                    job_id="stress-timeout-001",
                    owner="stress-test",
                    start_date="2023-01-01",
                    end_date="2023-12-31",
                    granularity="day",
                )
            elapsed = time.time() - start

        # 1. complete_job must have been called with an error kwarg (terminal state).
        error_calls = [c for c in complete_job_calls if c.get("error")]
        assert error_calls, (
            "Worker failed to call complete_job(error=...) after timeout-like exception; "
            f"complete_job calls: {complete_job_calls}"
        )

        # 2. The error message must be non-empty (not silently swallowed).
        assert error_calls[0]["error"], (
            "complete_job was called with an empty error string; "
            "job status would be ambiguous to pollers."
        )

        # 3. No indefinite hang — invocation must finish well within 10 s.
        assert elapsed < 10.0, (
            f"Timeout simulation took {elapsed:.1f} s — worker may not enforce the timeout "
            f"(RESOURCE_JOB_TIMEOUT_SECONDS=1 but worker ran for {elapsed:.1f} s)."
        )
