# -*- coding: utf-8 -*-
"""Unit tests for load monitoring infrastructure.

Tests: LoadSummary.assert_within(), LoadCollector, TelemetryDiff,
StressTestResult.report(), chunk boundary payload helpers, PaginationWalker,
IntegrityResult, AsyncJobPoller.
"""

import json
import sys
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch, call

import importlib.util

import pytest

# Ensure tests/stress is on the path for relative imports
_STRESS_DIR = os.path.dirname(__file__)
if _STRESS_DIR not in sys.path:
    sys.path.insert(0, _STRESS_DIR)

from load_collector import (
    LoadCollector,
    LoadSample,
    LoadSummary,
    TelemetryDiff,
    RQ_QUEUES,
    _to_float,
    _to_int,
)
from integrity_helpers import IntegrityResult, PaginationWalker, RowCountBaseline
from async_helpers import AsyncJobPoller, AsyncJobResult, AsyncJobTimeout

# Load the stress conftest under a unique module name to avoid name collision
# with pytest's conftest mechanism (pytest uses 'conftest' internally).
_spec = importlib.util.spec_from_file_location(
    "stress_conftest", os.path.join(_STRESS_DIR, "conftest.py")
)
_stress_conftest = importlib.util.module_from_spec(_spec)
sys.modules["stress_conftest"] = _stress_conftest
_spec.loader.exec_module(_stress_conftest)
StressTestResult = _stress_conftest.StressTestResult


# ─────────────────────────────────────────────────────────────
# 12.1 — LoadSummary.assert_within()
# ─────────────────────────────────────────────────────────────

class TestLoadSummaryAssertWithin:

    def _make_summary(self, peak_cpu=50.0, peak_mem=70.0, peak_db_pool=60.0) -> LoadSummary:
        return LoadSummary(
            peak_cpu_pct=peak_cpu,
            avg_cpu_pct=40.0,
            peak_mem_pct=peak_mem,
            avg_mem_pct=60.0,
            peak_db_pool_pct=peak_db_pool,
        )

    def test_all_within_thresholds_no_error(self):
        """Passing case: all metrics below thresholds."""
        summary = self._make_summary(peak_cpu=50.0, peak_mem=70.0, peak_db_pool=60.0)
        # Should not raise
        summary.assert_within(max_cpu_pct=90.0, max_mem_pct=85.0, max_db_pool_pct=90.0)

    def test_memory_threshold_exceeded_raises(self):
        """Breach case: peak_mem exceeds threshold."""
        summary = self._make_summary(peak_mem=88.0)
        with pytest.raises(AssertionError) as exc_info:
            summary.assert_within(max_mem_pct=85.0)
        assert "peak_mem_pct=88.0%" in str(exc_info.value)
        assert "85.0%" in str(exc_info.value)

    def test_cpu_threshold_exceeded_raises(self):
        """Breach case: peak_cpu exceeds threshold."""
        summary = self._make_summary(peak_cpu=95.0)
        with pytest.raises(AssertionError) as exc_info:
            summary.assert_within(max_cpu_pct=90.0)
        assert "peak_cpu_pct" in str(exc_info.value)

    def test_db_pool_threshold_exceeded_raises(self):
        """Breach case: peak_db_pool exceeds threshold."""
        summary = self._make_summary(peak_db_pool=95.0)
        with pytest.raises(AssertionError) as exc_info:
            summary.assert_within(max_db_pool_pct=90.0)
        assert "peak_db_pool_pct" in str(exc_info.value)

    def test_none_metric_skips_assertion(self):
        """None-skip case: unavailable metric is not checked."""
        summary = LoadSummary(peak_db_pool_pct=None)
        # Should not raise even though max_db_pool_pct is specified
        summary.assert_within(max_db_pool_pct=90.0)

    def test_multiple_violations_reported(self):
        """Multiple threshold breaches all appear in the error message."""
        summary = self._make_summary(peak_cpu=95.0, peak_mem=90.0)
        with pytest.raises(AssertionError) as exc_info:
            summary.assert_within(max_cpu_pct=90.0, max_mem_pct=85.0)
        msg = str(exc_info.value)
        assert "peak_cpu_pct" in msg
        assert "peak_mem_pct" in msg


