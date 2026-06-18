# -*- coding: utf-8 -*-
"""Unit tests for rq_monitor_service.

Covers:
- get_rq_worker_details(): worker enumeration, summary counts, fail-open
- get_rq_queue_details(): queue depth, registry counts, fail-open
- get_heavy_query_slot_status(): slot utilization calculation
- get_rq_monitor_summary(): aggregation, partial failure handling
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


import mes_dashboard.services.rq_monitor_service as svc


# ---------------------------------------------------------------------------
# get_rq_worker_details
# ---------------------------------------------------------------------------

class TestGetRqWorkerDetails:
    def test_returns_empty_when_rq_not_installed(self):
        with patch.object(svc, "_check_rq_installed", return_value=False):
            result = svc.get_rq_worker_details()
        assert result["workers"] == []
        assert result["summary"]["total"] == 0

    def test_returns_empty_when_redis_unavailable(self):
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=None):
            result = svc.get_rq_worker_details()
        assert result["workers"] == []
        assert result["summary"]["total"] == 0

    def test_returns_correct_summary_counts(self):
        w1 = MagicMock()
        w1.name = "worker-1"
        w1.get_state.return_value = "busy"
        w1.get_current_job.return_value = MagicMock(id="job-abc")
        w1.queues = [MagicMock(name="trace-events")]
        w1.birth_date = None
        w1.successful_job_count = 42
        w1.failed_job_count = 1

        w2 = MagicMock()
        w2.name = "worker-2"
        w2.get_state.return_value = "idle"
        w2.get_current_job.return_value = None
        w2.queues = [MagicMock(name="reject-query")]
        w2.birth_date = None
        w2.successful_job_count = 10
        w2.failed_job_count = 0

        mock_conn = MagicMock()
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.return_value = [w1, w2]
            result = svc.get_rq_worker_details()

        assert result["summary"]["total"] == 2
        assert result["summary"]["busy"] == 1
        assert result["summary"]["idle"] == 1
        assert result["workers"][0]["name"] == "worker-1"
        assert result["workers"][0]["state"] == "busy"
        assert result["workers"][0]["current_job"] == "job-abc"
        assert result["workers"][0]["successful_job_count"] == 42
        assert result["workers"][1]["state"] == "idle"
        assert result["workers"][1]["current_job"] is None

    def test_handles_worker_all_exception(self):
        mock_conn = MagicMock()
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.side_effect = Exception("Redis error")
            result = svc.get_rq_worker_details()
        assert result["workers"] == []
        assert result["summary"]["total"] == 0

    def test_birth_date_has_utc_suffix(self):
        from datetime import datetime
        w = MagicMock()
        w.name = "worker-tz"
        w.get_state.return_value = "idle"
        w.get_current_job.return_value = None
        w.queues = []
        w.birth_date = datetime(2026, 4, 1, 0, 0, 0)  # naive UTC datetime
        w.successful_job_count = 0
        w.failed_job_count = 0

        mock_conn = MagicMock()
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.return_value = [w]
            result = svc.get_rq_worker_details()

        birth = result["workers"][0]["birth_date"]
        assert birth is not None
        assert "+00:00" in birth

    def test_null_birth_date_returns_null(self):
        w = MagicMock()
        w.name = "worker-no-birth"
        w.get_state.return_value = "idle"
        w.get_current_job.return_value = None
        w.queues = []
        w.birth_date = None
        w.successful_job_count = 0
        w.failed_job_count = 0

        mock_conn = MagicMock()
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Worker") as mock_worker_cls:
            mock_worker_cls.all.return_value = [w]
            result = svc.get_rq_worker_details()

        assert result["workers"][0]["birth_date"] is None


# ---------------------------------------------------------------------------
# get_rq_queue_details
# ---------------------------------------------------------------------------

class TestGetRqQueueDetails:
    def test_returns_empty_when_redis_unavailable(self):
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=None):
            result = svc.get_rq_queue_details()
        assert result["queues"] == []
        assert result["total_queued"] == 0

    def test_returns_queue_depth_per_queue(self):
        mock_conn = MagicMock()

        def make_queue(name, connection):
            q = MagicMock()
            q.name = name
            q.__len__ = lambda self: 3 if name == "trace-events" else 1
            q.started_job_registry.count = 1
            q.failed_job_registry.count = 0
            return q

        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", side_effect=make_queue):
            result = svc.get_rq_queue_details()

        # trace-events, reject-query, msd-analysis, production-history-query,
        # yield-alert-query, material-consumption, downtime-query, hold-history-query,
        # resource-history-query, eap-alarm-query
        assert len(result["queues"]) == 10
        assert result["queues"][0]["name"] == "trace-events"
        assert result["queues"][0]["depth"] == 3
        assert result["queues"][1]["name"] == "reject-query"
        assert result["queues"][1]["depth"] == 1
        assert result["total_queued"] == 12  # 3 + 1×9
        assert result["total_started"] == 10  # 1 per queue × 10 queues
        assert result["total_failed"] == 0

    def test_hold_history_queue_in_queue_names(self):
        """'hold-history-query' must appear in _QUEUE_NAMES (AC-7, IP-4)."""
        assert "hold-history-query" in svc._QUEUE_NAMES, (
            "'hold-history-query' must be registered in _QUEUE_NAMES "
            "(rq_monitor_service IP-4 / AC-7)"
        )

    def test_handles_queue_exception_gracefully(self):
        mock_conn = MagicMock()
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", side_effect=Exception("Redis error")):
            result = svc.get_rq_queue_details()
        # Should still return entries with zero values (now 10 queues including eap-alarm-query)
        assert len(result["queues"]) == 10
        assert result["total_queued"] == 0


# ---------------------------------------------------------------------------
# get_heavy_query_slot_status
# ---------------------------------------------------------------------------

class TestGetHeavyQuerySlotStatus:
    def test_returns_active_max_utilization(self):
        with patch("mes_dashboard.core.global_concurrency.get_active_slot_count", return_value=2), \
             patch("mes_dashboard.core.global_concurrency.HEAVY_QUERY_MAX_CONCURRENT", 3):
            result = svc.get_heavy_query_slot_status()
        assert result["active"] == 2
        assert result["max"] == 3
        assert result["utilization_pct"] == 66.7

    def test_zero_max_handled(self):
        with patch("mes_dashboard.core.global_concurrency.get_active_slot_count", return_value=0), \
             patch("mes_dashboard.core.global_concurrency.HEAVY_QUERY_MAX_CONCURRENT", 0):
            result = svc.get_heavy_query_slot_status()
        assert result["utilization_pct"] == 0.0


# ---------------------------------------------------------------------------
# get_rq_monitor_summary
# ---------------------------------------------------------------------------

class TestGetRqMonitorSummary:
    def test_aggregates_all_sections(self):
        mock_workers = {"workers": [], "summary": {"total": 2, "busy": 1, "idle": 1}}
        mock_queues = {"queues": [], "total_queued": 3, "total_started": 1, "total_failed": 0}
        mock_slots = {"active": 1, "max": 3, "utilization_pct": 33.3}

        with patch.object(svc, "get_rq_worker_details", return_value=mock_workers), \
             patch.object(svc, "get_rq_queue_details", return_value=mock_queues), \
             patch.object(svc, "get_heavy_query_slot_status", return_value=mock_slots), \
             patch("mes_dashboard.services.async_query_job_service.is_async_available", return_value=True):
            result = svc.get_rq_monitor_summary()

        assert result["rq_available"] is True
        assert result["workers"] == mock_workers
        assert result["queues"] == mock_queues
        assert result["slots"] == mock_slots

    def test_graceful_on_partial_failure(self):
        with patch.object(svc, "get_rq_worker_details", side_effect=Exception("fail")), \
             patch.object(svc, "get_rq_queue_details", return_value={"queues": [], "total_queued": 0, "total_started": 0, "total_failed": 0}), \
             patch.object(svc, "get_heavy_query_slot_status", return_value={"active": 0, "max": 3, "utilization_pct": 0.0}), \
             patch("mes_dashboard.services.async_query_job_service.is_async_available", return_value=False):
            result = svc.get_rq_monitor_summary()

        assert result["rq_available"] is False
        assert result["workers"] == {}  # failed, returns empty
        assert result["queues"]["total_queued"] == 0
        assert result["slots"]["active"] == 0
