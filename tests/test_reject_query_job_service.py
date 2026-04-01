# -*- coding: utf-8 -*-
"""Unit tests for reject_query_job_service (Task 3.4).

Covers:
- should_use_async(): date_range >10 days + async available → True;
  container mode → False; <=10 days → False; REJECT_ASYNC_ENABLED=false → False;
  async not available → False
- enqueue_reject_query(): delegates to enqueue_job with correct args;
  returns (job_id, None) on success; returns (None, error) on failure
- execute_reject_query_job(): cache hit skips Oracle; success calls _execute_and_spool
  then complete_job; exception path calls complete_job with error and re-raises
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

import mes_dashboard.services.reject_query_job_service as rjs


# ---------------------------------------------------------------------------
# should_use_async
# ---------------------------------------------------------------------------

class TestShouldUseAsync:
    def test_true_for_date_range_over_threshold_when_async_available(self):
        """Should return True for date_range with >10 day span when async is available."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "REJECT_ASYNC_DAY_THRESHOLD", 10), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("date_range", "2024-01-01", "2024-01-20")
        assert result is True

    def test_false_for_container_mode(self):
        """Should return False immediately for container mode regardless of dates."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("container", "2024-01-01", "2024-02-01")
        assert result is False

    def test_false_when_range_is_exactly_at_threshold(self):
        """Should return False when days == REJECT_ASYNC_DAY_THRESHOLD (not strictly greater)."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "REJECT_ASYNC_DAY_THRESHOLD", 10), \
             patch.object(rjs, "is_async_available", return_value=True):
            # 10 days exactly
            result = rjs.should_use_async("date_range", "2024-01-01", "2024-01-11")
        assert result is False

    def test_false_when_range_is_below_threshold(self):
        """Should return False when the date range is shorter than the threshold."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "REJECT_ASYNC_DAY_THRESHOLD", 10), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("date_range", "2024-01-01", "2024-01-05")
        assert result is False

    def test_false_when_reject_async_enabled_is_false(self):
        """Should return False when REJECT_ASYNC_ENABLED is False regardless of other conditions."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", False), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("date_range", "2024-01-01", "2024-02-01")
        assert result is False

    def test_false_when_async_not_available(self):
        """Should return False when is_async_available() returns False even if range is large."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "REJECT_ASYNC_DAY_THRESHOLD", 10), \
             patch.object(rjs, "is_async_available", return_value=False):
            result = rjs.should_use_async("date_range", "2024-01-01", "2024-03-01")
        assert result is False

    def test_false_when_start_date_is_missing(self):
        """Should return False when start_date is None."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("date_range", None, "2024-02-01")
        assert result is False

    def test_false_when_end_date_is_missing(self):
        """Should return False when end_date is None."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("date_range", "2024-01-01", None)
        assert result is False

    def test_false_when_dates_are_invalid_format(self):
        """Should return False when date strings cannot be parsed as ISO dates."""
        with patch.object(rjs, "REJECT_ASYNC_ENABLED", True), \
             patch.object(rjs, "is_async_available", return_value=True):
            result = rjs.should_use_async("date_range", "not-a-date", "also-bad")
        assert result is False


# ---------------------------------------------------------------------------
# enqueue_reject_query
# ---------------------------------------------------------------------------

class TestEnqueueRejectQuery:
    def test_delegates_to_enqueue_job_with_correct_arguments(self):
        """Should call enqueue_job with queue_name, worker_fn, prefix=reject, and job kwargs."""
        mock_enqueue_job = MagicMock(return_value=("reject-abc123", None))
        params = {"start_date": "2024-01-01", "end_date": "2024-02-01"}

        with patch.object(rjs, "enqueue_job", mock_enqueue_job):
            job_id, err = rjs.enqueue_reject_query("date_range", params)

        assert job_id == "reject-abc123"
        assert err is None
        mock_enqueue_job.assert_called_once()

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["queue_name"] == rjs.REJECT_WORKER_QUEUE
        assert call_kwargs["worker_fn"] is rjs.execute_reject_query_job
        assert call_kwargs["prefix"] == "reject"
        assert call_kwargs["kwargs"]["mode"] == "date_range"
        assert call_kwargs["kwargs"]["params"] is params

    def test_returns_job_id_and_none_on_success(self):
        """Should return (job_id, None) when enqueue_job succeeds."""
        with patch.object(rjs, "enqueue_job", return_value=("reject-deadbeef", None)):
            job_id, err = rjs.enqueue_reject_query("date_range", {})
        assert job_id is not None
        assert job_id.startswith("reject-")
        assert err is None

    def test_returns_none_and_error_on_failure(self):
        """Should return (None, error_message) when enqueue_job fails."""
        with patch.object(rjs, "enqueue_job", return_value=(None, "Redis down")):
            job_id, err = rjs.enqueue_reject_query("date_range", {})
        assert job_id is None
        assert err == "Redis down"

    def test_job_id_prefixed_with_reject(self):
        """The job_id passed to enqueue_job should start with 'reject-'."""
        captured = {}

        def _capture(**kwargs):
            captured["job_id"] = kwargs.get("job_id")
            return (kwargs.get("job_id"), None)

        with patch.object(rjs, "enqueue_job", side_effect=_capture):
            rjs.enqueue_reject_query("date_range", {})

        assert captured["job_id"].startswith("reject-")

    def test_passes_ttl_and_timeout_from_config(self):
        """Should pass job_timeout and result_ttl from module-level config."""
        mock_enqueue_job = MagicMock(return_value=("reject-ttl-test", None))
        with patch.object(rjs, "enqueue_job", mock_enqueue_job):
            rjs.enqueue_reject_query("date_range", {})

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["job_timeout"] == rjs.REJECT_JOB_TIMEOUT_SECONDS
        assert call_kwargs["result_ttl"] == rjs.REJECT_JOB_TTL_SECONDS

    def test_passes_retry_configuration_to_enqueue_job(self):
        """Should pass retry config through to shared enqueue_job."""
        mock_enqueue_job = MagicMock(return_value=("reject-retry-test", None))
        retry_cfg = object()
        with patch.object(rjs, "enqueue_job", mock_enqueue_job), \
             patch.object(rjs, "_build_retry", return_value=retry_cfg):
            rjs.enqueue_reject_query("date_range", {})

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["retry"] is retry_cfg


# ---------------------------------------------------------------------------
# execute_reject_query_job
# ---------------------------------------------------------------------------

class TestExecuteRejectQueryJob:
    """Tests for the RQ worker entry-point function."""

    def _make_mock_cache_module(self, cache_hit=False):
        """Return a MagicMock for reject_dataset_cache."""
        mock_cache = MagicMock()
        mock_cache._CACHE_SCHEMA_VERSION = "v5"
        mock_cache._has_cached_df.return_value = cache_hit
        mock_cache._make_query_id.return_value = "qry-test-id-001"
        mock_cache.execute_primary_query.return_value = None
        mock_cache.RejectPrimaryQueryOverloadError = Exception
        return mock_cache

    def test_cache_hit_skips_oracle_and_calls_complete_job(self):
        """When cache already has data, skip Oracle and call complete_job immediately."""
        mock_cache = self._make_mock_cache_module(cache_hit=True)
        mock_qb = MagicMock()

        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()

        with patch.dict("sys.modules", {
            "mes_dashboard.services.reject_dataset_cache": mock_cache,
            "mes_dashboard.sql": mock_qb,
        }), \
        patch.object(rjs, "complete_job", mock_complete_job), \
        patch.object(rjs, "update_job_progress", mock_update_progress):
            rjs.execute_reject_query_job(
                job_id="reject-cache-hit",
                mode="date_range",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        mock_cache.execute_primary_query.assert_not_called()
        mock_complete_job.assert_called_once_with(
            "reject", "reject-cache-hit", query_id="qry-test-id-001"
        )

    def test_successful_execution_calls_execute_primary_query_then_complete(self):
        """Happy path: execute_primary_query is called and complete_job is called with query_id."""
        mock_cache = self._make_mock_cache_module(cache_hit=False)
        mock_qb = MagicMock()

        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()

        with patch.dict("sys.modules", {
            "mes_dashboard.services.reject_dataset_cache": mock_cache,
            "mes_dashboard.sql": mock_qb,
        }), \
        patch.object(rjs, "complete_job", mock_complete_job), \
        patch.object(rjs, "update_job_progress", mock_update_progress):
            rjs.execute_reject_query_job(
                job_id="reject-success",
                mode="date_range",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        mock_cache.execute_primary_query.assert_called_once()
        mock_complete_job.assert_called_once_with(
            "reject", "reject-success", query_id="qry-test-id-001"
        )

    def test_failure_path_calls_complete_job_with_error_and_reraises(self):
        """When execute_primary_query raises, complete_job is called with error and exception re-raised."""
        mock_cache = self._make_mock_cache_module(cache_hit=False)
        mock_cache.execute_primary_query.side_effect = RuntimeError("ORA-timeout")
        mock_qb = MagicMock()

        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()

        with patch.dict("sys.modules", {
            "mes_dashboard.services.reject_dataset_cache": mock_cache,
            "mes_dashboard.sql": mock_qb,
        }), \
        patch.object(rjs, "complete_job", mock_complete_job), \
        patch.object(rjs, "update_job_progress", mock_update_progress):
            with pytest.raises(RuntimeError, match="ORA-timeout"):
                rjs.execute_reject_query_job(
                    job_id="reject-fail",
                    mode="date_range",
                    params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
                )

        mock_complete_job.assert_called_once()
        complete_call_kwargs = mock_complete_job.call_args
        assert complete_call_kwargs.args[0] == "reject"
        assert complete_call_kwargs.args[1] == "reject-fail"
        assert complete_call_kwargs.kwargs.get("error") is not None
        assert "ORA-timeout" in complete_call_kwargs.kwargs["error"]

    def test_execute_primary_query_called_with_correct_params(self):
        """execute_primary_query should receive all params from the job payload."""
        mock_cache = self._make_mock_cache_module(cache_hit=False)
        mock_qb = MagicMock()

        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()

        with patch.dict("sys.modules", {
            "mes_dashboard.services.reject_dataset_cache": mock_cache,
            "mes_dashboard.sql": mock_qb,
        }), \
        patch.object(rjs, "complete_job", mock_complete_job), \
        patch.object(rjs, "update_job_progress", mock_update_progress):
            rjs.execute_reject_query_job(
                job_id="reject-params",
                mode="date_range",
                params={"start_date": "2024-01-01", "end_date": "2024-03-01"},
            )

        mock_cache.execute_primary_query.assert_called_once()
        call_kwargs = mock_cache.execute_primary_query.call_args.kwargs
        assert call_kwargs.get("mode") == "date_range"
        assert call_kwargs.get("start_date") == "2024-01-01"
        assert call_kwargs.get("end_date") == "2024-03-01"

    def test_failure_on_query_still_calls_complete_job(self):
        """Even when execute_primary_query raises ValueError, complete_job is called with error."""
        mock_cache = self._make_mock_cache_module(cache_hit=False)
        mock_cache.execute_primary_query.side_effect = ValueError("bad data")
        mock_qb = MagicMock()

        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()

        with patch.dict("sys.modules", {
            "mes_dashboard.services.reject_dataset_cache": mock_cache,
            "mes_dashboard.sql": mock_qb,
        }), \
        patch.object(rjs, "complete_job", mock_complete_job), \
        patch.object(rjs, "update_job_progress", mock_update_progress):
            with pytest.raises(ValueError):
                rjs.execute_reject_query_job(
                    job_id="reject-slot-fail",
                    mode="date_range",
                    params={"start_date": "2024-01-01", "end_date": "2024-03-01"},
                )

        mock_complete_job.assert_called_once()
        assert mock_complete_job.call_args.kwargs.get("error") is not None

    def test_job_completes_regardless_of_mode_parameter(self):
        """execute_reject_query_job should attempt execution for any mode value."""
        mock_cache = self._make_mock_cache_module(cache_hit=False)
        mock_qb = MagicMock()

        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()

        with patch.dict("sys.modules", {
            "mes_dashboard.services.reject_dataset_cache": mock_cache,
            "mes_dashboard.sql": mock_qb,
        }), \
        patch.object(rjs, "complete_job", mock_complete_job), \
        patch.object(rjs, "update_job_progress", mock_update_progress):
            rjs.execute_reject_query_job(
                job_id="reject-any-mode",
                mode="lot_id",
                params={"start_date": "2024-01-01", "end_date": "2024-03-01"},
            )

        mock_complete_job.assert_called_once()
