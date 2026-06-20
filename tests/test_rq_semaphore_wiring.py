# -*- coding: utf-8 -*-
"""Unit tests for rq-semaphore-wiring.

IP-6: Written BEFORE implementation (TDD order).

Covers:
  TestHeavyQuerySlotCM       — contextmanager helper yields bool; guards release on fail-open
  TestPerWorkerWiring        — each of the 3 workers acquires exactly once, around Oracle phase
  TestFlagOffParity          — when module flag is OFF, heavy_query_slot is NOT called
  TestSlotReleasedOnException— exception in Oracle phase still releases the slot
  TestRejectWorkerAbsence    — AST proof: execute_reject_query_job has no job-level acquire

AC mapping:
  AC-4 → TestHeavyQuerySlotCM::test_slot_released_on_oracle_exception
  AC-4 → TestHeavyQuerySlotCM::test_next_job_acquires_after_exception
  AC-5 → TestFlagOffParity::test_*_flag_off_no_slot_acquire
  AC-6 → TestPerWorkerWiring::test_*_slot_acquired_once
  AC-6 → TestRejectWorkerAbsence::test_reject_job_has_no_job_level_acquire
  AC-6 → TestHeavyQuerySlotCM (via test_global_concurrency.py extension)
"""

from __future__ import annotations

import ast
import textwrap
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# TestHeavyQuerySlotCM — contextmanager helper (also covered in test_global_concurrency.py)
# ---------------------------------------------------------------------------

class TestHeavyQuerySlotCM:
    """Tests for the heavy_query_slot() contextmanager helper in global_concurrency.

    Duplicate-class note: test_global_concurrency.py has the canonical TestHeavyQuerySlotCM
    class; this class provides the AC-4 exception-release and next-acquire tests.
    Both classes share the same names defined in the test plan; only run them once
    by pointing targeted phase at both files.
    """

    def test_slot_released_on_oracle_exception(self):
        """AC-4: When Oracle phase raises, slot is still released (finally fires)."""
        import mes_dashboard.core.global_concurrency as gc_mod
        from mes_dashboard.core.global_concurrency import heavy_query_slot

        with patch.object(gc_mod, "acquire_heavy_query_slot", return_value=True) as mock_acq, \
             patch.object(gc_mod, "release_heavy_query_slot") as mock_rel:
            with pytest.raises(RuntimeError, match="oracle failure"):
                with heavy_query_slot("test-owner"):
                    raise RuntimeError("oracle failure")

        mock_rel.assert_called_once_with("test-owner")

    def test_next_job_acquires_after_exception(self):
        """AC-4: After a slot is released due to exception, the next acquire succeeds."""
        import mes_dashboard.core.global_concurrency as gc_mod
        from mes_dashboard.core.global_concurrency import heavy_query_slot

        acquire_results = [True, True]
        release_calls = []

        with patch.object(gc_mod, "acquire_heavy_query_slot", side_effect=acquire_results), \
             patch.object(gc_mod, "release_heavy_query_slot", side_effect=lambda o: release_calls.append(o)):
            # First job: raises
            with pytest.raises(RuntimeError):
                with heavy_query_slot("job-1"):
                    raise RuntimeError("first failure")

            # Second job: succeeds (slot was released above)
            with heavy_query_slot("job-2"):
                pass  # no exception

        assert len(release_calls) == 2, "Both jobs must release their slots"
        assert release_calls[0] == "job-1"
        assert release_calls[1] == "job-2"


# ---------------------------------------------------------------------------
# TestPerWorkerWiring — each worker acquires the slot exactly once
# ---------------------------------------------------------------------------