# ─────────────────────────────────────────────────────────────
# 12.2 — LoadCollector with mock HTTP responses
# ─────────────────────────────────────────────────────────────

def _mock_health_response(cpu=45.0, mem_pct=65.0, mem_avail_mb=4096.0, pressure="normal"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "healthy",
        "cpu_percent": cpu,
        "system_memory": {
            "used_pct": mem_pct,
            "available_mb": mem_avail_mb,
            "pressure": pressure,
        },
    }
    return resp


def _mock_admin_response(active=2, size=10, queues=None):
    resp = MagicMock()
    resp.status_code = 200
    q_data = {}
    for q in RQ_QUEUES:
        depth = (queues or {}).get(q, 0)
        q_data[q] = {"queued": depth}
    resp.json.return_value = {
        "data": {
            "db_pool": {"db_pool_active": active, "db_pool_size": size},
            "rq_queues": q_data,
            "heavy_query_telemetry": {
                "guard_reject_total": 0,
                "async_fallback_total": 0,
                "memory_error_total": 0,
                "spool_cache_hit": 5,
                "spool_cache_miss": 2,
            },
        }
    }
    return resp


def _url_dispatch(health_resp, admin_resp):
    """Return a side_effect function that routes by URL fragment."""
    def _dispatch(url, **kwargs):
        if "/health" in url:
            return health_resp
        return admin_resp
    return _dispatch


class TestLoadCollectorMock:

    def test_valid_samples_produce_summary(self):
        """Context manager with valid health responses produces a LoadSummary."""
        health_resp = _mock_health_response(cpu=50.0, mem_pct=70.0)
        admin_resp = _mock_admin_response(active=2, size=10)

        with patch("requests.get", side_effect=_url_dispatch(health_resp, admin_resp)):
            collector = LoadCollector("http://localhost:8080", interval=0.05)
            with collector:
                time.sleep(0.15)

        assert collector.summary is not None
        assert collector.summary.sample_count >= 1
        assert collector.summary.peak_cpu_pct == 50.0
        assert collector.summary.peak_mem_pct == 70.0

    def test_connection_failure_records_null_sample(self):
        """Connection failures produce null samples without stopping collection."""
        import requests as req

        health_ok = _mock_health_response(cpu=30.0, mem_pct=55.0)
        admin_ok = _mock_admin_response()

        call_count = [0]

        def _fail_first_then_ok(url, **kwargs):
            c = call_count[0]
            call_count[0] += 1
            if "/health" in url:
                if c == 0:
                    raise req.exceptions.ConnectionError("refused")
                return health_ok
            return admin_ok

        with patch("requests.get", side_effect=_fail_first_then_ok):
            collector = LoadCollector("http://localhost:8080", interval=0.05)
            with collector:
                time.sleep(0.2)

        assert collector.summary is not None
        # Should have at least one null sample and one valid sample
        assert collector.summary.null_sample_count >= 1 or collector.summary.sample_count >= 1

    def test_all_null_samples_summary_has_none_metrics(self):
        """When all polls fail, summary has None metrics and sample_count=0."""
        import requests as req

        def _always_fail(url, **kwargs):
            if "/health" in url:
                raise req.exceptions.ConnectionError("refused")
            raise req.exceptions.ConnectionError("refused")

        with patch("requests.get", side_effect=_always_fail):
            collector = LoadCollector("http://localhost:8080", interval=0.05)
            with collector:
                time.sleep(0.15)

        assert collector.summary is not None
        assert collector.summary.sample_count == 0
        assert collector.summary.peak_cpu_pct is None
        assert collector.summary.peak_mem_pct is None

    def test_rq_queue_depth_parsing(self):
        """RQ queue depths are parsed correctly from admin endpoint."""
        health_resp = _mock_health_response()
        queue_depths = {
            "trace-events": 3,
            "reject-query": 7,
            "msd-analysis": 0,
            "production-history-query": 12,
            "yield-alert-query": 5,
        }
        admin_resp = _mock_admin_response(queues=queue_depths)

        with patch("requests.get", side_effect=_url_dispatch(health_resp, admin_resp)):
            collector = LoadCollector("http://localhost:8080", interval=0.05)
            with collector:
                time.sleep(0.15)

        s = collector.summary
        assert s is not None
        assert s.peak_queue_depths is not None
        assert s.peak_queue_depths["production-history-query"] == 12
        assert s.peak_queue_depths["reject-query"] == 7


