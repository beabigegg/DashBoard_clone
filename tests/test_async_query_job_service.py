# -*- coding: utf-8 -*-
"""Unit tests for async_query_job_service (Task 2.3).

Covers:
- is_async_available(): RQ+Redis up, Redis unavailable, no workers, TTL cache
- enqueue_job(): success path, RQ unavailable, Redis unavailable, enqueue exception
- get_job_status(): missing job, existing job field mapping, elapsed_seconds
- update_job_progress(): happy path, Redis unavailable
- complete_job(): completed with query_id, failed with error, Redis unavailable
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch


import mes_dashboard.services.async_query_job_service as svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_rq_cache():
    """Reset module-level RQ availability caches between tests."""
    svc._RQ_AVAILABLE = None
    svc._rq_health_cache["available"] = None
    svc._rq_health_cache["checked_at"] = 0.0
    with svc._FAILED_JOB_LOCK:
        svc._FAILED_JOB_COUNT = 0


# ---------------------------------------------------------------------------
# is_async_available
# ---------------------------------------------------------------------------

class TestIsAsyncAvailable:
    def setup_method(self):
        _reset_rq_cache()

    def test_returns_true_when_rq_installed_redis_up_workers_exist(self):
        """Should return True when RQ is installed, Redis pings OK, and workers are present."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.return_value = [MagicMock()]
            svc._RQ_AVAILABLE = True
            result = svc.is_async_available()
        assert result is True

    def test_returns_false_when_redis_unavailable(self):
        """Should return False when get_redis_client() returns None."""
        svc._RQ_AVAILABLE = True
        with patch.object(svc, "get_redis_client", return_value=None):
            result = svc.is_async_available()
        assert result is False

    def test_returns_false_when_redis_ping_fails(self):
        """Should return False when Redis ping raises an exception."""
        svc._RQ_AVAILABLE = True
        mock_conn = MagicMock()
        mock_conn.ping.side_effect = ConnectionError("refused")
        with patch.object(svc, "get_redis_client", return_value=mock_conn):
            result = svc.is_async_available()
        assert result is False

    def test_returns_false_when_no_workers(self):
        """Should return False when no RQ workers are registered."""
        svc._RQ_AVAILABLE = True
        mock_conn = MagicMock()
        with patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.return_value = []
            result = svc.is_async_available()
        assert result is False

    def test_returns_false_when_rq_not_installed(self):
        """Should return False immediately when RQ is not installed."""
        svc._RQ_AVAILABLE = None
        with patch.object(svc, "_check_rq_installed", return_value=False):
            result = svc.is_async_available()
        assert result is False

    def test_ttl_cache_returns_cached_value_within_window(self):
        """Should return cached True without re-checking Redis within TTL window."""
        svc._RQ_AVAILABLE = True
        svc._rq_health_cache["available"] = True
        svc._rq_health_cache["checked_at"] = time.monotonic()

        mock_get_redis = MagicMock()
        with patch.object(svc, "get_redis_client", mock_get_redis):
            result = svc.is_async_available()

        assert result is True
        mock_get_redis.assert_not_called()

    def test_ttl_cache_refreshes_after_expiry(self):
        """Should re-check Redis once the TTL window has passed."""
        svc._RQ_AVAILABLE = True
        svc._rq_health_cache["available"] = True
        # Simulate cache expired (checked more than TTL seconds ago)
        svc._rq_health_cache["checked_at"] = time.monotonic() - svc._RQ_HEALTH_TTL_SECONDS - 1

        mock_conn = MagicMock()
        with patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.return_value = [MagicMock()]
            result = svc.is_async_available()

        assert result is True
        mock_conn.ping.assert_called_once()

    def test_returns_false_when_worker_query_raises(self):
        """Should return False when rq.Worker.all() raises an unexpected exception."""
        svc._RQ_AVAILABLE = True
        mock_conn = MagicMock()
        with patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.side_effect = RuntimeError("Redis NOSCRIPT")
            result = svc.is_async_available()
        assert result is False


# ---------------------------------------------------------------------------
# enqueue_job
# ---------------------------------------------------------------------------