class TestPerWorkerWiring:
    """AC-6: Each wired worker acquires heavy_query_slot exactly once, around Oracle phase."""

    def _get_acquire_call_count(self, mock_cm):
        """Return the number of times the contextmanager was entered."""
        return mock_cm.call_count

    # ── query-tool ───────────────────────────────────────────────────────────

    def test_query_tool_slot_acquired_once(self, monkeypatch):
        """execute_query_tool_job acquires heavy_query_slot exactly once (AC-6)."""
        import mes_dashboard.services.query_tool_service as svc

        # Patch the feature flag ON so worker runs through the wired path
        monkeypatch.setattr(svc, "_QUERY_TOOL_CONCURRENCY_WIRED", True)

        acquire_count = []

        @contextmanager
        def _mock_slot(owner):
            acquire_count.append(owner)
            yield True

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch("mes_dashboard.services.async_query_job_service.update_job_progress"), \
             patch("mes_dashboard.services.async_query_job_service.complete_job"), \
             patch("mes_dashboard.services.query_tool_service.get_lot_history_batch",
                   return_value={"rows": [], "page": 1}), \
             patch("mes_dashboard.services.query_tool_service.heavy_query_slot", side_effect=_mock_slot), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=None):
            svc.execute_query_tool_job(
                job_id="qt-unit-001",
                owner="test-user",
                query_type="lot_history_batch",
                container_ids=["LOT001"],
            )

        assert len(acquire_count) == 1, (
            f"heavy_query_slot must be called exactly once; called {len(acquire_count)} times"
        )
        assert "qt-unit-001" in acquire_count[0] or "query-tool" in acquire_count[0], (
            f"owner string must identify the job; got {acquire_count[0]!r}"
        )

    # ── hold ─────────────────────────────────────────────────────────────────

    def test_hold_slot_acquired_once(self, monkeypatch):
        """execute_hold_history_query_job acquires heavy_query_slot exactly once (AC-6)."""
        import mes_dashboard.services.hold_query_job_service as svc

        monkeypatch.setattr(svc, "HOLD_ASYNC_ENABLED", True)

        acquire_count = []

        @contextmanager
        def _mock_slot(owner):
            acquire_count.append(owner)
            yield True

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch.object(svc, "update_job_progress"), \
             patch.object(svc, "complete_job"), \
             patch("mes_dashboard.services.hold_dataset_cache.execute_primary_query",
                   return_value={"query_id": "hold-qid-001"}), \
             patch("mes_dashboard.services.hold_query_job_service.heavy_query_slot",
                   side_effect=_mock_slot):
            svc.execute_hold_history_query_job(
                job_id="hold-unit-001",
                owner="test-user",
                start_date="2025-01-01",
                end_date="2025-06-01",
            )

        assert len(acquire_count) == 1, (
            f"heavy_query_slot must be called exactly once; called {len(acquire_count)} times"
        )

    # ── resource ─────────────────────────────────────────────────────────────

    def test_resource_slot_acquired_once(self, monkeypatch):
        """execute_resource_history_query_job acquires heavy_query_slot exactly once (AC-6)."""
        import mes_dashboard.services.resource_query_job_service as svc

        monkeypatch.setattr(svc, "RESOURCE_ASYNC_ENABLED", True)

        acquire_count = []

        @contextmanager
        def _mock_slot(owner):
            acquire_count.append(owner)
            yield True

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch.object(svc, "update_job_progress"), \
             patch.object(svc, "complete_job"), \
             patch("mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                   return_value={"query_id": "res-qid-001"}), \
             patch("mes_dashboard.services.resource_query_job_service.heavy_query_slot",
                   side_effect=_mock_slot):
            svc.execute_resource_history_query_job(
                job_id="res-unit-001",
                owner="test-user",
                start_date="2025-01-01",
                end_date="2025-06-01",
            )

        assert len(acquire_count) == 1, (
            f"heavy_query_slot must be called exactly once; called {len(acquire_count)} times"
        )


# ---------------------------------------------------------------------------
# TestFlagOffParity — when flag is OFF, heavy_query_slot is NOT called
# ---------------------------------------------------------------------------