# ─────────────────────────────────────────────────────────────
# 12.3 — TelemetryDiff computation
# ─────────────────────────────────────────────────────────────

class TestTelemetryDiff:

    def test_counter_increase(self):
        """Counter values increase: delta is computed correctly."""
        before = {"guard_reject_total": 5, "async_fallback_total": 2,
                  "memory_error_total": 0, "spool_cache_hit": 10, "spool_cache_miss": 3}
        after = {"guard_reject_total": 8, "async_fallback_total": 2,
                 "memory_error_total": 1, "spool_cache_hit": 15, "spool_cache_miss": 4}
        diff = TelemetryDiff.compute(before, after)
        assert diff.guard_reject_total == 3
        assert diff.async_fallback_total == 0
        assert diff.memory_error_total == 1
        assert diff.spool_cache_hit == 5
        assert diff.spool_cache_miss == 1
        assert not diff.endpoint_unavailable
        assert not diff.all_zero

    def test_counter_unchanged(self):
        """All counters the same: delta is zero and all_zero is True."""
        snap = {"guard_reject_total": 3, "async_fallback_total": 1,
                "memory_error_total": 0, "spool_cache_hit": 7, "spool_cache_miss": 2}
        diff = TelemetryDiff.compute(snap, snap)
        assert diff.all_zero

    def test_endpoint_unavailable(self):
        """None before or after marks endpoint_unavailable=True."""
        diff_none_before = TelemetryDiff.compute(None, {"guard_reject_total": 1})
        assert diff_none_before.endpoint_unavailable

        diff_none_after = TelemetryDiff.compute({"guard_reject_total": 0}, None)
        assert diff_none_after.endpoint_unavailable


# ─────────────────────────────────────────────────────────────
# 12.4 — StressTestResult.report() with load_summary / telemetry_diff
# ─────────────────────────────────────────────────────────────

class TestStressTestResultReport:

    def _make_result(self, with_load=True, with_telemetry=True, with_integrity=False):
        result = StressTestResult(test_name="Unit Test")
        result.add_success(0.5)
        result.add_success(1.2)
        result.add_failure("timeout", 5.0)

        if with_load:
            telemetry = None
            if with_telemetry:
                telemetry = TelemetryDiff(
                    guard_reject_total=2,
                    async_fallback_total=1,
                    memory_error_total=0,
                    spool_cache_hit=10,
                    spool_cache_miss=3,
                )
            result.load_summary = LoadSummary(
                peak_cpu_pct=75.0,
                avg_cpu_pct=60.0,
                peak_mem_pct=80.0,
                avg_mem_pct=70.0,
                peak_db_pool_pct=55.0,
                peak_queue_depths={q: 0 for q in RQ_QUEUES},
                sample_count=15,
                null_sample_count=1,
                duration_sec=30.0,
                telemetry_diff=telemetry,
            )
        return result

    def test_report_includes_system_load_section(self):
        """report() includes System Load section when load_summary is present."""
        result = self._make_result(with_load=True)
        report = result.report()
        assert "System Load Summary" in report
        assert "Peak CPU:" in report
        assert "Peak Memory:" in report
        assert "Peak DB Pool:" in report
        assert "Samples:" in report

    def test_report_includes_telemetry_diff(self):
        """report() includes telemetry diff when not all-zero."""
        result = self._make_result(with_load=True, with_telemetry=True)
        report = result.report()
        assert "Telemetry Diff" in report
        assert "Guard Rejections:" in report

    def test_report_shows_no_events_when_all_zero(self):
        """report() shows 'No guard/spillover events detected' when telemetry is all zeros."""
        result = StressTestResult(test_name="Zero Telemetry Test")
        result.load_summary = LoadSummary(
            peak_cpu_pct=50.0,
            peak_mem_pct=60.0,
            telemetry_diff=TelemetryDiff(),  # all zeros
        )
        report = result.report()
        assert "No guard/spillover events detected" in report

    def test_report_without_load_summary(self):
        """report() works correctly without load_summary (backward compatible)."""
        result = StressTestResult(test_name="No Load Test")
        result.add_success(0.3)
        report = result.report()
        assert "Stress Test Report: No Load Test" in report
        assert "System Load" not in report


