# -*- coding: utf-8 -*-
"""Resilience tests for UPH Performance async spool (add-uph-performance-page).

Mirrors tests/integration/test_production_achievement_resilience.py (the
closest precedent: both are BaseChunkedDuckDBJob TIME-chunk jobs sharing the
same heavy_query_slot semaphore) and tests/integration/test_eap_alarm_resilience.py.
All tests here are fully mocked (fake Redis dict, mocked OracleArrowReader /
global_concurrency) so they run in CI without a real Redis/RQ worker/Oracle
connection.

These tests are deliberately NOT duplicating the 2 resilience tests already
in tests/integration/test_uph_performance_rq_async.py::TestUphPerformanceResilience
(test_oracle_fault_mid_chunk_no_partial_spool, which checks no-partial-spool
via a fake reader on job.run(); test_redis_unavailable_returns_503_no_legacy_fallback,
which mocks is_async_available()=False directly). This file covers the
genuinely uncovered resilience surface, mirroring production-achievement's
class shapes:

  TestWorkerCrashMidJob
    - test_oracle_failure_during_chunk_fanout_marks_job_failed
        A real OracleArrowReader.chunk_iter() failure during the TIME-chunk
        fan-out must propagate out of execute_uph_performance_unified_job()
        AND resolve the job to a terminal "failed" status in the Redis
        job-meta hash (never left "queued"/"started") -- the rq_async file's
        existing fault test only checks the spool file, not job status.
  TestJobTimeout
    - test_rq_job_timeout_exception_marks_job_failed_not_stuck_running
        RQ's own SIGALRM-based job_timeout kill (JobTimeoutException) must
        still resolve to a terminal "failed" status, not leave the frontend
        poll loop waiting forever.
  TestRedisUnavailableAtEnqueueTOCTOU
    - test_route_returns_503_when_redis_drops_between_health_check_and_enqueue
        TOCTOU race: is_async_available() reports healthy, but Redis becomes
        unreachable by the time enqueue_job() actually runs -- exercises the
        REAL async_query_job_service.enqueue_job() Redis-down branch through
        the real Flask route (the existing rq_async test only short-circuits
        via a mocked is_async_available()=False, a coarser variant).
  TestHeavyQuerySlotContention
    - test_run_completes_when_slot_at_capacity_fail_open
        heavy_query_slot is advisory/fail-open -- UphPerformanceJob.run() must
        still complete when HEAVY_QUERY_MAX_CONCURRENT is already reached
        (design.md's flagged "4th heavy consumer on a shared 3-slot semaphore"
        risk -- correctness of the fail-open contract itself is resilience
        scope; load/contention measurement is stress-soak-engineer's).
    - test_release_not_called_when_slot_was_never_acquired
        A job that never counted against the semaphore must never call
        release_heavy_query_slot (would erroneously decrement another job's
        counted slot).
    - test_run_acquires_and_releases_when_slot_available
        Control case: acquire+release happen exactly once when the slot IS
        available.

pytestmark = pytest.mark.integration
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    from rq.timeouts import JobTimeoutException
except ImportError:  # pragma: no cover - rq always installed in this repo, defensive only
    JobTimeoutException = TimeoutError  # type: ignore[assignment,misc]

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_production_achievement_resilience.py)
# ---------------------------------------------------------------------------

def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


def _auth_client(app):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user"] = {"username": "alice", "mail": "alice@test.com", "is_admin": False}
    return c


def _make_redis_store():
    """Return a (store_dict, mock_client) pair sharing in-memory state."""
    store: dict = {}
    client = MagicMock()

    def _hset(key, mapping=None, **kw):
        if mapping:
            store.setdefault(key, {}).update(mapping)

    def _hgetall(key):
        return dict(store.get(key, {}))

    def _expire(key, ttl):
        pass

    client.hset.side_effect = _hset
    client.hgetall.side_effect = _hgetall
    client.expire.side_effect = _expire
    client.ping.return_value = True
    return store, client


def _seed_job(store: dict, prefix: str, job_id: str) -> None:
    from mes_dashboard.core.redis_client import get_key

    key = get_key(f"{prefix}:job:{job_id}:meta")
    store[key] = {
        "status": "queued",
        "queue_name": "test-queue",
        "owner": "tester",
        "created_at": str(time.time()),
        "completed_at": "",
        "progress": "",
        "pct": "",
        "stage": "",
        "completed_stages": "",
        "query_id": "",
        "dataset_id": "",
        "error": "",
    }


# ── Worker crash mid-job (Oracle failure during chunk fan-out) ───────────────

class TestWorkerCrashMidJob:
    """Worker crash mid-job: Oracle read error during the TIME-chunk fan-out
    must propagate AND mark the job failed (not silently stuck)."""

    def test_oracle_failure_during_chunk_fanout_marks_job_failed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        store, mock_client = _make_redis_store()
        job_id = f"uph-crash-{uuid.uuid4().hex[:8]}"
        _seed_job(store, "uph-performance", job_id)

        def _raising_chunk_iter(self, sql, params, chunk_size=10000):
            raise RuntimeError("ORA-03135: connection lost contact")

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _raising_chunk_iter,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.get_control_redis_client",
            lambda: mock_client,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.get_redis_client",
            lambda: mock_client,
        )
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)

        from mes_dashboard.workers.uph_performance_worker import (
            execute_uph_performance_unified_job,
        )

        with pytest.raises(RuntimeError, match="ORA-03135"):
            execute_uph_performance_unified_job(
                job_id=job_id,
                date_from="2026-04-01",
                date_to="2026-04-01",
                families=["GDBA"],
                workcenter_names=[],
                packages=[],
                pj_types=[],
                equipment_ids=[],
            )

        from mes_dashboard.services.async_query_job_service import get_job_status

        status = get_job_status("uph-performance", job_id)
        assert status is not None
        assert status["status"] == "failed", (
            f"Worker crash must mark the job terminal-failed, not leave it "
            f"queued/started: {status}"
        )
        assert status["error"] and "ORA-03135" in status["error"]


# ── Job timeout (RQ's own SIGALRM-based kill) ────────────────────────────────

class TestJobTimeout:
    """RQ's job_timeout kill manifests as JobTimeoutException raised inside
    the worker function -- the job must still resolve to a terminal "failed"
    status so the frontend poll loop does not wait forever."""

    def test_rq_job_timeout_exception_marks_job_failed_not_stuck_running(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        store, mock_client = _make_redis_store()
        job_id = f"uph-timeout-{uuid.uuid4().hex[:8]}"
        _seed_job(store, "uph-performance", job_id)
        from mes_dashboard.core.redis_client import get_key
        store[get_key(f"uph-performance:job:{job_id}:meta")]["status"] = "started"

        timeout_exc = JobTimeoutException(
            "Task exceeded maximum timeout value (1800 seconds)"
        )

        def _timing_out_chunk_iter(self, sql, params, chunk_size=10000):
            raise timeout_exc

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _timing_out_chunk_iter,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.get_control_redis_client",
            lambda: mock_client,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.get_redis_client",
            lambda: mock_client,
        )
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)

        from mes_dashboard.workers.uph_performance_worker import (
            execute_uph_performance_unified_job,
        )

        with pytest.raises(Exception):  # JobTimeoutException (or TimeoutError fallback)
            execute_uph_performance_unified_job(
                job_id=job_id,
                date_from="2026-04-01",
                date_to="2026-04-01",
                families=["GWBA"],
                workcenter_names=[],
                packages=[],
                pj_types=[],
                equipment_ids=[],
            )

        from mes_dashboard.services.async_query_job_service import get_job_status

        status = get_job_status("uph-performance", job_id)
        assert status is not None
        assert status["status"] == "failed", (
            f"A job killed by RQ's own timeout must resolve to a terminal "
            f"'failed' status, not remain 'started' forever (client poll "
            f"loop would hang): {status}"
        )
        assert status["status"] not in ("queued", "started"), (
            "job_timeout must not leave the job in a non-terminal state"
        )
        assert status["error"]


# ── Redis unavailable at enqueue (TOCTOU race) ────────────────────────────────

class TestRedisUnavailableAtEnqueueTOCTOU:
    """is_async_available() reports healthy, but Redis drops before the
    actual enqueue call -- exercises the REAL enqueue_job() Redis-down
    branch (async_query_job_service.py), not a mocked short-circuit."""

    def test_route_returns_503_when_redis_drops_between_health_check_and_enqueue(self):
        app = _make_app()
        client = _auth_client(app)

        with (
            patch(
                "mes_dashboard.routes.uph_performance_routes._get_spool_path",
                return_value=None,
            ),
            patch(
                "mes_dashboard.services.async_query_job_service.is_async_available",
                return_value=True,
            ),
            patch(
                "mes_dashboard.services.async_query_job_service.get_control_redis_client",
                return_value=None,
            ),
            patch(
                "mes_dashboard.services.async_query_job_service.get_redis_client",
                return_value=None,
            ),
        ):
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-04-01", "date_to": "2026-04-02"},
                content_type="application/json",
            )

        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.get_json()}"
        payload = resp.get_json()
        assert payload["success"] is False
        assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_enqueue_job_service_returns_none_and_error_when_redis_unreachable(self):
        """Unit-level pin: async_query_job_service.enqueue_job() itself (not
        the route) must fail closed -- (None, error) -- when Redis is down."""
        with (
            patch(
                "mes_dashboard.services.async_query_job_service.get_control_redis_client",
                return_value=None,
            ),
        ):
            from mes_dashboard.services.async_query_job_service import enqueue_job

            job_id, err = enqueue_job(
                queue_name="uph-performance-query",
                worker_fn=lambda **kw: None,
                owner="tester",
                prefix="uph-performance",
            )

        assert job_id is None
        assert err is not None
        assert "unreachable" in err.lower() or "redis" in err.lower()


# ── heavy_query_slot semaphore contention ─────────────────────────────────────

class TestHeavyQuerySlotContention:
    """global_concurrency.heavy_query_slot() is advisory/fail-open -- verify
    UphPerformanceJob still completes when the cap is already reached, and
    never double-releases a slot it never counted (design.md's flagged "4th
    heavy consumer on a shared 3-slot semaphore" risk)."""

    def _make_empty_result_job(self, tmp_path, monkeypatch, job_id: str):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        def _empty_chunk_iter(self, sql, params, chunk_size=10000):
            return iter(())  # zero Oracle rows -- valid empty-result path

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _empty_chunk_iter,
        )

        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        return UphPerformanceJob(
            job_id=job_id,
            params={"date_from": "2026-04-01", "date_to": "2026-04-01"},
        )

    def test_run_completes_when_slot_at_capacity_fail_open(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.core.global_concurrency.acquire_heavy_query_slot",
            lambda owner_id, ttl=600: False,  # HEAVY_QUERY_MAX_CONCURRENT already reached
        )
        release_calls: list[str] = []
        monkeypatch.setattr(
            "mes_dashboard.core.global_concurrency.release_heavy_query_slot",
            lambda owner_id: release_calls.append(owner_id),
        )

        job = self._make_empty_result_job(tmp_path, monkeypatch, "uph-slot-contended-001")
        spool_path = job.run()  # must not block or raise despite the cap being reached

        assert Path(spool_path).exists(), "job must still write its spool parquet (fail-open)"

    def test_release_not_called_when_slot_was_never_acquired(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.core.global_concurrency.acquire_heavy_query_slot",
            lambda owner_id, ttl=600: False,
        )
        release_calls: list[str] = []
        monkeypatch.setattr(
            "mes_dashboard.core.global_concurrency.release_heavy_query_slot",
            lambda owner_id: release_calls.append(owner_id),
        )

        job = self._make_empty_result_job(tmp_path, monkeypatch, "uph-slot-contended-002")
        job.run()

        assert release_calls == [], (
            "A job that never counted against the semaphore (acquired=False) "
            f"must never call release_heavy_query_slot (would erroneously "
            f"decrement another job's slot): {release_calls}"
        )

    def test_run_acquires_and_releases_when_slot_available(self, tmp_path, monkeypatch):
        """Control case: when the slot IS available, it is acquired and
        released exactly once around the Oracle fan-out."""
        acquire_calls: list[str] = []
        release_calls: list[str] = []

        def _acquire(owner_id, ttl=600):
            acquire_calls.append(owner_id)
            return True

        def _release(owner_id):
            release_calls.append(owner_id)

        monkeypatch.setattr("mes_dashboard.core.global_concurrency.acquire_heavy_query_slot", _acquire)
        monkeypatch.setattr("mes_dashboard.core.global_concurrency.release_heavy_query_slot", _release)

        job = self._make_empty_result_job(tmp_path, monkeypatch, "uph-slot-available-001")
        job.run()

        assert acquire_calls == ["uph_performance:uph-slot-available-001"]
        assert release_calls == ["uph_performance:uph-slot-available-001"]
