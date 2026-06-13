# -*- coding: utf-8 -*-
"""Unit tests for production_history_job_service.

Covers:
- enqueue_production_history_query(): delegates to enqueue_job with correct args;
  returns (job_id, None) on success; returns (None, error) on failure
- execute_production_history_job(): spool hit skips Oracle; success calls
  query_production_history then complete_job; exception path calls complete_job
  with error and re-raises
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import mes_dashboard.services.production_history_job_service as pjs


# ---------------------------------------------------------------------------
# enqueue_production_history_query
# ---------------------------------------------------------------------------

class TestEnqueueProductionHistoryQuery:
    def test_delegates_to_enqueue_job_with_correct_arguments(self):
        """Should call enqueue_job with correct queue_name, worker_fn, and prefix."""
        mock_enqueue_job = MagicMock(return_value=("prod-hist-abc123", None))
        params = {"start_date": "2024-01-01", "end_date": "2024-02-01"}

        with patch.object(pjs, "enqueue_job", mock_enqueue_job):
            job_id, err = pjs.enqueue_production_history_query(params, owner="test-owner")

        assert job_id == "prod-hist-abc123"
        assert err is None
        mock_enqueue_job.assert_called_once()

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["queue_name"] == pjs.PRODUCTION_HISTORY_WORKER_QUEUE
        assert call_kwargs["worker_fn"] is pjs.execute_production_history_job
        assert call_kwargs["prefix"] == "production_history"
        assert call_kwargs["kwargs"]["params"] is params

    def test_returns_job_id_and_none_on_success(self):
        """Should return (job_id, None) when enqueue_job succeeds."""
        with patch.object(pjs, "enqueue_job", return_value=("prod-hist-deadbeef", None)):
            job_id, err = pjs.enqueue_production_history_query({}, owner="test-owner")
        assert job_id is not None
        assert job_id.startswith("prod-hist-")
        assert err is None

    def test_returns_none_and_error_on_failure(self):
        """Should return (None, error_message) when enqueue_job fails."""
        with patch.object(pjs, "enqueue_job", return_value=(None, "Redis down")):
            job_id, err = pjs.enqueue_production_history_query({}, owner="test-owner")
        assert job_id is None
        assert err == "Redis down"

    def test_job_id_prefixed_with_prod_hist(self):
        """The job_id passed to enqueue_job should start with 'prod-hist-'."""
        captured = {}

        def _capture(**kwargs):
            captured["job_id"] = kwargs.get("job_id")
            return (kwargs.get("job_id"), None)

        with patch.object(pjs, "enqueue_job", side_effect=_capture):
            pjs.enqueue_production_history_query({}, owner="test-owner")

        assert captured["job_id"].startswith("prod-hist-")

    def test_passes_ttl_and_timeout_from_config(self):
        """Should pass job_timeout and result_ttl from module-level config."""
        mock_enqueue_job = MagicMock(return_value=("prod-hist-ttl-test", None))
        with patch.object(pjs, "enqueue_job", mock_enqueue_job):
            pjs.enqueue_production_history_query({}, owner="test-owner")

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["job_timeout"] == pjs.PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS
        assert call_kwargs["result_ttl"] == pjs.PRODUCTION_HISTORY_JOB_TTL_SECONDS

    def test_passes_retry_configuration_to_enqueue_job(self):
        """Should pass retry config through to shared enqueue_job."""
        mock_enqueue_job = MagicMock(return_value=("prod-hist-retry-test", None))
        retry_cfg = object()
        with patch.object(pjs, "enqueue_job", mock_enqueue_job), \
             patch.object(pjs, "_build_retry", return_value=retry_cfg):
            pjs.enqueue_production_history_query({}, owner="test-owner")

        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs["retry"] is retry_cfg


# ---------------------------------------------------------------------------
# execute_production_history_job
# ---------------------------------------------------------------------------

class TestExecuteProductionHistoryJob:
    """Tests for the RQ worker entry-point function."""

    def test_spool_hit_skips_oracle_and_calls_complete_job(self):
        """When spool already has data, skip Oracle and call complete_job immediately."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_query_fn = MagicMock()
        mock_spool_id = MagicMock(return_value="ph-test-dataset-001")
        mock_get_spool = MagicMock(return_value="/some/path/to/spool.parquet")

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
        }), \
        patch("mes_dashboard.services.production_history_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.production_history_job_service.update_job_progress", mock_update_progress), \
        patch("mes_dashboard.core.query_spool_store.get_spool_file_path", mock_get_spool), \
        patch("mes_dashboard.services.production_history_service.make_canonical_spool_id", mock_spool_id), \
        patch("mes_dashboard.services.production_history_service.query_production_history", mock_query_fn):
            pjs.execute_production_history_job(
                job_id="prod-hist-spool-hit",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        mock_query_fn.assert_not_called()
        mock_complete_job.assert_called_once_with(
            "production_history", "prod-hist-spool-hit", query_id="ph-test-dataset-001"
        )

    def test_spool_miss_calls_query_and_complete_job(self):
        """Spool miss: should call query_production_history then complete_job."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_query_fn = MagicMock(return_value={"dataset_id": "ph-new-001"})
        mock_spool_id = MagicMock(return_value="ph-new-001")
        mock_get_spool = MagicMock(return_value=None)  # spool miss

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
        }), \
        patch("mes_dashboard.services.production_history_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.production_history_job_service.update_job_progress", mock_update_progress), \
        patch("mes_dashboard.core.query_spool_store.get_spool_file_path", mock_get_spool), \
        patch("mes_dashboard.services.production_history_service.make_canonical_spool_id", mock_spool_id), \
        patch("mes_dashboard.services.production_history_service.query_production_history", mock_query_fn):
            pjs.execute_production_history_job(
                job_id="prod-hist-miss",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        mock_query_fn.assert_called_once()
        mock_complete_job.assert_called_once_with(
            "production_history", "prod-hist-miss", query_id="ph-new-001"
        )

    def test_failure_path_calls_complete_job_with_error_and_reraises(self):
        """When query raises, complete_job should be called with error and exception re-raised."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_query_fn = MagicMock(side_effect=RuntimeError("ORA-timeout"))
        mock_spool_id = MagicMock(return_value="ph-fail-001")
        mock_get_spool = MagicMock(return_value=None)

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
        }), \
        patch("mes_dashboard.services.production_history_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.production_history_job_service.update_job_progress", mock_update_progress), \
        patch("mes_dashboard.core.query_spool_store.get_spool_file_path", mock_get_spool), \
        patch("mes_dashboard.services.production_history_service.make_canonical_spool_id", mock_spool_id), \
        patch("mes_dashboard.services.production_history_service.query_production_history", mock_query_fn):
            with pytest.raises(RuntimeError, match="ORA-timeout"):
                pjs.execute_production_history_job(
                    job_id="prod-hist-fail",
                    params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
                )

        mock_complete_job.assert_called_once()
        call_kwargs = mock_complete_job.call_args
        assert call_kwargs.args[0] == "production_history"
        assert call_kwargs.args[1] == "prod-hist-fail"
        assert call_kwargs.kwargs.get("error") is not None
        assert "ORA-timeout" in call_kwargs.kwargs["error"]

    def _make_spool_miss_mocks(self, dataset_id="ph-pct-001"):
        """Return shared mock objects for the spool-miss (normal) execution path."""
        mock_complete_job = MagicMock()
        mock_update_progress = MagicMock()
        mock_query_fn = MagicMock()
        mock_spool_id = MagicMock(return_value=dataset_id)
        mock_get_spool = MagicMock(return_value=None)  # spool miss
        return mock_complete_job, mock_update_progress, mock_query_fn, mock_spool_id, mock_get_spool

    def test_update_job_progress_called_with_pct_0_at_start(self):
        """update_job_progress first call must carry pct=0 (job start milestone)."""
        mock_complete_job, mock_update_progress, mock_query_fn, mock_spool_id, mock_get_spool = (
            self._make_spool_miss_mocks()
        )

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
        }), \
        patch("mes_dashboard.services.production_history_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.production_history_job_service.update_job_progress", mock_update_progress), \
        patch("mes_dashboard.core.query_spool_store.get_spool_file_path", mock_get_spool), \
        patch("mes_dashboard.services.production_history_service.make_canonical_spool_id", mock_spool_id), \
        patch("mes_dashboard.services.production_history_service.query_production_history", mock_query_fn):
            pjs.execute_production_history_job(
                job_id="prod-hist-pct-0",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        pct_values = [c.kwargs.get("pct") for c in mock_update_progress.call_args_list if "pct" in c.kwargs]
        assert pct_values[0] == 0

    def test_update_job_progress_called_with_pct_30_after_query(self):
        """update_job_progress second pct call must carry pct=30 (Oracle query issued milestone)."""
        mock_complete_job, mock_update_progress, mock_query_fn, mock_spool_id, mock_get_spool = (
            self._make_spool_miss_mocks()
        )

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
        }), \
        patch("mes_dashboard.services.production_history_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.production_history_job_service.update_job_progress", mock_update_progress), \
        patch("mes_dashboard.core.query_spool_store.get_spool_file_path", mock_get_spool), \
        patch("mes_dashboard.services.production_history_service.make_canonical_spool_id", mock_spool_id), \
        patch("mes_dashboard.services.production_history_service.query_production_history", mock_query_fn):
            pjs.execute_production_history_job(
                job_id="prod-hist-pct-30",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        pct_values = [c.kwargs.get("pct") for c in mock_update_progress.call_args_list if "pct" in c.kwargs]
        assert pct_values[1] == 30

    def test_update_job_progress_called_with_pct_100_before_complete(self):
        """update_job_progress third pct call must carry pct=100 (data written milestone), before complete_job."""
        mock_complete_job, mock_update_progress, mock_query_fn, mock_spool_id, mock_get_spool = (
            self._make_spool_miss_mocks()
        )

        call_order = []

        def track_update(*args, **kwargs):
            call_order.append(("update", kwargs.get("pct")))

        def track_complete(*args, **kwargs):
            call_order.append(("complete", None))

        mock_update_progress.side_effect = track_update
        mock_complete_job.side_effect = track_complete

        with patch.dict("sys.modules", {
            "mes_dashboard.rq_worker_preload": MagicMock(ensure_rq_logging=MagicMock()),
        }), \
        patch("mes_dashboard.services.production_history_job_service.complete_job", mock_complete_job), \
        patch("mes_dashboard.services.production_history_job_service.update_job_progress", mock_update_progress), \
        patch("mes_dashboard.core.query_spool_store.get_spool_file_path", mock_get_spool), \
        patch("mes_dashboard.services.production_history_service.make_canonical_spool_id", mock_spool_id), \
        patch("mes_dashboard.services.production_history_service.query_production_history", mock_query_fn):
            pjs.execute_production_history_job(
                job_id="prod-hist-pct-100",
                params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
            )

        pct_values = [c.kwargs.get("pct") for c in mock_update_progress.call_args_list if "pct" in c.kwargs]
        assert pct_values[2] == 100
        # pct=100 update must precede complete_job in call order
        pct_100_index = next(i for i, (kind, pct) in enumerate(call_order) if kind == "update" and pct == 100)
        complete_index = next(i for i, (kind, _) in enumerate(call_order) if kind == "complete")
        assert pct_100_index < complete_index
