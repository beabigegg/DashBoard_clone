# -*- coding: utf-8 -*-
"""Resilience tests for Production Achievement Rate async spool
(production-achievement-async-spool, ADR-0016).

Mirrors tests/integration/test_eap_alarm_resilience.py and
tests/test_async_job_timeout.py's fake-Redis pattern. All tests here are
fully mocked (fake Redis dict, mocked OracleArrowReader/global_concurrency) so
they run in CI without a real Redis/RQ worker/Oracle connection -- the real
-Redis/real-Oracle end-to-end variants belong to the nightly
``integration_real`` gate (tests/integration/test_production_achievement_rq_async.py).

Tests:
  TestWorkerCrashMidJob
    - test_oracle_failure_during_chunk_fanout_marks_job_failed
        Worker crash mid-job: an Oracle read error raised inside
        OracleArrowReader.chunk_iter() during the TIME-chunk fan-out must
        propagate out of execute_production_achievement_unified_job() AND
        mark the job "failed" in the Redis job-meta hash (never leaves it
        stuck in "queued"/"started").
  TestJobTimeout
    - test_rq_job_timeout_exception_marks_job_failed_not_stuck_running
        RQ's own SIGALRM-based job_timeout kill manifests as
        rq.timeouts.JobTimeoutException raised inside the worker function;
        this must still be caught by execute_production_achievement_unified_job's
        except-block and produce a terminal "failed" status (not an
        indefinitely "started" job that the poll loop waits on forever).
  TestRedisUnavailableAtEnqueue
    - test_route_returns_503_when_redis_drops_between_health_check_and_enqueue
        TOCTOU race: is_async_available() reports healthy, but Redis becomes
        unreachable by the time enqueue_job() actually runs -- exercises the
        REAL async_query_job_service.enqueue_job() Redis-down branch (not a
        mocked enqueue_query_job return value), end-to-end through the real
        Flask route.
  TestMissingOrLateSpool
    - test_spool_miss_returns_410 (namespace-pinned regression)
    - test_spool_registered_then_removed_from_disk_before_download_returns_410
        Realistic "late spool" race: GET /report reports a spool-hit (200,
        spool_download_url present) but the underlying parquet file is
        removed from disk (TTL sweep / rollback purge) before the client's
        subsequent spool download -- must degrade to 410, never 500 or a
        silently-empty download.
  TestHeavyQuerySlotContention
    - test_run_completes_when_slot_at_capacity_fail_open
        heavy_query_slot is advisory/fail-open (global_concurrency.py) -- a
        job must still complete successfully when the concurrency cap is
        already reached, not block or raise.
    - test_release_not_called_when_slot_was_never_acquired
        A job that never counted against the semaphore (acquired=False) must
        never call release_heavy_query_slot -- doing so would erroneously
        decrement another job's counted slot.

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
# Shared helpers
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
    """Return a (store_dict, mock_client) pair sharing in-memory state.

    Mirrors tests/test_async_job_timeout.py's _make_redis_store() -- a
    minimal HSET/HGETALL/EXPIRE double so async_query_job_service's
    complete_job()/get_job_status() round-trip without a real Redis server.
    """
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
    """Pre-populate a queued job entry (mirrors enqueue_job's initial write)."""
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
        job_id = f"pa-crash-{uuid.uuid4().hex[:8]}"
        _seed_job(store, "production-achievement", job_id)

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

        from mes_dashboard.workers.production_achievement_worker import (
            execute_production_achievement_unified_job,
        )

        with pytest.raises(RuntimeError, match="ORA-03135"):
            execute_production_achievement_unified_job(
                job_id=job_id,
                params={"start_date": "2026-04-01", "end_date": "2026-04-01"},
            )

        from mes_dashboard.services.async_query_job_service import get_job_status

        status = get_job_status("production-achievement", job_id)
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
        job_id = f"pa-timeout-{uuid.uuid4().hex[:8]}"
        _seed_job(store, "production-achievement", job_id)
        # Simulate the job having been "started" (in-flight) before the timeout fires.
        from mes_dashboard.core.redis_client import get_key
        store[get_key(f"production-achievement:job:{job_id}:meta")]["status"] = "started"

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

        from mes_dashboard.workers.production_achievement_worker import (
            execute_production_achievement_unified_job,
        )

        with pytest.raises(Exception):  # JobTimeoutException (or TimeoutError fallback)
            execute_production_achievement_unified_job(
                job_id=job_id,
                params={"start_date": "2026-04-01", "end_date": "2026-04-01"},
            )

        from mes_dashboard.services.async_query_job_service import get_job_status

        status = get_job_status("production-achievement", job_id)
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

class TestRedisUnavailableAtEnqueue:
    """is_async_available() reports healthy, but Redis drops before the
    actual enqueue call -- exercises the REAL enqueue_job() Redis-down
    branch (async_query_job_service.py), not a mocked short-circuit."""

    def test_route_returns_503_when_redis_drops_between_health_check_and_enqueue(self):
        app = _make_app()
        client = _auth_client(app)

        with (
            patch(
                "mes_dashboard.routes.production_achievement_routes.get_spool_file_path",
                return_value=None,
            ),
            patch(
                "mes_dashboard.routes.production_achievement_routes.is_async_available",
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
            resp = client.get(
                "/api/production-achievement/report",
                query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
            )

        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.get_json()}"
        payload = resp.get_json()
        assert payload["success"] is False
        assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_enqueue_job_service_returns_none_and_error_when_redis_unreachable(self):
        """Unit-level pin: async_query_job_service.enqueue_job() itself (not
        the route) must fail closed -- (None, error) -- when Redis is down,
        for the production-achievement job type specifically registered."""
        with (
            patch(
                "mes_dashboard.services.async_query_job_service.get_control_redis_client",
                return_value=None,
            ),
        ):
            from mes_dashboard.services.async_query_job_service import enqueue_job

            job_id, err = enqueue_job(
                queue_name="production-achievement-query",
                worker_fn=lambda **kw: None,
                owner="tester",
                prefix="production-achievement",
            )

        assert job_id is None
        assert err is not None
        assert "unreachable" in err.lower() or "redis" in err.lower()


# ── Missing / late spool file (410 from spool_routes) ────────────────────────

class TestMissingOrLateSpool:
    def test_spool_miss_returns_410(self):
        """Namespace-pinned regression: production_achievement spool miss
        must degrade to 410, mirroring test_eap_alarm_resilience.py's
        per-domain spool-miss pin (generic mechanism, domain-scoped test)."""
        app = _make_app()
        with app.test_client() as client:
            with (
                patch(
                    "mes_dashboard.routes.spool_routes.get_spool_file_path",
                    return_value=None,
                ),
            ):
                resp = client.get("/api/spool/production_achievement/abc123def4567890.parquet")

        assert resp.status_code == 410
        data = resp.get_json()
        assert data["success"] is False

    def test_spool_registered_then_removed_from_disk_before_download_returns_410(self, tmp_path):
        """Realistic 'late spool' race spanning both routes: /report reports
        a spool-hit (200, spool_download_url present) but the file is purged
        from disk (TTL sweep / rollback rm) before the client's subsequent
        download -- must be 410, never 500 or a truncated/empty download."""
        parquet_path = tmp_path / "pa-late-001.parquet"
        parquet_path.write_bytes(b"PAR1" + b"\x00" * 12)

        app = _make_app()
        client = _auth_client(app)

        with (
            patch(
                "mes_dashboard.routes.production_achievement_routes.get_spool_file_path",
                return_value=str(parquet_path),
            ),
            patch(
                "mes_dashboard.routes.production_achievement_routes.get_spec_workcenter_mapping",
                return_value={},
            ),
            patch(
                "mes_dashboard.routes.production_achievement_routes.get_targets_map",
                return_value={},
            ),
        ):
            resp = client.get(
                "/api/production-achievement/report",
                query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        spool_url = data["spool_download_url"]
        assert spool_url.startswith("/api/spool/production_achievement/")

        # Simulate the race: the file is removed from disk between the
        # /report spool-hit check and the client's actual download request
        # (TTL sweep, cleanup_expired_spool orphan reap, or a rollback rm).
        parquet_path.unlink()
        assert not parquet_path.exists()

        with (
            patch(
                "mes_dashboard.routes.spool_routes.get_spool_file_path",
                return_value=str(parquet_path),
            ),
            patch(
                "mes_dashboard.routes.spool_routes.should_enforce_csrf",
                return_value=False,
            ),
        ):
            dl_resp = client.get(spool_url)

        assert dl_resp.status_code == 410, (
            f"Late-spool race must degrade to 410, got {dl_resp.status_code}: {dl_resp.data!r}"
        )
        dl_data = dl_resp.get_json()
        assert dl_data["success"] is False


# ── heavy_query_slot semaphore contention ─────────────────────────────────────

class TestHeavyQuerySlotContention:
    """global_concurrency.heavy_query_slot() is advisory/fail-open (never a
    hard gate for the calling job itself) -- verify ProductionAchievementJob
    still completes when the cap is already reached, and never
    double-releases a slot it never counted."""

    def _make_empty_result_job(self, tmp_path, monkeypatch, job_id: str):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        def _empty_chunk_iter(self, sql, params, chunk_size=10000):
            return iter(())  # zero Oracle rows -- valid empty-result path

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _empty_chunk_iter,
        )

        from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob

        return ProductionAchievementJob(
            job_id=job_id,
            params={"start_date": "2026-04-01", "end_date": "2026-04-01"},
        )

    def test_run_completes_when_slot_at_capacity_fail_open(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.core.global_concurrency.acquire_heavy_query_slot",
            lambda owner_id, ttl=600: False,  # simulate HEAVY_QUERY_MAX_CONCURRENT already reached
        )
        release_calls: list[str] = []
        monkeypatch.setattr(
            "mes_dashboard.core.global_concurrency.release_heavy_query_slot",
            lambda owner_id: release_calls.append(owner_id),
        )

        job = self._make_empty_result_job(tmp_path, monkeypatch, "pa-slot-contended-001")
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

        job = self._make_empty_result_job(tmp_path, monkeypatch, "pa-slot-contended-002")
        job.run()

        assert release_calls == [], (
            "A job that never counted against the semaphore (acquired=False) "
            f"must never call release_heavy_query_slot (would erroneously "
            f"decrement another job's slot): {release_calls}"
        )

    def test_run_acquires_and_releases_when_slot_available(self, tmp_path, monkeypatch):
        """Control case: when the slot IS available, it is acquired and
        released exactly once around the Oracle fan-out (contrast with the
        at-capacity fail-open case above)."""
        acquire_calls: list[str] = []
        release_calls: list[str] = []

        def _acquire(owner_id, ttl=600):
            acquire_calls.append(owner_id)
            return True

        def _release(owner_id):
            release_calls.append(owner_id)

        monkeypatch.setattr("mes_dashboard.core.global_concurrency.acquire_heavy_query_slot", _acquire)
        monkeypatch.setattr("mes_dashboard.core.global_concurrency.release_heavy_query_slot", _release)

        job = self._make_empty_result_job(tmp_path, monkeypatch, "pa-slot-available-001")
        job.run()

        assert acquire_calls == ["production_achievement:pa-slot-available-001"]
        assert release_calls == ["production_achievement:pa-slot-available-001"]
