# -*- coding: utf-8 -*-
"""Unit tests for msd_query_job_service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import mes_dashboard.services.msd_query_job_service as svc


class TestEnqueueMsdAnalysis:
    @patch.object(svc, "enqueue_job", return_value=("msd-job-1", None))
    def test_enqueue_delegates_to_shared_service(self, mock_enqueue):
        job_id, err = svc.enqueue_msd_analysis(
            start_date="2025-01-01",
            end_date="2025-01-31",
            station="測試",
            direction="backward",
            loss_reasons=["A", "B"],
        )

        assert job_id == "msd-job-1"
        assert err is None
        kwargs = mock_enqueue.call_args.kwargs
        assert kwargs["queue_name"] == svc.MSD_WORKER_QUEUE
        assert kwargs["worker_fn"] is svc._execute_msd_analysis
        assert kwargs["prefix"] == "msd"
        assert kwargs["job_timeout"] == svc.MSD_JOB_TIMEOUT_SECONDS
        assert kwargs["result_ttl"] == svc.MSD_JOB_TTL_SECONDS


class TestExecuteMsdAnalysis:
    @patch.object(svc, "complete_job")
    @patch.object(svc, "cache_set")
    @patch.object(svc, "query_analysis")
    @patch.object(svc, "update_job_progress")
    def test_success_path_stores_cache_and_completes(
        self,
        mock_update,
        mock_query,
        mock_cache_set,
        mock_complete,
    ):
        mock_query.return_value = {
            "kpi": {"total_input": 1},
            "charts": {},
            "daily_trend": [],
            "detail": [],
        }
        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            svc._execute_msd_analysis(
                job_id="msd-job-1",
                start_date="2025-01-01",
                end_date="2025-01-31",
                station="測試",
                direction="backward",
                loss_reasons=["A"],
            )

        assert mock_update.called
        assert mock_cache_set.called
        complete_args = mock_complete.call_args.args
        complete_kwargs = mock_complete.call_args.kwargs
        assert complete_args[0] == "msd"
        assert complete_args[1] == "msd-job-1"
        assert "query_id" in complete_kwargs

    @patch.object(svc, "complete_job")
    @patch.object(svc, "query_analysis", return_value={"error": "invalid range"})
    def test_failure_path_marks_job_failed_and_reraises(self, _mock_query, mock_complete):
        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with pytest.raises(ValueError):
                svc._execute_msd_analysis(
                    job_id="msd-job-2",
                    start_date="2025-01-01",
                    end_date="2025-01-31",
                    station="測試",
                    direction="backward",
                    loss_reasons=None,
                )

        complete_args = mock_complete.call_args.args
        complete_kwargs = mock_complete.call_args.kwargs
        assert complete_args[0] == "msd"
        assert complete_args[1] == "msd-job-2"
        assert complete_kwargs["error"] == "invalid range"


class TestGetMsdJobResult:
    @patch.object(svc, "cache_get", return_value={"kpi": {}})
    @patch.object(svc, "get_msd_job_status", return_value={"status": "completed", "query_id": "abc"})
    def test_result_uses_status_query_id(self, _mock_status, mock_cache_get):
        result = svc.get_msd_job_result("msd-job-3")
        assert result == {"kpi": {}}
        mock_cache_get.assert_called_once_with("abc")

    @patch.object(svc, "get_msd_job_status", return_value={"status": "running"})
    def test_result_returns_none_without_query_id(self, _mock_status):
        assert svc.get_msd_job_result("msd-job-4") is None