class TestEnqueueJob:
    def setup_method(self):
        _reset_rq_cache()

    def test_returns_job_id_on_success(self):
        """Should return (job_id, None) and write initial HSET metadata."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()

        def _worker_fn(**kwargs):
            pass

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            job_id, err = svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=_worker_fn,
                owner="test-owner",
                kwargs={"foo": "bar"},
                prefix="async",
            )

        assert job_id is not None
        assert err is None
        assert "test-queue" in job_id
        mock_conn.hset.assert_called_once()
        mock_conn.expire.assert_called_once()
        mock_queue.enqueue.assert_called_once()

    def test_initial_metadata_has_queued_status(self):
        """The initial Redis HSET call should include status=queued."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()

        def _worker_fn(**kwargs):
            pass

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=_worker_fn,
                owner="test-owner",
                prefix="async",
            )

        hset_call = mock_conn.hset.call_args
        mapping = hset_call.kwargs.get("mapping") or hset_call[1].get("mapping")
        assert mapping["status"] == "queued"
        assert mapping["queue_name"] == "test-queue"
        assert mapping["owner"] == "test-owner"
        assert mapping["error"] == ""

    def test_returns_none_error_when_rq_not_installed(self):
        """Should return (None, error) immediately when RQ is not installed."""
        with patch.object(svc, "_check_rq_installed", return_value=False):
            job_id, err = svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=lambda: None,
                owner="test-owner",
            )
        assert job_id is None
        assert err is not None
        assert "RQ" in err or "unavailable" in err.lower()

    def test_returns_none_error_when_redis_unavailable(self):
        """Should return (None, error) when control Redis client is unavailable."""
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=None):
            job_id, err = svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=lambda: None,
                owner="test-owner",
            )
        assert job_id is None
        assert err is not None
        assert "unavailable" in err.lower()

    def test_returns_none_error_when_queue_enqueue_raises(self):
        """Should return (None, error) and mark status=failed when enqueue raises."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()
        mock_queue.enqueue.side_effect = RuntimeError("broker down")

        def _worker_fn(**kwargs):
            pass

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            job_id, err = svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=_worker_fn,
                owner="test-owner",
            )

        assert job_id is None
        assert "broker down" in err
        # The second hset call should mark job as failed
        second_hset = mock_conn.hset.call_args_list[-1]
        mapping = second_hset.kwargs.get("mapping") or second_hset[1].get("mapping")
        assert mapping["status"] == "failed"

    def test_uses_provided_job_id(self):
        """Should use caller-supplied job_id when provided."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()

        def _worker_fn(**kwargs):
            pass

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            job_id, err = svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=_worker_fn,
                owner="test-owner",
                job_id="my-custom-id",
                prefix="async",
            )

        assert job_id == "my-custom-id"
        assert err is None

    def test_default_retry_enabled_when_not_explicitly_overridden(self):
        """Should pass default Retry config to queue.enqueue by default."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()
        default_retry = object()

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch.object(svc, "_build_default_retry", return_value=default_retry), \
             patch("rq.Queue", return_value=mock_queue):
            svc.enqueue_job(queue_name="test-queue", worker_fn=lambda: None, owner="test-owner")

        enqueue_kwargs = mock_queue.enqueue.call_args.kwargs
        assert enqueue_kwargs["retry"] is default_retry

    def test_retry_can_be_disabled_explicitly(self):
        """Should pass retry=None when caller disables retry."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            svc.enqueue_job(queue_name="test-queue", worker_fn=lambda: None, owner="test-owner", retry=None)

        enqueue_kwargs = mock_queue.enqueue.call_args.kwargs
        assert "retry" in enqueue_kwargs
        assert enqueue_kwargs["retry"] is None

    def test_custom_retry_configuration_is_forwarded(self):
        """Should forward caller-provided retry config to queue.enqueue."""
        mock_conn = MagicMock()
        mock_queue = MagicMock()
        custom_retry = object()

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            svc.enqueue_job(
                queue_name="test-queue",
                worker_fn=lambda: None,
                owner="test-owner",
                retry=custom_retry,
            )

        enqueue_kwargs = mock_queue.enqueue.call_args.kwargs
        assert enqueue_kwargs["retry"] is custom_retry

    def test_default_timeout_is_600_seconds(self):
        """Default timeout should match the hardening requirement (600s)."""
        assert svc.ASYNC_JOB_DEFAULT_TIMEOUT_SECONDS == 600


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------

