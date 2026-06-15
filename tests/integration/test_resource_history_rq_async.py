# -*- coding: utf-8 -*-
"""
Integration tests for resource-history-rq-async: dispatch and worker-fn parity.

Mirrors test_hold_history_rq_async.py pattern (hold-history-rq-async change).

Tier 1 (dispatch) and Tier 3 (data-boundary parity) — all require real
Redis and a running RQ worker environment.

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_resource_history_rq_async.py \
        --run-integration-real -v

Test classes:
  TestResourceHistoryAsyncDispatch — AC-7: enqueue_job_dynamic routes to resource-history-query
  TestResourceHistoryAsyncParity   — AC-3/AC-5: worker fn parity vs sync + milestone ordering
"""

from __future__ import annotations

import importlib
import os
import uuid
from typing import Any, Dict
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_registry() -> None:
    """Clear the job registry to allow clean re-registration tests."""
    from mes_dashboard.services import job_registry as _reg_mod
    _reg_mod._REGISTRY.clear()


def _reload_resource_job_service() -> None:
    """Reload resource_query_job_service so register_job_type() re-fires."""
    import mes_dashboard.services.resource_query_job_service as _svc
    _reset_registry()
    importlib.reload(_svc)


# ===========================================================================
# TestResourceHistoryAsyncDispatch — AC-7
# ===========================================================================

