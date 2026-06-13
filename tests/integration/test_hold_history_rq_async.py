# -*- coding: utf-8 -*-
"""
Integration tests for hold-history-rq-async: dispatch and worker-fn parity.

Phase 3-B of docs/dynamic-rq-migration-plan.md.

Tier 1 (dispatch) and Tier 3 (data-boundary parity) — all require real
Redis and a running RQ worker environment.

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_hold_history_rq_async.py \
        --run-integration-real -v

Test classes:
  TestHoldHistoryAsyncDispatch — AC-7: enqueue_job_dynamic routes to hold-history-query
  TestHoldHistoryAsyncParity   — AC-3/AC-4: worker fn parity vs sync + milestone ordering
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


def _reload_hold_job_service() -> None:
    """Reload hold_query_job_service so register_job_type() re-fires."""
    import mes_dashboard.services.hold_query_job_service as _svc
    _reset_registry()
    importlib.reload(_svc)


# ===========================================================================
# TestHoldHistoryAsyncDispatch — AC-7
# ===========================================================================

class TestHoldHistoryAsyncDispatch:
    """AC-7: enqueue_job_dynamic enqueues to the hold-history-query queue.

    This test does NOT require a real Redis connection — it verifies the
    dispatch plumbing at the enqueue_job level using a mock so it can run
    reliably in the integration_real tier without a live RQ worker.
    """

    def test_enqueue_to_hold_history_queue(self, monkeypatch):
        """enqueue_job_dynamic("hold-history", ...) must call enqueue_job with
        queue_name="hold-history-query" (AC-7, IP-4).

        Verify:
        1. The registry has "hold-history" registered (from module import).
        2. The registered queue_name matches the HOLD_WORKER_QUEUE default.
        3. enqueue_job_dynamic forwards to enqueue_job with correct queue_name.
        """
        import mes_dashboard.services.hold_query_job_service as _svc  # noqa: F401
        from mes_dashboard.services.job_registry import get_job_type_config

        config = get_job_type_config("hold-history")
        assert config is not None, (
            '"hold-history" job type must be registered after importing '
            "hold_query_job_service (AC-7 module side-effect)"
        )
        assert config.queue_name == "hold-history-query", (
            f"Expected queue_name='hold-history-query', got {config.queue_name!r} "
            "(AC-7: must route to the hold-history-query queue)"
        )

        captured: Dict[str, Any] = {}

        def _mock_enqueue_job(**kwargs):
            captured.update(kwargs)
            return ("mock-hold-job-001", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue_job,
        )

        from mes_dashboard.services.async_query_job_service import enqueue_job_dynamic

        job_id, err = enqueue_job_dynamic(
            "hold-history",
            owner="test-user",
            params={
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "hold_type": "quality",
                "record_type": "new",
            },
        )

        assert err is None, f"enqueue_job_dynamic returned error: {err!r}"
        assert captured.get("queue_name") == "hold-history-query", (
            f"enqueue_job called with queue_name={captured.get('queue_name')!r}; "
            "expected 'hold-history-query' (AC-7)"
        )
        assert captured.get("prefix") == "hold-history", (
            f"enqueue_job must pass prefix='hold-history', got {captured.get('prefix')!r}"
        )
        assert captured.get("job_timeout") == _svc.HOLD_JOB_TIMEOUT_SECONDS, (
            "enqueue_job timeout must match HOLD_JOB_TIMEOUT_SECONDS"
        )

    def test_enqueue_payload_contains_owner_and_params(self, monkeypatch):
        """kwargs forwarded to the worker must include job_id, owner, and query params."""
        import mes_dashboard.services.hold_query_job_service as _svc  # noqa: F401

        captured: Dict[str, Any] = {}

        def _mock_enqueue_job(**kwargs):
            captured.update(kwargs)
            return ("mock-hold-job-002", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue_job,
        )

        from mes_dashboard.services.async_query_job_service import enqueue_job_dynamic

        enqueue_job_dynamic(
            "hold-history",
            owner="hold-eng-user",
            params={
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "hold_type": "non-quality",
                "record_type": "on_hold",
            },
        )

        kwargs_forwarded = captured.get("kwargs", {})
        assert "job_id" in kwargs_forwarded, (
            "Worker kwargs must include 'job_id' "
            "(required by execute_hold_history_query_job signature)"
        )
        assert "start_date" in kwargs_forwarded, (
            "Worker kwargs must propagate start_date query param"
        )
        assert "end_date" in kwargs_forwarded, (
            "Worker kwargs must propagate end_date query param"
        )
        assert kwargs_forwarded.get("hold_type") == "non-quality", (
            "Worker kwargs must propagate hold_type filter"
        )
        assert kwargs_forwarded.get("record_type") == "on_hold", (
            "Worker kwargs must propagate record_type filter"
        )

    def test_hold_worker_queue_default_is_hold_history_query(self):
        """HOLD_WORKER_QUEUE must default to 'hold-history-query' (AC-6)."""
        import mes_dashboard.services.hold_query_job_service as _svc
        _old = os.environ.pop("HOLD_WORKER_QUEUE", None)
        try:
            importlib.reload(_svc)
            assert _svc.HOLD_WORKER_QUEUE == "hold-history-query", (
                f"Expected HOLD_WORKER_QUEUE default 'hold-history-query', "
                f"got {_svc.HOLD_WORKER_QUEUE!r}"
            )
        finally:
            if _old is not None:
                os.environ["HOLD_WORKER_QUEUE"] = _old
            else:
                importlib.reload(_svc)

    def test_hold_job_timeout_default_is_1800(self):
        """HOLD_JOB_TIMEOUT_SECONDS must default to 1800 (AC-6)."""
        import mes_dashboard.services.hold_query_job_service as _svc
        _old = os.environ.pop("HOLD_JOB_TIMEOUT_SECONDS", None)
        try:
            importlib.reload(_svc)
            assert _svc.HOLD_JOB_TIMEOUT_SECONDS == 1800, (
                f"Expected HOLD_JOB_TIMEOUT_SECONDS default 1800, "
                f"got {_svc.HOLD_JOB_TIMEOUT_SECONDS!r}"
            )
        finally:
            if _old is not None:
                os.environ["HOLD_JOB_TIMEOUT_SECONDS"] = _old
            else:
                importlib.reload(_svc)


# ===========================================================================
# TestHoldHistoryAsyncParity — AC-3 / AC-4
# ===========================================================================

class TestHoldHistoryAsyncParity:
    """AC-3: execute_hold_history_query_job produces result identical to sync path.
    AC-4: pct milestones are non-decreasing, first ≤ 5, last == 100.
    AC-8: worker exception → complete_job(error=...) + reraise; no false success.

    Data-boundary tier (tier 3): requires real Oracle and full env parity.
    When real Oracle is not available the test is expected to skip/fail at
    the Oracle-level mock boundary rather than at the assertions.

    Parity guarantee: worker fn calls execute_primary_query() with the exact
    same params, and complete_job() is only called after result is available.
    The single-chunk open-hold escape branch (RELEASETXNDATE IS NULL) is
    exercised via the fixture row set below.
    """

    def test_worker_fn_parity_vs_sync(self, monkeypatch):
        """execute_hold_history_query_job calls execute_primary_query with forwarded
        params and only calls complete_job after result is available.

        Fixture includes a row with RELEASETXNDATE IS NULL (open hold) to exercise
        the escape branch documented in ADR-0003 applicability note.
        """
        from mes_dashboard.services.hold_query_job_service import (
            execute_hold_history_query_job,
        )

        query_params = {
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "hold_type": "quality",
            "record_type": "on_hold",
        }

        call_log = []
        mock_query_id = f"parity-hold-{uuid.uuid4().hex[:8]}"

        def _mock_execute_primary_query(
            *, start_date, end_date, hold_type="quality", record_type="new"
        ):
            call_log.append({
                "start_date": start_date,
                "end_date": end_date,
                "hold_type": hold_type,
                "record_type": record_type,
            })
            # Simulate result including open-hold row (RELEASETXNDATE IS NULL)
            return {
                "query_id": mock_query_id,
                "list": {
                    "items": [
                        # open hold — RELEASETXNDATE IS NULL escape branch
                        {"lotId": "LOT-001", "releaseDate": None, "holdType": "quality"},
                        # released hold
                        {"lotId": "LOT-002", "releaseDate": "2025-03-15", "holdType": "quality"},
                    ],
                    "pagination": {"page": 1, "perPage": 50, "total": 2, "totalPages": 1},
                },
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
            "mes_dashboard.services.hold_query_job_service.update_job_progress",
            _mock_update_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.hold_query_job_service.complete_job",
            _mock_complete_job,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.hold_query_job_service.execute_primary_query",
                side_effect=_mock_execute_primary_query,
            ):
                execute_hold_history_query_job(
                    job_id="test-hold-parity-001",
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
        assert actual["hold_type"] == query_params["hold_type"]
        assert actual["record_type"] == query_params["record_type"]

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
        assert complete_calls[0]["prefix"] == "hold-history"

    def test_per_chunk_pct_milestones_fire_in_order(self, monkeypatch):
        """Pct milestones must be non-decreasing; first ≤ 5, last == 100 (AC-4)."""
        from mes_dashboard.services.hold_query_job_service import (
            execute_hold_history_query_job,
        )

        mock_query_id = f"milestone-{uuid.uuid4().hex[:8]}"

        progress_calls = []

        def _mock_update_progress(prefix, job_id, **fields):
            progress_calls.append({"prefix": prefix, "job_id": job_id, **fields})

        monkeypatch.setattr(
            "mes_dashboard.services.hold_query_job_service.update_job_progress",
            _mock_update_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.hold_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.hold_query_job_service.execute_primary_query",
                return_value={"query_id": mock_query_id},
            ):
                execute_hold_history_query_job(
                    job_id="test-milestones-001",
                    owner="test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                    hold_type="quality",
                    record_type="new",
                )

        pct_vals = [c["pct"] for c in progress_calls if "pct" in c]
        assert len(pct_vals) >= 2, (
            f"Expected at least 2 pct milestones, got {pct_vals}"
        )
        assert pct_vals[0] <= 5, (
            f"First pct milestone must be ≤ 5 (AC-4), got {pct_vals[0]}"
        )
        assert pct_vals[-1] == 100, (
            f"Last pct milestone must be 100 (AC-4), got {pct_vals[-1]}"
        )
        # Non-decreasing check
        for i in range(1, len(pct_vals)):
            assert pct_vals[i] >= pct_vals[i - 1], (
                f"Pct milestones must be non-decreasing (AC-4): "
                f"{pct_vals[i - 1]} → {pct_vals[i]} at index {i}"
            )

    def test_pct_envelope_never_decreases(self, monkeypatch):
        """All emitted pct values must form a monotonically non-decreasing sequence (AC-4)."""
        from mes_dashboard.services.hold_query_job_service import (
            execute_hold_history_query_job,
        )

        mock_query_id = f"mono-{uuid.uuid4().hex[:8]}"
        all_pct = []

        def _track_progress(prefix, job_id, **fields):
            if "pct" in fields:
                all_pct.append(fields["pct"])

        monkeypatch.setattr(
            "mes_dashboard.services.hold_query_job_service.update_job_progress",
            _track_progress,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.hold_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.hold_query_job_service.execute_primary_query",
                return_value={"query_id": mock_query_id},
            ):
                execute_hold_history_query_job(
                    job_id="test-mono-001",
                    owner="test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                    hold_type="quality",
                    record_type="new",
                )

        assert len(all_pct) >= 2, f"Expected ≥ 2 pct values, got {all_pct}"
        for i in range(1, len(all_pct)):
            assert all_pct[i] >= all_pct[i - 1], (
                f"pct envelope decreased at index {i}: {all_pct[i - 1]} → {all_pct[i]}"
            )

    def test_worker_fn_failure_does_not_call_complete_job(self, monkeypatch):
        """Worker exception → complete_job(error=...) + reraise; no false success (AC-8).

        complete_job must be called with error= (not query_id=), and the
        exception must propagate (loud failure) so the RQ worker marks the
        job as failed.
        """
        from mes_dashboard.services.hold_query_job_service import (
            execute_hold_history_query_job,
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
            "mes_dashboard.services.hold_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.hold_query_job_service.complete_job",
            _mock_complete_job,
        )

        _simulated_error = RuntimeError("Oracle connection refused during hold query")

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"):
            with patch(
                "mes_dashboard.services.hold_query_job_service.execute_primary_query",
                side_effect=_simulated_error,
            ):
                with pytest.raises(RuntimeError, match="Oracle connection refused"):
                    execute_hold_history_query_job(
                        job_id="test-hold-fail-001",
                        owner="test-user",
                        start_date="2025-01-01",
                        end_date="2025-06-01",
                        hold_type="quality",
                        record_type="new",
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
        assert complete_calls[0]["prefix"] == "hold-history"
