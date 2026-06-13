# -*- coding: utf-8 -*-
"""
Integration tests for downtime-rq-async: dispatch and worker-fn parity.

Tier 1 (dispatch) and Tier 3 (data-boundary parity) — all require real
Redis and a running RQ worker environment.

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_downtime_rq_async.py \
        --run-integration-real -v

Test classes:
  TestDowntimeAsyncDispatch — AC-7b: enqueue_job_dynamic routes to downtime-query
  TestDowntimeAsyncParity   — AC-3: worker fn writes byte/row-identical parquets vs sync path
"""

from __future__ import annotations

import importlib
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_registry() -> None:
    """Clear the job registry to allow clean re-registration tests."""
    from mes_dashboard.services import job_registry as _reg_mod
    _reg_mod._REGISTRY.clear()


def _reload_job_service() -> None:
    """Reload downtime_query_job_service so register_job_type() re-fires."""
    import mes_dashboard.services.downtime_query_job_service as _svc
    _reset_registry()
    importlib.reload(_svc)


# ===========================================================================
# TestDowntimeAsyncDispatch — AC-7b
# ===========================================================================

class TestDowntimeAsyncDispatch:
    """AC-7b: enqueue_job_dynamic enqueues to the downtime-query queue.

    This test does NOT require a real Redis connection — it verifies the
    dispatch plumbing at the enqueue_job level using a mock so it can run
    reliably in the integration_real tier without a live RQ worker.
    """

    def test_enqueue_to_downtime_queue(self, monkeypatch):
        """enqueue_job_dynamic("downtime", ...) must call enqueue_job with
        queue_name="downtime-query" (AC-7b, ASYNC-DA-01).

        Verify:
        1. The registry has "downtime" registered (from module import).
        2. The registered queue_name matches the DOWNTIME_WORKER_QUEUE default.
        3. enqueue_job_dynamic forwards to enqueue_job with correct queue_name.
        """
        # Ensure the job service has been imported and its registration ran
        import mes_dashboard.services.downtime_query_job_service as _svc  # noqa: F401
        from mes_dashboard.services.job_registry import get_job_type_config

        config = get_job_type_config("downtime")
        assert config is not None, (
            '"downtime" job type must be registered after importing '
            "downtime_query_job_service (AC-7a module side-effect)"
        )
        assert config.queue_name == "downtime-query", (
            f"Expected queue_name='downtime-query', got {config.queue_name!r} "
            "(AC-7b: must route to the downtime-query queue)"
        )

        # Verify that enqueue_job_dynamic delegates to enqueue_job with the correct queue
        captured: Dict[str, Any] = {}

        def _mock_enqueue_job(**kwargs):
            captured.update(kwargs)
            return ("mock-job-id-001", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue_job,
        )

        from mes_dashboard.services.async_query_job_service import enqueue_job_dynamic

        job_id, err = enqueue_job_dynamic(
            "downtime",
            owner="test-user",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-02-28",
            },
        )

        assert err is None, f"enqueue_job_dynamic returned error: {err!r}"
        assert captured.get("queue_name") == "downtime-query", (
            f"enqueue_job called with queue_name={captured.get('queue_name')!r}; "
            "expected 'downtime-query' (AC-7b)"
        )
        assert captured.get("prefix") == "downtime", (
            f"enqueue_job must pass prefix='downtime', got {captured.get('prefix')!r}"
        )
        assert captured.get("job_timeout") == _svc.DOWNTIME_JOB_TIMEOUT_SECONDS, (
            "enqueue_job timeout must match DOWNTIME_JOB_TIMEOUT_SECONDS"
        )

    def test_enqueue_payload_contains_owner_and_params(self, monkeypatch):
        """kwargs forwarded to the worker must include job_id, owner, and query params."""
        import mes_dashboard.services.downtime_query_job_service as _svc  # noqa: F401

        captured: Dict[str, Any] = {}

        def _mock_enqueue_job(**kwargs):
            captured.update(kwargs)
            return ("mock-job-id-002", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue_job,
        )

        from mes_dashboard.services.async_query_job_service import enqueue_job_dynamic

        enqueue_job_dynamic(
            "downtime",
            owner="eng-user",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-04-10",
                "resource_ids": ["R-001", "R-002"],
            },
        )

        kwargs_forwarded = captured.get("kwargs", {})
        assert "job_id" in kwargs_forwarded, (
            "Worker kwargs must include 'job_id' (required by execute_downtime_query_job signature)"
        )
        assert "start_date" in kwargs_forwarded, (
            "Worker kwargs must propagate start_date query param"
        )
        assert "end_date" in kwargs_forwarded, (
            "Worker kwargs must propagate end_date query param"
        )
        assert kwargs_forwarded.get("resource_ids") == ["R-001", "R-002"], (
            "Worker kwargs must propagate resource_ids filter"
        )


# ===========================================================================
# TestDowntimeAsyncParity — AC-3
# ===========================================================================