# ─────────────────────────────────────────────────────────────
# 12.5 — Chunk boundary probe payload helpers
# ─────────────────────────────────────────────────────────────

class TestChunkBoundaryPayloadHelpers:

    def test_padded_payload_200kb(self):
        """200KB payload is correctly sized."""
        from test_chunk_boundary import _make_padded_payload
        payload = _make_padded_payload(200 * 1024)
        serialised = json.dumps(payload).encode()
        assert len(serialised) >= 195 * 1024  # within 5KB tolerance

    def test_padded_payload_255kb(self):
        """255KB payload is correctly sized."""
        from test_chunk_boundary import _make_padded_payload
        payload = _make_padded_payload(255 * 1024)
        serialised = json.dumps(payload).encode()
        assert len(serialised) >= 250 * 1024

    def test_padded_payload_300kb(self):
        """300KB payload is correctly sized."""
        from test_chunk_boundary import _make_padded_payload
        payload = _make_padded_payload(300 * 1024)
        serialised = json.dumps(payload).encode()
        assert len(serialised) >= 295 * 1024

    def test_date_range_helper(self):
        """_date_range returns valid ISO date strings."""
        from test_chunk_boundary import _date_range
        start, end = _date_range(90)
        from datetime import date
        start_dt = date.fromisoformat(start)
        end_dt = date.fromisoformat(end)
        delta = (end_dt - start_dt).days
        assert 89 <= delta <= 91


# ─────────────────────────────────────────────────────────────
# 12.6 — PaginationWalker unit tests
# ─────────────────────────────────────────────────────────────

