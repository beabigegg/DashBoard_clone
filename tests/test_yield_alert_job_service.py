# -*- coding: utf-8 -*-
"""Unit tests for yield_alert_job_service.

Covers:
- enqueue_yield_alert_query(): delegates to enqueue_job with correct args;
  returns (job_id, None) on success; returns (None, error) on failure
- execute_yield_alert_job(): cache hit skips Oracle; success calls
  execute_primary_query then complete_job; exception path calls complete_job
  with error and re-raises
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import mes_dashboard.services.yield_alert_job_service as yajs


# ---------------------------------------------------------------------------
# enqueue_yield_alert_query
# ---------------------------------------------------------------------------

class TestEnqueueYieldAlertQuery:
    def test_delegates_to_enqueue_job_with_correct_arguments(self):
        """Should call enqueue_job with correct queue_name, worker_fn, and prefix."""
        mock_enqueue_job = MagicMock(return_value=("yield-alert-abc123", None))
        params = {"start_date": "2024-01-01", "end_date": "2024-02-01"}

        with patch.object(yajs, "enqueue_job", mock_enqueue_job):
            job_id, err = yajs.enqueue_yield_alert_query(params, owner="test-owner")

        assert job_id == "yield-alert-abc123"
        assert err is None
        mock_enqueue_job.assert_called_once()

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["queue_name"] == yajs.YIELD_ALERT_WORKER_QUEUE
        assert call_kwargs["worker_fn"] is yajs.execute_yield_alert_job
        assert call_kwargs["prefix"] == "yield_alert"
        assert call_kwargs["kwargs"]["params"] is params

    def test_returns_job_id_and_none_on_success(self):
        """Should return (job_id, None) when enqueue_job succeeds."""
        with patch.object(yajs, "enqueue_job", return_value=("yield-alert-deadbeef", None)):
            job_id, err = yajs.enqueue_yield_alert_query({}, owner="test-owner")
        assert job_id is not None
        assert job_id.startswith("yield-alert-")
        assert err is None

    def test_returns_none_and_error_on_failure(self):
        """Should return (None, error_message) when enqueue_job fails."""
        with patch.object(yajs, "enqueue_job", return_value=(None, "Redis down")):
            job_id, err = yajs.enqueue_yield_alert_query({}, owner="test-owner")
        assert job_id is None
        assert err == "Redis down"

    def test_job_id_prefixed_with_yield_alert(self):
        """The job_id passed to enqueue_job should start with 'yield-alert-'."""
        captured = {}

        def _capture(**kwargs):
            captured["job_id"] = kwargs.get("job_id")
            return (kwargs.get("job_id"), None)

        with patch.object(yajs, "enqueue_job", side_effect=_capture):
            yajs.enqueue_yield_alert_query({}, owner="test-owner")

        assert captured["job_id"].startswith("yield-alert-")

    def test_passes_ttl_and_timeout_from_config(self):
        """Should pass job_timeout and result_ttl from module-level config."""
        mock_enqueue_job = MagicMock(return_value=("yield-alert-ttl-test", None))
        with patch.object(yajs, "enqueue_job", mock_enqueue_job):
            yajs.enqueue_yield_alert_query({}, owner="test-owner")

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["job_timeout"] == yajs.YIELD_ALERT_JOB_TIMEOUT_SECONDS
        assert call_kwargs["result_ttl"] == yajs.YIELD_ALERT_JOB_TTL_SECONDS

    def test_passes_retry_configuration_to_enqueue_job(self):
        """Should pass retry config through to shared enqueue_job."""
        mock_enqueue_job = MagicMock(return_value=("yield-alert-retry-test", None))
        retry_cfg = object()
        with patch.object(yajs, "enqueue_job", mock_enqueue_job), \
             patch.object(yajs, "_build_retry", return_value=retry_cfg):
            yajs.enqueue_yield_alert_query({}, owner="test-owner")

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["retry"] is retry_cfg


# ---------------------------------------------------------------------------
# execute_yield_alert_job
# ---------------------------------------------------------------------------

class TestExecuteYieldAlertJob:
    """Tests for the RQ worker entry-point function."""

    def test_cache_hit_skips_oracle_and_calls_complete_job(self):
        """When cache already has data, skip Oracle and call complete_job immediately."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_execute_fn = MagicMock()
        mock_cache_module = MagicMock()
        mock_cache_module._CACHE_SCHEMA_VERSION = 4
        mock_cache_module._make_query_id.return_value = "ya-qid-hit-001"
        mock_cache_module._get_cached_payload.return_value = {"query_id": "ya-qid-hit-001"}
        mock_cache_module.execute_primary_query = mock_execute_fn

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
            "mes_dashboard.services.yield_alert_dataset_cache": mock_cache_module,
        }), \
        patch("mes_dashboard.services.yield_alert_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.yield_alert_job_service.update_job_progress", mock_update_progress):
            yajs.execute_yield_alert_job(
                job_id="yield-alert-cache-hit",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        mock_execute_fn.assert_not_called()
        mock_complete_job.assert_called_once_with(
            "yield_alert", "yield-alert-cache-hit", query_id="ya-qid-hit-001"
        )

    def test_cache_miss_calls_execute_primary_query_then_complete(self):
        """Cache miss: should call execute_primary_query then complete_job."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_execute_fn = MagicMock(return_value={"query_id": "ya-qid-new-001"})
        mock_cache_module = MagicMock()
        mock_cache_module._CACHE_SCHEMA_VERSION = 4
        mock_cache_module._make_query_id.return_value = "ya-qid-new-001"
        mock_cache_module._get_cached_payload.return_value = None  # cache miss
        mock_cache_module.execute_primary_query = mock_execute_fn

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
            "mes_dashboard.services.yield_alert_dataset_cache": mock_cache_module,
        }), \
        patch("mes_dashboard.services.yield_alert_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.yield_alert_job_service.update_job_progress", mock_update_progress):
            yajs.execute_yield_alert_job(
                job_id="yield-alert-cache-miss",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        mock_execute_fn.assert_called_once_with(start_date="2024-01-01", end_date="2024-02-01")
        mock_complete_job.assert_called_once_with(
            "yield_alert", "yield-alert-cache-miss", query_id="ya-qid-new-001"
        )

    def test_failure_path_calls_complete_job_with_error_and_reraises(self):
        """When execute_primary_query raises, complete_job should be called with error and re-raised."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_execute_fn = MagicMock(side_effect=RuntimeError("DB timeout"))
        mock_cache_module = MagicMock()
        mock_cache_module._CACHE_SCHEMA_VERSION = 4
        mock_cache_module._make_query_id.return_value = "ya-qid-fail-001"
        mock_cache_module._get_cached_payload.return_value = None
        mock_cache_module.execute_primary_query = mock_execute_fn

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
            "mes_dashboard.services.yield_alert_dataset_cache": mock_cache_module,
        }), \
        patch("mes_dashboard.services.yield_alert_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.yield_alert_job_service.update_job_progress", mock_update_progress):
            with pytest.raises(RuntimeError, match="DB timeout"):
                yajs.execute_yield_alert_job(
                    job_id="yield-alert-fail",
                    params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
                )

        mock_complete_job.assert_called_once()
        call_kwargs = mock_complete_job.call_args
        assert call_kwargs.args[0] == "yield_alert"
        assert call_kwargs.args[1] == "yield-alert-fail"
        assert call_kwargs.kwargs.get("error") is not None
        assert "DB timeout" in call_kwargs.kwargs["error"]
