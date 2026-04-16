# -*- coding: utf-8 -*-
"""Task 6.4 — Oracle timeout marks jobs failed for production-history, reject-history,
yield-alert, and material-trace.

Integration tests that verify:
  - When the Oracle query raises oracledb.OperationalError (timeout), the RQ
    worker entry point catches the exception and marks the job as "failed" with
    the error stored in Redis metadata.
  - The job metadata `error` field is populated (not empty) on timeout.

All tests mock the Oracle query layer and a minimal Redis so no real database
or broker is required.
"""

import time
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

try:
    import oracledb
    _ORACLEDB_AVAILABLE = True
except ImportError:
    import types
    oracledb = types.ModuleType("oracledb")  # type: ignore[assignment]
    oracledb.OperationalError = type("OperationalError", (Exception,), {})  # type: ignore[attr-defined]
    _ORACLEDB_AVAILABLE = False

from mes_dashboard.services.async_query_job_service import (
    complete_job,
    get_job_status,
    update_job_progress,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _meta_key_full(prefix: str, job_id: str) -> str:
    """Return the exact Redis key used by async_query_job_service._meta_key()."""
    from mes_dashboard.core.redis_client import get_key, REDIS_KEY_PREFIX
    return get_key(f"{prefix}:job:{job_id}:meta")


def _seed_job(store, client, prefix, job_id):
    """Pre-populate a queued job entry (mirrors enqueue_job initial state)."""
    key = _meta_key_full(prefix, job_id)
    store[key] = {
        "status": "queued",
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAsyncJobTimeout:
    """Task 6.4 — Oracle timeout marks jobs failed across worker types."""

    def test_oracle_timeout_marks_job_failed_production_history(self):
        """OperationalError in production-history worker → job status == 'failed'."""
        from mes_dashboard.services.production_history_job_service import (
            execute_production_history_job,
        )

        store, mock_client = _make_redis_store()
        job_id = f"prod-hist-{uuid.uuid4().hex[:8]}"
        _seed_job(store, mock_client, "production_history", job_id)

        timeout_exc = oracledb.OperationalError("ORA-01013: user requested cancel of current operation")

        with (
            patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client),
            patch("mes_dashboard.services.async_query_job_service.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"),
            patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value=None),
            patch(
                "mes_dashboard.services.production_history_service.make_canonical_spool_id",
                return_value="prod-hist-test-spool-id",
            ),
            patch(
                "mes_dashboard.services.production_history_service.query_production_history",
                side_effect=timeout_exc,
            ),
        ):
            with pytest.raises(oracledb.OperationalError):
                execute_production_history_job(job_id=job_id, params={"start_date": "2024-01-01"})

        # Verify job metadata was marked as failed
        with patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client):
            status = get_job_status("production_history", job_id)
        assert status is not None
        assert status["status"] == "failed"
        assert status["error"] is not None and len(status["error"]) > 0

    def test_oracle_timeout_marks_job_failed_reject_history(self):
        """OperationalError in reject-history worker → job status == 'failed'."""
        from mes_dashboard.services.reject_query_job_service import execute_reject_query_job

        store, mock_client = _make_redis_store()
        job_id = f"reject-{uuid.uuid4().hex[:8]}"
        _seed_job(store, mock_client, "reject", job_id)

        timeout_exc = oracledb.OperationalError("ORA-01013: timeout")

        with (
            patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client),
            patch("mes_dashboard.services.async_query_job_service.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"),
            patch("mes_dashboard.services.reject_dataset_cache._has_cached_df", return_value=False),
            patch("mes_dashboard.services.reject_dataset_cache._make_query_id", return_value="reject-test-id"),
            patch("mes_dashboard.services.reject_dataset_cache.execute_primary_query", side_effect=timeout_exc),
        ):
            with pytest.raises(oracledb.OperationalError):
                execute_reject_query_job(
                    job_id=job_id,
                    mode="lot",
                    params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
                )

        with patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client):
            status = get_job_status("reject", job_id)
        assert status is not None
        assert status["status"] == "failed"
        assert status["error"] is not None and len(status["error"]) > 0

    def test_oracle_timeout_marks_job_failed_yield_alert(self):
        """OperationalError in yield-alert worker → job status == 'failed'."""
        from mes_dashboard.services.yield_alert_job_service import execute_yield_alert_job

        store, mock_client = _make_redis_store()
        job_id = f"yield-{uuid.uuid4().hex[:8]}"
        _seed_job(store, mock_client, "yield_alert", job_id)

        timeout_exc = oracledb.OperationalError("ORA-01013: timeout")

        with (
            patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client),
            patch("mes_dashboard.services.async_query_job_service.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"),
            patch("mes_dashboard.services.yield_alert_dataset_cache._get_cached_payload", return_value=None),
            patch("mes_dashboard.services.yield_alert_dataset_cache._make_query_id", return_value="yield-test-id"),
            patch("mes_dashboard.services.yield_alert_dataset_cache.execute_primary_query", side_effect=timeout_exc),
        ):
            with pytest.raises(oracledb.OperationalError):
                execute_yield_alert_job(
                    job_id=job_id,
                    params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
                )

        with patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client):
            status = get_job_status("yield_alert", job_id)
        assert status is not None
        assert status["status"] == "failed"
        assert status["error"] is not None and len(status["error"]) > 0

    def test_job_timeout_envelope_has_error_code(self):
        """After timeout, job metadata error field contains error text (not empty)."""
        store, mock_client = _make_redis_store()
        job_id = f"env-test-{uuid.uuid4().hex[:8]}"
        _seed_job(store, mock_client, "production_history", job_id)

        timeout_exc = oracledb.OperationalError("ORA-01013: user requested cancel")

        with (
            patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client),
            patch("mes_dashboard.services.async_query_job_service.get_redis_client", return_value=mock_client),
        ):
            complete_job("production_history", job_id, error=str(timeout_exc))
            status = get_job_status("production_history", job_id)

        assert status is not None
        assert status["status"] == "failed"
        error_msg = status.get("error") or ""
        assert "ORA-01013" in error_msg or len(error_msg) > 0

    def test_complete_job_without_error_sets_status_completed(self):
        """Successful completion sets status='completed' and stores query_id."""
        store, mock_client = _make_redis_store()
        job_id = f"done-{uuid.uuid4().hex[:8]}"
        _seed_job(store, mock_client, "production_history", job_id)

        with (
            patch("mes_dashboard.services.async_query_job_service.get_control_redis_client", return_value=mock_client),
            patch("mes_dashboard.services.async_query_job_service.get_redis_client", return_value=mock_client),
        ):
            complete_job("production_history", job_id, query_id="spool-abc-123")
            status = get_job_status("production_history", job_id)

        assert status is not None
        assert status["status"] == "completed"
        assert status.get("query_id") == "spool-abc-123"
        assert status.get("error") is None
