# -*- coding: utf-8 -*-
"""Unit tests for resource_query_job_service.

Tests the should_use_async boundary, worker fn failure behavior,
and module-level constant defaults.

AC coverage: AC-7, AC-9.
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestResourceQueryJobService:
    """Unit tests for resource_query_job_service."""

    # ── should_use_async boundary tests ──────────────────────────────────────

    def test_should_use_async_above_threshold(self, monkeypatch):
        """should_use_async returns True when day_span ≥ threshold and flag is True (AC-7)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_ENABLED", True)
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD", 90)

        params = {"start_date": "2025-01-01", "end_date": "2025-06-01"}  # 151 days
        assert _svc.should_use_async(params) is True, (
            "should_use_async must return True when span >= threshold and enabled"
        )

    def test_should_use_async_at_exact_threshold(self, monkeypatch):
        """should_use_async returns True at exactly threshold days (AC-7)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_ENABLED", True)
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD", 90)

        # end - start = 90 days
        params = {"start_date": "2025-01-01", "end_date": "2025-04-01"}  # 90 days
        assert _svc.should_use_async(params) is True, (
            "should_use_async must return True when span == threshold (boundary inclusive)"
        )

    def test_should_use_async_below_threshold_is_false(self, monkeypatch):
        """should_use_async returns False when day_span < threshold (AC-7)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_ENABLED", True)
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD", 90)

        params = {"start_date": "2025-01-01", "end_date": "2025-01-07"}  # 6 days
        assert _svc.should_use_async(params) is False, (
            "should_use_async must return False when span < threshold"
        )

    def test_should_use_async_flag_false_returns_false(self, monkeypatch):
        """should_use_async returns False when RESOURCE_ASYNC_ENABLED=False (AC-6)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_ENABLED", False)
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD", 90)

        params = {"start_date": "2025-01-01", "end_date": "2025-12-31"}  # 364 days
        assert _svc.should_use_async(params) is False, (
            "should_use_async must return False when flag is False"
        )

    def test_should_use_async_missing_dates_returns_false(self, monkeypatch):
        """should_use_async returns False when start_date or end_date is missing (AC-7)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_ENABLED", True)
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD", 90)

        assert _svc.should_use_async({}) is False
        assert _svc.should_use_async({"start_date": "2025-01-01"}) is False
        assert _svc.should_use_async({"end_date": "2025-12-31"}) is False

    def test_should_use_async_invalid_date_format_returns_false(self, monkeypatch):
        """should_use_async returns False when date format is invalid (AC-7)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_ENABLED", True)
        monkeypatch.setattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD", 90)

        params = {"start_date": "not-a-date", "end_date": "also-bad"}
        assert _svc.should_use_async(params) is False, (
            "should_use_async must return False on invalid date format"
        )

    # ── worker fn failure tests ───────────────────────────────────────────────

    def test_worker_fn_failure_reraises_and_sets_error(self, monkeypatch):
        """execute_resource_history_query_job on exception: calls complete_job(error=...) and re-raises (AC-9)."""
        import mes_dashboard.services.resource_query_job_service as _svc

        complete_calls = []

        def _mock_complete_job(prefix, job_id, query_id=None, error=None, **kw):
            complete_calls.append({
                "prefix": prefix,
                "job_id": job_id,
                "query_id": query_id,
                "error": error,
            })

        monkeypatch.setattr(_svc, "update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr(_svc, "complete_job", _mock_complete_job)

        _error = RuntimeError("Oracle ORA-00001 during resource query")

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                side_effect=_error,
            ):
                with pytest.raises(RuntimeError, match="Oracle ORA-00001"):
                    _svc.execute_resource_history_query_job(
                        job_id="unit-fail-001",
                        owner="unit-test-user",
                        start_date="2025-01-01",
                        end_date="2025-06-01",
                        granularity="day",
                    )

        assert len(complete_calls) == 1, (
            "complete_job must be called exactly once on failure (AC-9)"
        )
        assert complete_calls[0]["error"] is not None, (
            "complete_job must be called with error= on failure (AC-9)"
        )
        assert complete_calls[0]["query_id"] is None, (
            "complete_job must NOT set query_id on failure path (AC-9)"
        )
        assert complete_calls[0]["prefix"] == "resource-history"

    def test_worker_fn_success_calls_complete_job_with_query_id(self, monkeypatch):
        """execute_resource_history_query_job on success: calls complete_job(query_id=...) (AC-3)."""
        import mes_dashboard.services.resource_query_job_service as _svc

        complete_calls = []
        mock_qid = f"unit-success-{uuid.uuid4().hex[:8]}"

        def _mock_complete_job(prefix, job_id, query_id=None, error=None, **kw):
            complete_calls.append({
                "query_id": query_id,
                "error": error,
            })

        monkeypatch.setattr(_svc, "update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr(_svc, "complete_job", _mock_complete_job)

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                return_value={"query_id": mock_qid},
            ):
                _svc.execute_resource_history_query_job(
                    job_id="unit-success-001",
                    owner="unit-test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                    granularity="day",
                )

        assert len(complete_calls) == 1
        assert complete_calls[0]["query_id"] == mock_qid
        assert complete_calls[0]["error"] is None

    # ── register_job_type side-effect tests ────────────────────────────────────

    def test_register_job_type_fires_at_import(self):
        """register_job_type('resource-history', ...) is called at module import time (IP-1)."""
        from mes_dashboard.services.job_registry import get_job_type_config
        config = get_job_type_config("resource-history")
        assert config is not None, (
            '"resource-history" job type must be registered after importing '
            "resource_query_job_service"
        )
        assert config.queue_name == "resource-history-query"
        assert config.timeout_seconds == 1800

    def test_register_job_type_reruns_after_reload(self):
        """register_job_type() re-fires after importlib.reload() (test-discipline rule)."""
        from mes_dashboard.services import job_registry as _reg_mod
        import mes_dashboard.services.resource_query_job_service as _svc

        _reg_mod._REGISTRY.clear()
        assert _reg_mod._REGISTRY.get("resource-history") is None

        importlib.reload(_svc)
        from mes_dashboard.services.job_registry import get_job_type_config
        config = get_job_type_config("resource-history")
        assert config is not None, "register_job_type must re-fire after importlib.reload()"

    # ── env var default tests ─────────────────────────────────────────────────

    def test_resource_async_enabled_defaults_to_true(self):
        """RESOURCE_ASYNC_ENABLED must default to True (AC-5)."""
        _old = os.environ.pop("RESOURCE_ASYNC_ENABLED", None)
        try:
            import mes_dashboard.services.resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_ASYNC_ENABLED is True, (
                f"RESOURCE_ASYNC_ENABLED expected True, got {_svc.RESOURCE_ASYNC_ENABLED!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_ASYNC_ENABLED"] = _old
            else:
                import mes_dashboard.services.resource_query_job_service as _svc
                importlib.reload(_svc)

    def test_resource_async_day_threshold_defaults_to_90(self):
        """RESOURCE_ASYNC_DAY_THRESHOLD must default to 90 (AC-5)."""
        _old = os.environ.pop("RESOURCE_ASYNC_DAY_THRESHOLD", None)
        try:
            import mes_dashboard.services.resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_ASYNC_DAY_THRESHOLD == 90, (
                f"RESOURCE_ASYNC_DAY_THRESHOLD expected 90, got {_svc.RESOURCE_ASYNC_DAY_THRESHOLD!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_ASYNC_DAY_THRESHOLD"] = _old
            else:
                import mes_dashboard.services.resource_query_job_service as _svc
                importlib.reload(_svc)

    def test_resource_worker_queue_defaults_to_resource_history_query(self):
        """RESOURCE_WORKER_QUEUE must default to 'resource-history-query' (AC-5)."""
        _old = os.environ.pop("RESOURCE_WORKER_QUEUE", None)
        try:
            import mes_dashboard.services.resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_WORKER_QUEUE == "resource-history-query", (
                f"RESOURCE_WORKER_QUEUE expected 'resource-history-query', got {_svc.RESOURCE_WORKER_QUEUE!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_WORKER_QUEUE"] = _old
            else:
                import mes_dashboard.services.resource_query_job_service as _svc
                importlib.reload(_svc)

    def test_resource_job_timeout_defaults_to_1800(self):
        """RESOURCE_JOB_TIMEOUT_SECONDS must default to 1800 (AC-5)."""
        _old = os.environ.pop("RESOURCE_JOB_TIMEOUT_SECONDS", None)
        try:
            import mes_dashboard.services.resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_JOB_TIMEOUT_SECONDS == 1800, (
                f"RESOURCE_JOB_TIMEOUT_SECONDS expected 1800, got {_svc.RESOURCE_JOB_TIMEOUT_SECONDS!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_JOB_TIMEOUT_SECONDS"] = _old
            else:
                import mes_dashboard.services.resource_query_job_service as _svc
                importlib.reload(_svc)
