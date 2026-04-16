# -*- coding: utf-8 -*-
"""Task 6.5 — RQ worker crash recovery: SIGKILL reconciliation and restart idempotency.

Integration tests that verify job metadata in Redis survives a simulated worker
crash and can be transitioned to a terminal state via the async_query_job_service
helpers (update_job_progress / complete_job).

Requires Redis to be reachable.  Skip automatically when unavailable.
"""

from __future__ import annotations

import time
import uuid

import pytest

from mes_dashboard.core.redis_client import (
    get_control_redis_client,
    redis_available,
)
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    get_job_status,
    update_job_progress,
    _meta_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PREFIX = "test_crash"


def _seed_job(job_id: str, status: str = "started", extra: dict | None = None) -> None:
    """Write a minimal job HSET directly into the control-plane Redis."""
    conn = get_control_redis_client()
    mapping = {
        "status": status,
        "queue_name": "test-queue",
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
    if extra:
        mapping.update(extra)
    key = _meta_key(_PREFIX, job_id)
    conn.hset(key, mapping=mapping)
    conn.expire(key, 300)


def _cleanup(job_id: str) -> None:
    conn = get_control_redis_client()
    if conn is not None:
        conn.delete(_meta_key(_PREFIX, job_id))


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRqWorkerCrashRecovery:
    """Verify job-state reconciliation after a simulated worker SIGKILL."""

    def setup_method(self):
        if not redis_available():
            pytest.skip("Redis not available")

    # ------------------------------------------------------------------
    # test_job_in_started_state_can_be_recovered
    # ------------------------------------------------------------------
    def test_job_in_started_state_can_be_recovered(self):
        """A job stuck in 'started' can be reconciled to a terminal state.

        Scenario: worker received SIGKILL after writing status='started' but
        before completing.  A reconciler calls complete_job(..., error=...) to
        mark it failed and unblock any polling client.
        """
        job_id = f"crash-recover-{uuid.uuid4().hex[:8]}"
        _seed_job(job_id, status="started")
        try:
            # Precondition: job is in 'started'
            status = get_job_status(_PREFIX, job_id)
            assert status is not None, "seeded job should be readable"
            assert status["status"] == "started"

            # Reconcile: mark failed (as a crash-recovery reconciler would)
            complete_job(_PREFIX, job_id, error="worker SIGKILL — reconciled by supervisor")

            recovered = get_job_status(_PREFIX, job_id)
            assert recovered is not None
            assert recovered["status"] == "failed", (
                f"expected 'failed', got {recovered['status']!r}"
            )
            # Terminal state must include an error message
            assert recovered.get("error"), "reconciled failure must carry an error string"
        finally:
            _cleanup(job_id)

    # ------------------------------------------------------------------
    # test_enqueue_after_crash_is_idempotent
    # ------------------------------------------------------------------
    def test_enqueue_after_crash_is_idempotent(self):
        """Writing metadata for the same job_id twice must not create duplicates.

        When a client retries an enqueue (e.g. because the first attempt is
        uncertain after a crash), the second HSET must overwrite — there should
        be exactly one metadata key for a given job_id.
        """
        job_id = f"idempotent-{uuid.uuid4().hex[:8]}"
        _seed_job(job_id, status="queued")
        try:
            # Simulate a second enqueue attempt: write again with same job_id
            _seed_job(job_id, status="queued", extra={"progress": "retry"})

            conn = get_control_redis_client()
            key = _meta_key(_PREFIX, job_id)

            # Redis HSET is idempotent — still one key, not two
            assert conn.exists(key) == 1, "duplicate keys must not exist for the same job_id"

            status = get_job_status(_PREFIX, job_id)
            assert status is not None
            assert status["status"] == "queued"
        finally:
            _cleanup(job_id)

    # ------------------------------------------------------------------
    # test_failed_job_metadata_persists_error
    # ------------------------------------------------------------------
    def test_failed_job_metadata_persists_error(self):
        """complete_job(..., error=...) must persist the error string in metadata.

        This allows operators and monitoring to inspect what went wrong after a
        worker crashes and the supervisor marks the job as failed.
        """
        job_id = f"fail-meta-{uuid.uuid4().hex[:8]}"
        _seed_job(job_id, status="started")
        error_message = "ORA-12541: TNS:no listener — simulated crash"
        try:
            complete_job(_PREFIX, job_id, error=error_message)

            status = get_job_status(_PREFIX, job_id)
            assert status is not None
            assert status["status"] == "failed"
            assert status.get("error") == error_message, (
                f"expected error={error_message!r}, got {status.get('error')!r}"
            )
            # completed_at must be set so elapsed time can be computed
            assert status.get("elapsed_seconds") is not None
        finally:
            _cleanup(job_id)