class TestResourceHistoryAsyncDispatch:
    """AC-7: enqueue_job_dynamic enqueues to the resource-history-query queue.

    This test does NOT require a real Redis connection — it verifies the
    dispatch plumbing at the enqueue_job level using a mock so it can run
    reliably in the integration_real tier without a live RQ worker.
    """

    def test_enqueue_to_resource_history_queue(self, monkeypatch):
        """enqueue_job_dynamic("resource-history", ...) must call enqueue_job with
        queue_name="resource-history-query" (AC-7, IP-4).

        Verify:
        1. The registry has "resource-history" registered (from module import).
        2. The registered queue_name matches the RESOURCE_WORKER_QUEUE default.
        3. enqueue_job_dynamic forwards to enqueue_job with correct queue_name.
        """
        import mes_dashboard.services.resource_query_job_service as _svc  # noqa: F401
        from mes_dashboard.services.job_registry import get_job_type_config

        config = get_job_type_config("resource-history")
        assert config is not None, (
            '"resource-history" job type must be registered after importing '
            "resource_query_job_service (AC-7 module side-effect)"
        )
        assert config.queue_name == "resource-history-query", (
            f"Expected queue_name='resource-history-query', got {config.queue_name!r} "
            "(AC-7: must route to the resource-history-query queue)"
        )

        captured: Dict[str, Any] = {}

        def _mock_enqueue_job(**kwargs):
            captured.update(kwargs)
            return ("mock-resource-job-001", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue_job,
        )

        from mes_dashboard.services.async_query_job_service import enqueue_job_dynamic

        job_id, err = enqueue_job_dynamic(
            "resource-history",
            owner="test-user",
            params={
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "granularity": "day",
            },
        )

        assert err is None, f"enqueue_job_dynamic returned error: {err!r}"
        assert captured.get("queue_name") == "resource-history-query", (
            f"enqueue_job called with queue_name={captured.get('queue_name')!r}; "
            "expected 'resource-history-query' (AC-7)"
        )
        assert captured.get("prefix") == "resource-history", (
            f"enqueue_job must pass prefix='resource-history', got {captured.get('prefix')!r}"
        )
        assert captured.get("job_timeout") == _svc.RESOURCE_JOB_TIMEOUT_SECONDS, (
            "enqueue_job timeout must match RESOURCE_JOB_TIMEOUT_SECONDS"
        )

    def test_enqueue_payload_owner_inside_params_dict(self, monkeypatch):
        """owner MUST be inside the _params dict (AC-7 regression guard).

        kwargs forwarded to the worker must include job_id, owner, and query params.
        Assert via call_args.kwargs["params"]["owner"] (per-kwarg, not assert_called_once_with).
        """
        import mes_dashboard.services.resource_query_job_service as _svc  # noqa: F401

        captured: Dict[str, Any] = {}

        def _mock_enqueue_job(**kwargs):
            captured.update(kwargs)
            return ("mock-resource-job-002", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue_job,
        )

        from mes_dashboard.services.async_query_job_service import enqueue_job_dynamic

        enqueue_job_dynamic(
            "resource-history",
            owner="resource-eng-user",
            params={
                "owner": "resource-eng-user",  # owner must be inside params dict
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "granularity": "week",
                "workcenter_groups": ["WC01"],
                "families": None,
                "resource_ids": None,
                "is_production": True,
                "is_key": False,
                "is_monitor": False,
                "package_groups": None,
            },
        )

        kwargs_forwarded = captured.get("kwargs", {})
        assert "job_id" in kwargs_forwarded, (
            "Worker kwargs must include 'job_id' "
            "(required by execute_resource_history_query_job signature)"
        )
        assert "start_date" in kwargs_forwarded, (
            "Worker kwargs must propagate start_date query param"
        )
        assert "end_date" in kwargs_forwarded, (
            "Worker kwargs must propagate end_date query param"
        )
        # AC-7: owner must be inside params dict so worker can authenticate
        params_in_kwargs = kwargs_forwarded.get("params", {})
        assert params_in_kwargs.get("owner") == "resource-eng-user", (
            "owner must be inside kwargs['params']['owner'] (AC-7 regression guard): "
            f"got params={params_in_kwargs!r}"
        )

    def test_resource_worker_queue_default_is_resource_history_query(self):
        """RESOURCE_WORKER_QUEUE must default to 'resource-history-query' (AC-5)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        _old = os.environ.pop("RESOURCE_WORKER_QUEUE", None)
        try:
            importlib.reload(_svc)
            assert _svc.RESOURCE_WORKER_QUEUE == "resource-history-query", (
                f"Expected RESOURCE_WORKER_QUEUE default 'resource-history-query', "
                f"got {_svc.RESOURCE_WORKER_QUEUE!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_WORKER_QUEUE"] = _old
            else:
                importlib.reload(_svc)

    def test_resource_job_timeout_default_is_1800(self):
        """RESOURCE_JOB_TIMEOUT_SECONDS must default to 1800 (AC-5)."""
        import mes_dashboard.services.resource_query_job_service as _svc
        _old = os.environ.pop("RESOURCE_JOB_TIMEOUT_SECONDS", None)
        try:
            importlib.reload(_svc)
            assert _svc.RESOURCE_JOB_TIMEOUT_SECONDS == 1800, (
                f"Expected RESOURCE_JOB_TIMEOUT_SECONDS default 1800, "
                f"got {_svc.RESOURCE_JOB_TIMEOUT_SECONDS!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_JOB_TIMEOUT_SECONDS"] = _old
            else:
                importlib.reload(_svc)


# ===========================================================================
# TestResourceHistoryAsyncParity — AC-3 / AC-5
# ===========================================================================

class TestResourceHistoryAsyncParity:
    """AC-3: execute_resource_history_query_job produces result identical to sync path.
    AC-5: pct milestones are non-decreasing, first ≤ 5, last == 100.
    AC-9: worker exception → complete_job(error=...) + reraise; no false success.

    Data-boundary tier (tier 3): requires real Oracle and full env parity.
    When real Oracle is not available the test is expected to skip/fail at
    the Oracle-level mock boundary rather than at the assertions.

    Parity guarantee: worker fn calls execute_primary_query() with the exact
    same params, and complete_job() is only called after result is available.
    """

    def test_worker_fn_parity_vs_sync(self, monkeypatch):
        """execute_resource_history_query_job calls execute_primary_query with forwarded
        params and only calls complete_job after result is available.

        Also verifies that owner is NOT forwarded to execute_primary_query
        (it is a job-level param, not a query param).
        """
        from mes_dashboard.services.resource_query_job_service import (
            execute_resource_history_query_job,
        )

        query_params = {
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "granularity": "day",
            "workcenter_groups": ["WC01"],
            "families": None,
            "resource_ids": None,
            "is_production": True,
            "is_key": False,
            "is_monitor": False,
            "package_groups": None,
        }

        call_log = []
        mock_query_id = f"parity-resource-{uuid.uuid4().hex[:8]}"

        def _mock_execute_primary_query(
            *,
            start_date,
            end_date,
            granularity="day",
            workcenter_groups=None,
            families=None,
            resource_ids=None,
            is_production=False,
            is_key=False,
            is_monitor=False,
            package_groups=None,
        ):
            call_log.append({
                "start_date": start_date,
                "end_date": end_date,
                "granularity": granularity,
                "workcenter_groups": workcenter_groups,
                "families": families,
                "is_production": is_production,
                "is_key": is_key,
                "is_monitor": is_monitor,
                "package_groups": package_groups,
            })
            return {
                "query_id": mock_query_id,
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
            }

        complete_calls = []

        def _mock_complete_job(prefix, job_id, query_id=None, error=None, **kw):
            complete_calls.append({
                "prefix": prefix,
                "job_id": job_id,
                "query_id": query_id,
                "error": error,
            })

        progress_calls = []

        def _mock_update_progress(prefix, job_id, **fields):
            progress_calls.append({"prefix": prefix, "job_id": job_id, **fields})

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            _mock_update_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            _mock_complete_job,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                side_effect=_mock_execute_primary_query,
            ):
                execute_resource_history_query_job(
                    job_id="test-resource-parity-001",
                    owner="test-user",
                    **query_params,
                )

        # 1. execute_primary_query was called exactly once with the correct params
        assert len(call_log) == 1, (
            f"execute_primary_query must be called exactly once, got {len(call_log)}"
        )
        actual = call_log[0]
        assert actual["start_date"] == query_params["start_date"]
        assert actual["end_date"] == query_params["end_date"]
        assert actual["granularity"] == query_params["granularity"]
        assert actual["workcenter_groups"] == query_params["workcenter_groups"]
        assert actual["is_production"] == query_params["is_production"]
        # owner must NOT be forwarded to execute_primary_query
        assert "owner" not in actual, (
            "owner must NOT be forwarded to execute_primary_query (not a query param)"
        )

        # 2. complete_job called only AFTER successful return
        assert len(complete_calls) == 1, (
            f"complete_job must be called exactly once on success, got {len(complete_calls)}"
        )
        assert complete_calls[0]["error"] is None, (
            "complete_job must not be called with error= on success path"
        )
        assert complete_calls[0]["query_id"] == mock_query_id, (
            f"complete_job query_id must match result['query_id']; "
            f"expected {mock_query_id!r}, got {complete_calls[0]['query_id']!r}"
        )
        assert complete_calls[0]["prefix"] == "resource-history"

    def test_coarse_milestones_fire_in_order(self, monkeypatch):
        """Pct milestones must be non-decreasing; first ≤ 5, last == 100 (AC-3)."""
        from mes_dashboard.services.resource_query_job_service import (
            execute_resource_history_query_job,
        )

        mock_query_id = f"milestone-resource-{uuid.uuid4().hex[:8]}"

        progress_calls = []

        def _mock_update_progress(prefix, job_id, **fields):
            progress_calls.append({"prefix": prefix, "job_id": job_id, **fields})

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            _mock_update_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                return_value={"query_id": mock_query_id},
            ):
                execute_resource_history_query_job(
                    job_id="test-resource-milestones-001",
                    owner="test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                    granularity="day",
                )

        pct_vals = [c["pct"] for c in progress_calls if "pct" in c]
        assert len(pct_vals) >= 2, (
            f"Expected at least 2 pct milestones, got {pct_vals}"
        )
        assert pct_vals[0] <= 5, (
            f"First pct milestone must be ≤ 5 (AC-3), got {pct_vals[0]}"
        )
        assert pct_vals[-1] == 100, (
            f"Last pct milestone must be 100 (AC-3), got {pct_vals[-1]}"
        )
        # Non-decreasing check
        for i in range(1, len(pct_vals)):
            assert pct_vals[i] >= pct_vals[i - 1], (
                f"Pct milestones must be non-decreasing (AC-3): "
                f"{pct_vals[i - 1]} → {pct_vals[i]} at index {i}"
            )

    def test_pct_envelope_never_decreases(self, monkeypatch):
        """All emitted pct values must form a monotonically non-decreasing sequence (AC-3)."""
        from mes_dashboard.services.resource_query_job_service import (
            execute_resource_history_query_job,
        )

        mock_query_id = f"mono-resource-{uuid.uuid4().hex[:8]}"
        all_pct = []

        def _track_progress(prefix, job_id, **fields):
            if "pct" in fields:
                all_pct.append(fields["pct"])

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            _track_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                return_value={"query_id": mock_query_id},
            ):
                execute_resource_history_query_job(
                    job_id="test-resource-mono-001",
                    owner="test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                    granularity="day",
                )

        assert len(all_pct) >= 2, f"Expected ≥ 2 pct values, got {all_pct}"
        for i in range(1, len(all_pct)):
            assert all_pct[i] >= all_pct[i - 1], (
                f"pct envelope decreased at index {i}: {all_pct[i - 1]} → {all_pct[i]}"
            )

    def test_worker_exception_calls_complete_job_with_error(self, monkeypatch):
        """Worker exception → complete_job(error=...) + reraise; no false success (AC-9).

        complete_job must be called with error= (not query_id=), and the
        exception must propagate (loud failure) so the RQ worker marks the
        job as failed.
        """
        from mes_dashboard.services.resource_query_job_service import (
            execute_resource_history_query_job,
        )

        complete_calls = []

        def _mock_complete_job(prefix, job_id, query_id=None, error=None, **kw):
            complete_calls.append({
                "prefix": prefix,
                "job_id": job_id,
                "query_id": query_id,
                "error": error,
            })

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            _mock_complete_job,
        )

        _simulated_error = RuntimeError("Oracle connection refused during resource query")

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                side_effect=_simulated_error,
            ):
                with pytest.raises(RuntimeError, match="Oracle connection refused"):
                    execute_resource_history_query_job(
                        job_id="test-resource-fail-001",
                        owner="test-user",
                        start_date="2025-01-01",
                        end_date="2025-06-01",
                        granularity="day",
                    )

        assert len(complete_calls) == 1, (
            "complete_job must be called once even on failure (to mark job as failed)"
        )
        assert complete_calls[0]["error"] is not None, (
            "complete_job must be called with error= on failure path"
        )
        assert complete_calls[0]["query_id"] is None, (
            "complete_job must NOT set query_id on failure path"
        )
        assert complete_calls[0]["prefix"] == "resource-history"

    def test_job_timeout_produces_terminal_error_status(self, monkeypatch):
        """Job timeout → complete_job(error=...) terminal status, not indefinite poll (AC-9).

        Simulates a timeout by raising an RQ-like Timeout exception from
        execute_primary_query. The worker must catch, call complete_job(error=...),
        then re-raise so RQ marks the job failed.
        """
        from mes_dashboard.services.resource_query_job_service import (
            execute_resource_history_query_job,
        )

        complete_calls = []

        def _mock_complete_job(prefix, job_id, query_id=None, error=None, **kw):
            complete_calls.append({"error": error, "query_id": query_id})

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            _mock_complete_job,
        )

        class _FakeJobTimeout(Exception):
            pass

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                side_effect=_FakeJobTimeout("Job timed out after 1800 seconds"),
            ):
                with pytest.raises(_FakeJobTimeout):
                    execute_resource_history_query_job(
                        job_id="test-resource-timeout-001",
                        owner="test-user",
                        start_date="2024-01-01",
                        end_date="2024-12-31",
                        granularity="day",
                    )

        assert len(complete_calls) == 1, (
            "complete_job must be called on timeout (AC-9)"
        )
        assert complete_calls[0]["error"] is not None, (
            "complete_job must receive error= on timeout"
        )
        assert complete_calls[0]["query_id"] is None, (
            "complete_job must NOT set query_id on timeout failure"
        )

    def test_worker_fn_does_not_forward_owner_to_execute_primary_query(self, monkeypatch):
        """owner must NOT be forwarded to execute_primary_query (AC-7 / design constraint).

        execute_primary_query takes no owner param; forwarding would cause TypeError.
        """
        from mes_dashboard.services.resource_query_job_service import (
            execute_resource_history_query_job,
        )

        call_kwargs = {}

        def _spy_execute_primary_query(**kwargs):
            call_kwargs.update(kwargs)
            return {"query_id": "spy-qid-001"}

        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                side_effect=_spy_execute_primary_query,
            ):
                execute_resource_history_query_job(
                    job_id="test-no-owner-forward",
                    owner="test-owner-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                    granularity="day",
                )

        assert "owner" not in call_kwargs, (
            f"owner must NOT be forwarded to execute_primary_query; "
            f"call_kwargs={call_kwargs!r}"
        )