class TestFlagOffParity:
    """AC-5: When the module-level feature flag is OFF, heavy_query_slot is never called."""

    def test_query_tool_flag_off_no_slot_acquire(self, monkeypatch):
        """When _QUERY_TOOL_CONCURRENCY_WIRED=False, no slot acquisition occurs (AC-5)."""
        import mes_dashboard.services.query_tool_service as svc

        monkeypatch.setattr(svc, "_QUERY_TOOL_CONCURRENCY_WIRED", False)

        slot_calls = []

        @contextmanager
        def _mock_slot(owner):
            slot_calls.append(owner)
            yield True

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch("mes_dashboard.services.async_query_job_service.update_job_progress"), \
             patch("mes_dashboard.services.async_query_job_service.complete_job"), \
             patch("mes_dashboard.services.query_tool_service.get_lot_history_batch",
                   return_value={"rows": [], "page": 1}), \
             patch("mes_dashboard.services.query_tool_service.heavy_query_slot",
                   side_effect=_mock_slot), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=None):
            svc.execute_query_tool_job(
                job_id="qt-flagoff-001",
                owner="test-user",
                query_type="lot_history_batch",
                container_ids=["LOT001"],
            )

        assert len(slot_calls) == 0, (
            "heavy_query_slot must NOT be called when _QUERY_TOOL_CONCURRENCY_WIRED=False"
        )

    def test_hold_flag_off_no_slot_acquire(self, monkeypatch):
        """When HOLD_ASYNC_ENABLED=False, no slot acquisition occurs (AC-5)."""
        import mes_dashboard.services.hold_query_job_service as svc

        monkeypatch.setattr(svc, "HOLD_ASYNC_ENABLED", False)

        slot_calls = []

        @contextmanager
        def _mock_slot(owner):
            slot_calls.append(owner)
            yield True

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch.object(svc, "update_job_progress"), \
             patch.object(svc, "complete_job"), \
             patch("mes_dashboard.services.hold_dataset_cache.execute_primary_query",
                   return_value={"query_id": "hold-flagoff-qid"}), \
             patch("mes_dashboard.services.hold_query_job_service.heavy_query_slot",
                   side_effect=_mock_slot):
            svc.execute_hold_history_query_job(
                job_id="hold-flagoff-001",
                owner="test-user",
                start_date="2025-01-01",
                end_date="2025-06-01",
            )

        assert len(slot_calls) == 0, (
            "heavy_query_slot must NOT be called when HOLD_ASYNC_ENABLED=False"
        )

    def test_resource_flag_off_no_slot_acquire(self, monkeypatch):
        """When RESOURCE_ASYNC_ENABLED=False, no slot acquisition occurs (AC-5)."""
        import mes_dashboard.services.resource_query_job_service as svc

        monkeypatch.setattr(svc, "RESOURCE_ASYNC_ENABLED", False)

        slot_calls = []

        @contextmanager
        def _mock_slot(owner):
            slot_calls.append(owner)
            yield True

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch.object(svc, "update_job_progress"), \
             patch.object(svc, "complete_job"), \
             patch("mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                   return_value={"query_id": "res-flagoff-qid"}), \
             patch("mes_dashboard.services.resource_query_job_service.heavy_query_slot",
                   side_effect=_mock_slot):
            svc.execute_resource_history_query_job(
                job_id="res-flagoff-001",
                owner="test-user",
                start_date="2025-01-01",
                end_date="2025-06-01",
            )

        assert len(slot_calls) == 0, (
            "heavy_query_slot must NOT be called when RESOURCE_ASYNC_ENABLED=False"
        )


# ---------------------------------------------------------------------------
# TestSlotReleasedOnException — exception in oracle phase releases slot
# ---------------------------------------------------------------------------