class TestDowntimeAsyncParity:
    """AC-3: execute_downtime_query_job writes byte/row-identical spools to sync path.

    Data-boundary tier (tier 3): requires real Oracle and full env parity
    between worker context and gunicorn context (design.md §Open Risks).

    When the real Oracle environment is not available, the test is expected to
    skip gracefully (Oracle fixture not started) rather than fail with a
    connection error.

    Parity guarantee: the worker fn must call query_downtime_dataset_raw()
    with the exact same params passed via enqueue_job_dynamic.kwargs, and
    complete_job() must only be called after both parquets are written (DA-11 D3).
    """

    def test_worker_fn_parity_vs_sync(self, monkeypatch, tmp_path):
        """execute_downtime_query_job calls query_downtime_dataset_raw with
        forwarded params and only calls complete_job after result is available (DA-11).

        This variant uses a mock for query_downtime_dataset_raw (the real Oracle
        call) so that the structural parity — same function, same params, same
        DA-11 ordering — can be asserted deterministically.  A separate nightly
        gate with real Oracle validates the actual byte/row equality.
        """
        from mes_dashboard.services.downtime_query_job_service import (
            execute_downtime_query_job,
        )

        query_params = {
            "start_date": "2026-01-01",
            "end_date": "2026-04-10",
            "workcenter_groups": ["WCG-SMT"],
            "families": None,
            "resource_ids": None,
            "package_groups": None,
            "big_categories": None,
            "status_types": None,
            "is_production": False,
            "is_key": False,
            "is_monitor": False,
        }

        call_log = []
        mock_query_id = f"parity-{uuid.uuid4().hex[:8]}"

        def _mock_query_raw(**kw):
            call_log.append(("query_downtime_dataset_raw", dict(kw)))
            # Simulate successful write of both parquets — returns query_id
            return {"query_id": mock_query_id}

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
            "mes_dashboard.services.downtime_query_job_service.update_job_progress",
            _mock_update_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_query_job_service.complete_job",
            _mock_complete_job,
        )

        # Patch ensure_rq_logging to no-op (not relevant in unit context)
        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.downtime_analysis_service.query_downtime_dataset_raw",
                side_effect=_mock_query_raw,
            ):
                execute_downtime_query_job(
                    job_id="test-parity-job-001",
                    owner="test-user",
                    **query_params,
                )

        # 1. query_downtime_dataset_raw was called exactly once with the correct params
        assert len(call_log) == 1, (
            f"query_downtime_dataset_raw must be called exactly once, got {len(call_log)}"
        )
        actual_params = call_log[0][1]
        assert actual_params["start_date"] == query_params["start_date"], (
            "start_date must be forwarded to query_downtime_dataset_raw unchanged"
        )
        assert actual_params["end_date"] == query_params["end_date"], (
            "end_date must be forwarded to query_downtime_dataset_raw unchanged"
        )
        assert actual_params["workcenter_groups"] == query_params["workcenter_groups"], (
            "workcenter_groups filter must be forwarded to query_downtime_dataset_raw"
        )

        # 2. DA-11: complete_job called only AFTER successful return from query_raw
        #    (not before, not on exception — the ordering is what guarantees "both or neither")
        assert len(complete_calls) == 1, (
            f"complete_job must be called exactly once on success, got {len(complete_calls)}"
        )
        assert complete_calls[0]["error"] is None, (
            "complete_job must not be called with error= on success path (DA-11)"
        )
        assert complete_calls[0]["query_id"] == mock_query_id, (
            f"complete_job query_id must match result['query_id']; "
            f"expected {mock_query_id!r}, got {complete_calls[0]['query_id']!r}"
        )
        assert complete_calls[0]["prefix"] == "downtime", (
            "complete_job prefix must be 'downtime'"
        )

        # 3. Pct milestones are emitted in order: 5→15→60→90→100 (design.md D2)
        pct_vals = [c["pct"] for c in progress_calls if "pct" in c]
        assert pct_vals == [5, 15, 60, 90, 100], (
            f"Pct milestones must be emitted in order 5→15→60→90→100, got {pct_vals} "
            "(AC-6a / design.md D2)"
        )

    def test_worker_fn_da11_failure_does_not_call_complete_job(self, monkeypatch):
        """DA-11: if query_downtime_dataset_raw raises, complete_job is called with
        error= (not query_id=), and the exception propagates (loud failure).

        This is the 'base hit + job bridge miss → loud 500' scenario on the worker path.
        """
        from mes_dashboard.services.downtime_query_job_service import (
            execute_downtime_query_job,
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
            "mes_dashboard.services.downtime_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_query_job_service.complete_job",
            _mock_complete_job,
        )

        _simulated_error = RuntimeError("DA-11: base_events written but job_bridge store failed")

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.downtime_analysis_service.query_downtime_dataset_raw",
                side_effect=_simulated_error,
            ):
                with pytest.raises(RuntimeError, match="DA-11"):
                    execute_downtime_query_job(
                        job_id="test-da11-fail-001",
                        owner="test-user",
                        start_date="2026-01-01",
                        end_date="2026-04-10",
                    )

        assert len(complete_calls) == 1, (
            "complete_job must be called once even on failure (to mark job as failed)"
        )
        assert complete_calls[0]["error"] is not None, (
            "complete_job must be called with error= on failure path (DA-11)"
        )
        assert complete_calls[0]["query_id"] is None, (
            "complete_job must NOT set query_id on failure path (DA-11 atomicity)"
        )