class TestPaginationWalker:

    def _mock_page(self, items_count: int, total_rows: int, status: int = 200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {
            "data": {
                "items": [{"id": i} for i in range(items_count)],
                "total_rows": total_rows,
            }
        }
        return resp

    def test_complete_walkthrough(self):
        """Complete walkthrough: all pages sum to total_rows."""
        page1 = self._mock_page(500, 1200)
        page2 = self._mock_page(500, 1200)
        page3 = self._mock_page(200, 1200)

        with patch("requests.get", side_effect=[page1, page2, page3]):
            walker = PaginationWalker("http://localhost:8080", page_size=500)
            row_sum, cp_failed = walker.walk("/api/paginate", "spool_key_1", 1200)

        assert row_sum == 1200
        assert not cp_failed

    def test_mid_pagination_error(self):
        """HTTP error mid-pagination sets checkpoint_failed."""
        page1 = self._mock_page(500, 1200)
        error_resp = MagicMock()
        error_resp.status_code = 500

        with patch("requests.get", side_effect=[page1, error_resp]):
            walker = PaginationWalker("http://localhost:8080", page_size=500)
            row_sum, cp_failed = walker.walk("/api/paginate", "spool_key_2", 1200)

        assert cp_failed

    def test_empty_page_mid_traversal(self):
        """Empty page before total_rows is reached sets checkpoint_failed."""
        page1 = self._mock_page(500, 1200)
        empty_page = self._mock_page(0, 1200)

        with patch("requests.get", side_effect=[page1, empty_page]):
            walker = PaginationWalker("http://localhost:8080", page_size=500)
            row_sum, cp_failed = walker.walk("/api/paginate", "spool_key_3", 1200)

        assert cp_failed


# ─────────────────────────────────────────────────────────────
# 12.7 — IntegrityResult verdict logic
# ─────────────────────────────────────────────────────────────

class TestIntegrityResultVerdict:

    def test_within_tolerance_pass(self):
        """Row count within 0.1% tolerance → PASS."""
        ir = IntegrityResult(service="test", baseline_count=10000, api_total_rows=9995)
        ir.compute_verdict(tolerance_pct=0.1)
        assert ir.verdict == "PASS"
        assert ir.deficit_pct is not None
        assert ir.deficit_pct < 0.1

    def test_over_tolerance_fail(self):
        """Row count deficit over 0.1% tolerance → FAIL."""
        ir = IntegrityResult(service="test", baseline_count=10000, api_total_rows=9500)
        ir.compute_verdict(tolerance_pct=0.1)
        assert ir.verdict == "FAIL"
        assert ir.deficit_pct == pytest.approx(5.0)

    def test_baseline_unavailable_skipped(self):
        """None baseline → SKIPPED (fallback to two-point is not possible)."""
        ir = IntegrityResult(service="test", baseline_count=None, api_total_rows=5000)
        ir.compute_verdict()
        assert ir.verdict == "SKIPPED"

    def test_pagination_sum_mismatch_fail(self):
        """Pagination sum != api_total_rows beyond tolerance → FAIL."""
        ir = IntegrityResult(
            service="test",
            baseline_count=1000,
            api_total_rows=1000,
            pagination_sum=800,
        )
        ir.compute_verdict(tolerance_pct=0.1)
        assert ir.verdict == "FAIL"
        assert "pagination sum" in ir.notes.lower() or "pagination" in ir.notes.lower()


# ─────────────────────────────────────────────────────────────
# 12.8 — AsyncJobPoller unit tests
# ─────────────────────────────────────────────────────────────

class TestAsyncJobPoller:

    def test_sync_200_path(self):
        """HTTP 200 response: returns sync_hit immediately."""
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b'{"data": {"total_rows": 500}}'
        resp.json.return_value = {"data": {"total_rows": 500}}

        with patch("requests.post", return_value=resp):
            poller = AsyncJobPoller("http://localhost:8080", max_wait=10, poll_interval=0.1)
            result = poller.submit_and_wait("POST", "/api/test/query", {})

        assert result.status == "sync_hit"
        assert result.poll_count == 0
        assert result.data == {"total_rows": 500}

    def test_async_202_polling_path(self):
        """HTTP 202 + polling until completed → returns completed result."""
        submit_resp = MagicMock()
        submit_resp.status_code = 202
        submit_resp.content = b'{}'
        submit_resp.json.return_value = {
            "data": {
                "job_id": "job-123",
                "status_url": "http://localhost:8080/api/test/status/job-123",
            }
        }

        pending_resp = MagicMock()
        pending_resp.status_code = 202
        pending_resp.json.return_value = {"data": {"status": "pending"}}

        done_resp = MagicMock()
        done_resp.status_code = 200
        done_resp.json.return_value = {
            "data": {"status": "completed", "result": {"total_rows": 1000}}
        }

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", side_effect=[pending_resp, done_resp]):
            poller = AsyncJobPoller("http://localhost:8080", max_wait=30, poll_interval=0.05)
            result = poller.submit_and_wait("POST", "/api/test/query", {})

        assert result.status == "completed"
        assert result.poll_count == 2
        assert result.data == {"total_rows": 1000}
        assert result.job_id == "job-123"

    def test_job_failure(self):
        """Polling returns failed status → AsyncJobResult with status=failed."""
        submit_resp = MagicMock()
        submit_resp.status_code = 202
        submit_resp.content = b'{}'
        submit_resp.json.return_value = {
            "data": {
                "job_id": "job-fail",
                "status_url": "http://localhost:8080/api/test/status/job-fail",
            }
        }

        fail_resp = MagicMock()
        fail_resp.status_code = 200
        fail_resp.json.return_value = {
            "data": {"status": "failed", "error": "DB timeout"}
        }

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", return_value=fail_resp):
            poller = AsyncJobPoller("http://localhost:8080", max_wait=30, poll_interval=0.05)
            result = poller.submit_and_wait("POST", "/api/test/query", {})

        assert result.status == "failed"
        assert "DB timeout" in (result.error or "")

    def test_timeout_raises_async_job_timeout(self):
        """Job never completes → AsyncJobTimeout raised."""
        submit_resp = MagicMock()
        submit_resp.status_code = 202
        submit_resp.content = b'{}'
        submit_resp.json.return_value = {
            "data": {
                "job_id": "job-slow",
                "status_url": "http://localhost:8080/api/test/status/job-slow",
            }
        }

        pending_resp = MagicMock()
        pending_resp.status_code = 202
        pending_resp.json.return_value = {"data": {"status": "pending"}}

        with patch("requests.post", return_value=submit_resp), \
             patch("requests.get", return_value=pending_resp):
            poller = AsyncJobPoller("http://localhost:8080", max_wait=0.2, poll_interval=0.05)
            with pytest.raises(AsyncJobTimeout) as exc_info:
                poller.submit_and_wait("POST", "/api/test/query", {})

        assert "job-slow" in str(exc_info.value)
        assert exc_info.value.job_id == "job-slow"