class TestSlotReleasedOnException:
    """AC-4: heavy_query_slot is released even when the Oracle phase raises."""

    def test_query_tool_slot_released_on_oracle_exception(self, monkeypatch):
        """execute_query_tool_job: slot released on exception within Oracle phase."""
        import mes_dashboard.services.query_tool_service as svc

        monkeypatch.setattr(svc, "_QUERY_TOOL_CONCURRENCY_WIRED", True)

        release_count = []

        @contextmanager
        def _mock_slot(owner):
            try:
                yield True
            finally:
                release_count.append(owner)

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch("mes_dashboard.services.async_query_job_service.update_job_progress"), \
             patch("mes_dashboard.services.async_query_job_service.complete_job"), \
             patch("mes_dashboard.services.query_tool_service.get_lot_history_batch",
                   side_effect=RuntimeError("oracle down")), \
             patch("mes_dashboard.services.query_tool_service.heavy_query_slot",
                   side_effect=_mock_slot), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=None):
            with pytest.raises(RuntimeError, match="oracle down"):
                svc.execute_query_tool_job(
                    job_id="qt-exc-001",
                    owner="test-user",
                    query_type="lot_history_batch",
                    container_ids=["LOT001"],
                )

        assert len(release_count) == 1, "slot must be released exactly once on exception"

    def test_hold_slot_released_on_oracle_exception(self, monkeypatch):
        """execute_hold_history_query_job: slot released on exception within Oracle phase."""
        import mes_dashboard.services.hold_query_job_service as svc

        monkeypatch.setattr(svc, "HOLD_ASYNC_ENABLED", True)

        release_count = []

        @contextmanager
        def _mock_slot(owner):
            try:
                yield True
            finally:
                release_count.append(owner)

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch.object(svc, "update_job_progress"), \
             patch.object(svc, "complete_job"), \
             patch("mes_dashboard.services.hold_dataset_cache.execute_primary_query",
                   side_effect=RuntimeError("oracle timeout")), \
             patch("mes_dashboard.services.hold_query_job_service.heavy_query_slot",
                   side_effect=_mock_slot):
            with pytest.raises(RuntimeError, match="oracle timeout"):
                svc.execute_hold_history_query_job(
                    job_id="hold-exc-001",
                    owner="test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                )

        assert len(release_count) == 1, "slot must be released exactly once on exception"

    def test_resource_slot_released_on_oracle_exception(self, monkeypatch):
        """execute_resource_history_query_job: slot released on exception within Oracle phase."""
        import mes_dashboard.services.resource_query_job_service as svc

        monkeypatch.setattr(svc, "RESOURCE_ASYNC_ENABLED", True)

        release_count = []

        @contextmanager
        def _mock_slot(owner):
            try:
                yield True
            finally:
                release_count.append(owner)

        with patch("mes_dashboard.rq_worker_preload.ensure_rq_logging"), \
             patch.object(svc, "update_job_progress"), \
             patch.object(svc, "complete_job"), \
             patch("mes_dashboard.services.resource_dataset_cache.execute_primary_query",
                   side_effect=RuntimeError("ORA-01000 max open cursors")), \
             patch("mes_dashboard.services.resource_query_job_service.heavy_query_slot",
                   side_effect=_mock_slot):
            with pytest.raises(RuntimeError, match="ORA-01000"):
                svc.execute_resource_history_query_job(
                    job_id="res-exc-001",
                    owner="test-user",
                    start_date="2025-01-01",
                    end_date="2025-06-01",
                )

        assert len(release_count) == 1, "slot must be released exactly once on exception"


# ---------------------------------------------------------------------------
# TestRejectWorkerAbsence — AST proof: no job-level acquire in execute_reject_query_job
# ---------------------------------------------------------------------------

class TestRejectWorkerAbsence:
    """AC-6 (reject): execute_reject_query_job has NO job-level acquire_heavy_query_slot call.

    Per design D3: reject's execute_primary_query already acquires internally
    in reject_dataset_cache. Adding a job-level acquire would double-count.
    Uses ast.parse() to prove the absence (test-discipline.md pattern).
    """

    def test_reject_job_has_no_job_level_acquire(self):
        """execute_reject_query_job body must NOT call acquire_heavy_query_slot or heavy_query_slot."""
        src_path = Path(__file__).parent.parent / (
            "src/mes_dashboard/services/reject_query_job_service.py"
        )
        source = src_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Find execute_reject_query_job function body
        fn_body = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "execute_reject_query_job":
                fn_body = node
                break

        assert fn_body is not None, "execute_reject_query_job not found in reject_query_job_service.py"

        # Walk the function body looking for calls to acquire_heavy_query_slot or heavy_query_slot
        forbidden_names = {"acquire_heavy_query_slot", "heavy_query_slot"}
        bad_calls = []
        for node in ast.walk(fn_body):
            if isinstance(node, ast.Call):
                # Direct call: acquire_heavy_query_slot(...)
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_names:
                    bad_calls.append(node.func.id)
                # Attribute call: gc.acquire_heavy_query_slot(...) or module.heavy_query_slot(...)
                elif isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_names:
                    bad_calls.append(node.func.attr)

        assert len(bad_calls) == 0, (
            f"execute_reject_query_job must NOT call {forbidden_names} at job level "
            f"(reject acquires internally in reject_dataset_cache); found: {bad_calls}"
        )