class TestGetJobStatus:
    def test_returns_none_for_missing_job(self):
        """Should return None when Redis HGETALL returns empty dict."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {}
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("async", "no-such-job")
        assert result is None

    def test_returns_none_when_redis_unavailable(self):
        """Should return None when get_control_redis_client() returns None."""
        with patch.object(svc, "get_control_redis_client", return_value=None):
            result = svc.get_job_status("async", "some-job-id")
        assert result is None

    def test_returns_dict_with_correct_fields_for_existing_job(self):
        """Should return a dict containing all expected fields for a known job."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "running",
            "queue_name": "reject-query",
            "created_at": "1700000000.0",
            "completed_at": "",
            "progress": "querying Oracle",
            "pct": "45",
            "query_id": "",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("reject", "reject-abc123")

        assert result is not None
        assert result["job_id"] == "reject-abc123"
        assert result["status"] == "running"
        assert result["progress"] == "querying Oracle"
        assert result["pct"] == 45
        assert result["error"] is None

    def test_elapsed_seconds_calculated_correctly(self):
        """elapsed_seconds should be positive and consistent with created_at timestamp."""
        fixed_created = time.time() - 30.0
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "running",
            "created_at": str(fixed_created),
            "completed_at": "",
            "progress": "",
            "pct": "",
            "query_id": "",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("async", "job-elapsed-test")

        assert result is not None
        assert 25.0 <= result["elapsed_seconds"] <= 40.0

    def test_includes_query_id_for_completed_job(self):
        """Should include query_id in result when the job has completed."""
        mock_conn = MagicMock()
        completed_at = str(time.time())
        mock_conn.hgetall.return_value = {
            "status": "completed",
            "created_at": str(time.time() - 60),
            "completed_at": completed_at,
            "progress": "",
            "pct": "",
            "query_id": "qry-deadbeef0123",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("reject", "job-done")

        assert result["status"] == "completed"
        assert result["query_id"] == "qry-deadbeef0123"
        assert "completed_at" in result

    def test_error_field_populated_for_failed_job(self):
        """Should surface the error string for a failed job."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "failed",
            "created_at": str(time.time() - 10),
            "completed_at": str(time.time()),
            "progress": "",
            "pct": "",
            "query_id": "",
            "error": "ORA-01555: snapshot too old",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("reject", "job-fail")

        assert result["status"] == "failed"
        assert result["error"] == "ORA-01555: snapshot too old"

    def test_pct_omitted_when_empty(self):
        """pct should not appear in result when Redis field is empty string."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "queued",
            "created_at": str(time.time()),
            "completed_at": "",
            "progress": "",
            "pct": "",
            "query_id": "",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("async", "queued-job")

        assert "pct" not in result


# ---------------------------------------------------------------------------
# update_job_progress
# ---------------------------------------------------------------------------

class TestUpdateJobProgress:
    def test_writes_fields_to_redis_hset(self):
        """Should call hset on the correct meta key with stringified field values."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.update_job_progress("reject", "job-prog-1", status="running", progress="50%", pct=50)

        mock_conn.hset.assert_called_once()
        call_kwargs = mock_conn.hset.call_args
        mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
        assert mapping["status"] == "running"
        assert mapping["progress"] == "50%"
        assert mapping["pct"] == "50"

    def test_silently_returns_when_redis_unavailable(self):
        """Should not raise when get_control_redis_client() returns None."""
        with patch.object(svc, "get_control_redis_client", return_value=None):
            svc.update_job_progress("reject", "job-no-redis", status="running")
        # No exception = pass

    def test_silently_handles_hset_error(self):
        """Should not raise when Redis hset itself throws."""
        mock_conn = MagicMock()
        mock_conn.hset.side_effect = ConnectionError("pipe broken")
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.update_job_progress("reject", "job-err", status="running")
        # No exception = pass


# ---------------------------------------------------------------------------
# complete_job
# ---------------------------------------------------------------------------

class TestCompleteJob:
    def setup_method(self):
        _reset_rq_cache()

    def test_sets_status_completed_with_query_id(self):
        """Should write status=completed and query_id when no error is given."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.complete_job("reject", "job-ok", query_id="qry-abc123")

        mock_conn.hset.assert_called_once()
        call_kwargs = mock_conn.hset.call_args
        mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
        assert mapping["status"] == "completed"
        assert mapping["query_id"] == "qry-abc123"
        assert "completed_at" in mapping

    def test_sets_status_failed_with_error_message(self):
        """Should write status=failed and error message when error is provided."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.complete_job("reject", "job-fail", error="ORA-00942: table not found")

        mock_conn.hset.assert_called_once()
        call_kwargs = mock_conn.hset.call_args
        mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
        assert mapping["status"] == "failed"
        assert mapping["error"] == "ORA-00942: table not found"
        assert "completed_at" in mapping

    def test_completed_at_is_recent_timestamp(self):
        """completed_at value written to Redis should be a recent Unix timestamp."""
        mock_conn = MagicMock()
        before = time.time()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.complete_job("reject", "job-ts", query_id="q1")
        after = time.time()

        call_kwargs = mock_conn.hset.call_args
        mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
        completed_at = float(mapping["completed_at"])
        assert before <= completed_at <= after

    def test_silently_returns_when_redis_unavailable(self):
        """Should not raise when get_control_redis_client() returns None."""
        with patch.object(svc, "get_control_redis_client", return_value=None):
            svc.complete_job("reject", "job-no-redis", query_id="q1")
        # No exception = pass

    def test_handles_none_query_id(self):
        """Should store empty string for query_id when None is passed."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.complete_job("reject", "job-noqid", query_id=None)

        call_kwargs = mock_conn.hset.call_args
        mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
        assert mapping["status"] == "completed"
        assert mapping["query_id"] == ""

    def test_failure_increments_failed_job_counter_and_logs_warning(self):
        """Failed completion path should log warning and increment counter."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "logger") as mock_logger:
            svc.complete_job("reject", "job-fail-counter", error="DB timeout")

        assert svc.get_failed_job_count() == 1
        assert any(
            call.args and call.args[0] == "Job failed: prefix=%s job_id=%s error=%s"
            for call in mock_logger.warning.call_args_list
        )


# ---------------------------------------------------------------------------
# Task 4.3 — multi-stage progress and compatibility fields
# ---------------------------------------------------------------------------

class TestMultiStageProgress:
    """Verify stage-aware progress fields in enqueue_job / get_job_status."""

    def test_enqueue_job_includes_stage_fields_in_initial_meta(self):
        """Initial job metadata must include stage and completed_stages keys."""
        mock_conn = MagicMock()
        mock_conn.ping.return_value = True
        mock_queue = MagicMock()

        with patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch.object(svc, "_check_rq_installed", return_value=True), \
             patch("rq.Queue", return_value=mock_queue):
            svc.enqueue_job(queue_name="test-queue", worker_fn=lambda: None, owner="test-owner", prefix="test")

        hset_call = mock_conn.hset.call_args
        mapping = hset_call.kwargs.get("mapping") or hset_call[1].get("mapping")
        assert "stage" in mapping
        assert "completed_stages" in mapping
        assert "dataset_id" in mapping

    def test_update_job_progress_with_stage_stores_correctly(self):
        """update_job_progress with stage should store it in Redis HSET."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.update_job_progress(
                "test",
                "job-stage-001",
                status="running",
                stage="lineage",
                pct="60",
                completed_stages="seed_detection",
            )

        hset_call = mock_conn.hset.call_args
        mapping = hset_call.kwargs.get("mapping") or hset_call[1].get("mapping")
        assert mapping["stage"] == "lineage"
        assert mapping["completed_stages"] == "seed_detection"
        assert mapping["pct"] == "60"

    def test_get_job_status_returns_stage_and_completed_stages(self):
        """get_job_status must return stage and completed_stages when present."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "running",
            "stage": "events",
            "completed_stages": "seed_detection,lineage",
            "progress": "aggregating events",
            "pct": "75",
            "created_at": str(time.time() - 30),
            "completed_at": "",
            "query_id": "",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("test", "job-stage-001")

        assert result is not None
        assert result["stage"] == "events"
        assert result["completed_stages"] == ["seed_detection", "lineage"]
        assert result["pct"] == 75

    def test_get_job_status_returns_dataset_id_when_present(self):
        """get_job_status must return dataset_id for completed jobs."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "completed",
            "stage": "",
            "completed_stages": "",
            "progress": "",
            "pct": "",
            "created_at": str(time.time() - 5),
            "completed_at": str(time.time()),
            "query_id": "msd-abc12345",
            "dataset_id": "ds-abc12345",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("test", "job-complete-001")

        assert result is not None
        assert result["query_id"] == "msd-abc12345"
        assert result["dataset_id"] == "ds-abc12345"

    def test_complete_job_stores_dataset_id(self):
        """complete_job should persist dataset_id when provided."""
        mock_conn = MagicMock()
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            svc.complete_job("test", "job-ds-001", query_id="msd-abc", dataset_id="ds-abc")

        hset_call = mock_conn.hset.call_args
        mapping = hset_call.kwargs.get("mapping") or hset_call[1].get("mapping")
        assert mapping["dataset_id"] == "ds-abc"
        assert mapping["query_id"] == "msd-abc"
        assert mapping["status"] == "completed"

    def test_completed_stages_empty_not_in_result(self):
        """get_job_status should omit completed_stages when field is empty."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "queued",
            "stage": "",
            "completed_stages": "",
            "created_at": str(time.time()),
            "completed_at": "",
            "query_id": "",
            "error": "",
        }
        with patch.object(svc, "get_control_redis_client", return_value=mock_conn):
            result = svc.get_job_status("test", "job-queued-001")

        assert result is not None
        assert "stage" not in result
        assert "completed_stages" not in result
