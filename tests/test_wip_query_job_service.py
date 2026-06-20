# -*- coding: utf-8 -*-
"""Unit tests for wip_query_job_service.py — WIP detail async RQ worker.

TDD: tests written BEFORE implementation.
Covers AC-4 (no Oracle at enqueue; slot wraps Oracle phase only at pct 15→90),
AC-6 (merge_chunks absent from new module via ast.parse).

Change: wip-rq-worker-chunks-cleanup
"""
from __future__ import annotations

import ast
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_SERVICE_PATH = _REPO_ROOT / "src/mes_dashboard/services/wip_query_job_service.py"


# ---------------------------------------------------------------------------
# AC-6: merge_chunks must NOT appear in the new module (ast.parse proof)
# ---------------------------------------------------------------------------

class TestMergeChunksAbsentFromModule:
    def test_merge_chunks_not_referenced_in_wip_query_job_service(self):
        """AC-6: wip_query_job_service.py must not reference merge_chunks.

        Uses ast.parse() + ast.walk to prove absence at the AST level (not grep).
        merge_chunks_to_spool is allowed; only the deprecated bare merge_chunks
        must be absent.
        """
        assert _SERVICE_PATH.exists(), (
            f"wip_query_job_service.py must exist at {_SERVICE_PATH}"
        )
        source = _SERVICE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_SERVICE_PATH))

        # Walk all Name and Attribute nodes looking for bare "merge_chunks"
        # (not "merge_chunks_to_spool" — that is allowed)
        forbidden_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "merge_chunks":
                forbidden_names.add(node.id)
            elif isinstance(node, ast.Attribute) and node.attr == "merge_chunks":
                # attr access like bqe.merge_chunks
                if not node.attr.endswith("_to_spool"):
                    forbidden_names.add(node.attr)

        assert not forbidden_names, (
            f"wip_query_job_service.py references merge_chunks: {forbidden_names}. "
            "Only merge_chunks_to_spool is allowed."
        )

    def test_merge_chunks_string_not_in_service_source(self):
        """AC-6: bare 'merge_chunks' token does not appear in the source (belt+suspenders)."""
        assert _SERVICE_PATH.exists(), (
            f"wip_query_job_service.py must exist at {_SERVICE_PATH}"
        )
        source = _SERVICE_PATH.read_text(encoding="utf-8")
        # Strip out merge_chunks_to_spool occurrences first, then check for merge_chunks
        cleaned = source.replace("merge_chunks_to_spool", "__ALLOWED__")
        assert "merge_chunks" not in cleaned, (
            "wip_query_job_service.py must not reference the deprecated merge_chunks function. "
            "Use merge_chunks_to_spool or direct parquet write instead."
        )


# ---------------------------------------------------------------------------
# AC-1: "wip-detail" registered in job registry
# ---------------------------------------------------------------------------

class TestWipDetailJobRegistration:
    def test_wip_detail_registered_after_import(self):
        """AC-1: Importing wip_query_job_service registers 'wip-detail' job type."""
        import importlib
        import mes_dashboard.services.job_registry as jr

        jr._REGISTRY.clear()

        import mes_dashboard.services.wip_query_job_service as wip_svc
        importlib.reload(wip_svc)

        config = jr.get_job_type_config("wip-detail")
        assert config is not None, "'wip-detail' job type must be registered after import"
        assert config.job_type == "wip-detail"
        assert config.queue_name == wip_svc.WIP_WORKER_QUEUE
        assert config.worker_fn is wip_svc.execute_wip_detail_job
        assert config.always_async is False

    def test_wip_detail_queue_default(self):
        """AC-1: WIP_WORKER_QUEUE defaults to 'wip-detail-query' when env var absent."""
        import importlib
        import mes_dashboard.services.wip_query_job_service as wip_svc
        # Reload to ensure default is tested
        importlib.reload(wip_svc)
        assert wip_svc.WIP_WORKER_QUEUE == "wip-detail-query"

    def test_wip_job_timeout_default(self):
        """AC-1: WIP_JOB_TIMEOUT_SECONDS defaults to 1800."""
        import importlib
        import mes_dashboard.services.wip_query_job_service as wip_svc
        importlib.reload(wip_svc)
        assert wip_svc.WIP_JOB_TIMEOUT_SECONDS == 1800

    def test_wip_spool_ttl_default(self):
        """AC-1: WIP_SPOOL_TTL defaults to 72000."""
        import importlib
        import mes_dashboard.services.wip_query_job_service as wip_svc
        importlib.reload(wip_svc)
        assert wip_svc.WIP_SPOOL_TTL == 72000


# ---------------------------------------------------------------------------
# AC-4: No Oracle at enqueue; slot only inside worker (wraps pct 15→90)
# ---------------------------------------------------------------------------

class TestExecuteWipDetailJobSlotPlacement:
    """Tests that the slot wraps the Oracle phase only (pct 15→90) and
    spool/complete_job are OUTSIDE the slot."""

    def _setup_monkeypatches(self, monkeypatch, wip_svc, preload):
        """Apply all patches before threads run (test-discipline.md rule)."""
        monkeypatch.setattr(wip_svc, "update_job_progress", MagicMock())
        monkeypatch.setattr(wip_svc, "complete_job", MagicMock())
        monkeypatch.setattr(preload, "ensure_rq_logging", lambda: None)

    def test_slot_entered_exactly_once_per_job(self, monkeypatch):
        """AC-4: heavy_query_slot is entered exactly once per worker call."""
        import mes_dashboard.services.wip_query_job_service as wip_svc
        import mes_dashboard.rq_worker_preload as preload

        self._setup_monkeypatches(monkeypatch, wip_svc, preload)

        slot_enter_count = [0]

        @contextmanager
        def _recording_slot(owner: str):
            slot_enter_count[0] += 1
            try:
                yield True
            finally:
                pass

        monkeypatch.setattr(wip_svc, "heavy_query_slot", _recording_slot)

        # Mock the Oracle query helper in wip_service
        mock_query_result = {
            "query_id": "abc123def456",
            "spool_path": "/tmp/fake.parquet",
            "row_count": 5,
        }
        monkeypatch.setattr(
            wip_svc, "execute_wip_detail_oracle_query",
            MagicMock(return_value=mock_query_result),
        )

        wip_svc.execute_wip_detail_job(
            job_id="test-job-001",
            owner="test-user",
            workcenter="焊接_DB",
        )

        assert slot_enter_count[0] == 1, (
            f"Expected 1 slot enter; got {slot_enter_count[0]}. "
            "heavy_query_slot must wrap Oracle phase exactly once."
        )

    def test_slot_released_on_oracle_exception(self, monkeypatch):
        """AC-4 / AC-8: Slot is released even when Oracle query raises."""
        import mes_dashboard.services.wip_query_job_service as wip_svc
        import mes_dashboard.rq_worker_preload as preload

        self._setup_monkeypatches(monkeypatch, wip_svc, preload)

        slot_releases = [0]

        @contextmanager
        def _recording_slot(owner: str):
            try:
                yield True
            finally:
                slot_releases[0] += 1

        monkeypatch.setattr(wip_svc, "heavy_query_slot", _recording_slot)
        monkeypatch.setattr(
            wip_svc, "execute_wip_detail_oracle_query",
            MagicMock(side_effect=RuntimeError("Oracle timeout")),
        )

        with pytest.raises(RuntimeError, match="Oracle timeout"):
            wip_svc.execute_wip_detail_job(
                job_id="fault-job-001",
                owner="test-user",
                workcenter="焊接_DB",
            )

        assert slot_releases[0] == 1, (
            f"Slot must be released (finally block) even on exception; got {slot_releases[0]}"
        )

    def test_progress_sequence_non_decreasing(self, monkeypatch):
        """AC-4: Progress milestones are emitted in order 5, 15, 90, 100."""
        import mes_dashboard.services.wip_query_job_service as wip_svc
        import mes_dashboard.rq_worker_preload as preload

        self._setup_monkeypatches(monkeypatch, wip_svc, preload)

        progress_calls = []

        def _capture_progress(prefix, job_id, **kwargs):
            progress_calls.append(kwargs.get("pct"))

        monkeypatch.setattr(wip_svc, "update_job_progress", _capture_progress)

        @contextmanager
        def _noop_slot(owner: str):
            yield True

        monkeypatch.setattr(wip_svc, "heavy_query_slot", _noop_slot)
        monkeypatch.setattr(
            wip_svc, "execute_wip_detail_oracle_query",
            MagicMock(return_value={"query_id": "abc123", "spool_path": None, "row_count": 0}),
        )

        wip_svc.execute_wip_detail_job(
            job_id="progress-job-001",
            owner="test-user",
            workcenter="焊接_DB",
        )

        # Non-decreasing check
        assert len(progress_calls) >= 3, (
            f"Expected at least 3 progress updates; got {progress_calls}"
        )
        assert progress_calls == sorted(progress_calls), (
            f"Progress must be non-decreasing; got {progress_calls}"
        )
        assert progress_calls[0] <= 5, f"First pct must be ≤ 5; got {progress_calls[0]}"
        assert progress_calls[-1] == 100, f"Final pct must be 100; got {progress_calls[-1]}"

    def test_complete_job_outside_slot(self, monkeypatch):
        """AC-4 / D2: complete_job must be called AFTER the slot is released (not inside)."""
        import mes_dashboard.services.wip_query_job_service as wip_svc
        import mes_dashboard.rq_worker_preload as preload

        self._setup_monkeypatches(monkeypatch, wip_svc, preload)

        call_order: List[str] = []

        @contextmanager
        def _recording_slot(owner: str):
            call_order.append("slot_enter")
            try:
                yield True
            finally:
                call_order.append("slot_exit")

        def _fake_complete(prefix, job_id, **kw):
            call_order.append("complete_job")

        monkeypatch.setattr(wip_svc, "heavy_query_slot", _recording_slot)
        monkeypatch.setattr(wip_svc, "complete_job", _fake_complete)
        monkeypatch.setattr(
            wip_svc, "execute_wip_detail_oracle_query",
            MagicMock(return_value={"query_id": "abc123", "spool_path": None, "row_count": 0}),
        )

        wip_svc.execute_wip_detail_job(
            job_id="order-job-001",
            owner="test-user",
            workcenter="焊接_DB",
        )

        # slot_exit must come before complete_job
        assert "slot_exit" in call_order, "slot_exit event not recorded"
        assert "complete_job" in call_order, "complete_job not called"
        exit_idx = call_order.index("slot_exit")
        complete_idx = call_order.index("complete_job")
        assert exit_idx < complete_idx, (
            f"complete_job must be called AFTER slot_exit. Order: {call_order}"
        )


# ---------------------------------------------------------------------------
# AC-4: No Oracle at enqueue time (route-level guarantee)
# ---------------------------------------------------------------------------

class TestNoOracleAtEnqueueTime:
    def test_enqueue_wip_detail_does_not_call_oracle(self):
        """AC-4: enqueue_wip_detail_query must not issue Oracle queries at request time."""
        import mes_dashboard.services.wip_query_job_service as wip_svc

        oracle_calls = []

        # Patch the oracle reader at the module boundary used by wip_service
        with patch(
            "mes_dashboard.services.wip_service.read_sql_df",
            side_effect=lambda *a, **kw: oracle_calls.append(a) or MagicMock(),
        ), patch(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            return_value=("wip-detail-test-job-id", None),
        ):
            job_id, err = wip_svc.enqueue_wip_detail_query(
                params={"workcenter": "焊接_DB", "owner": "test-user"},
                owner="test-user",
            )

        assert oracle_calls == [], (
            f"Oracle must NOT be queried at enqueue time. Got calls: {oracle_calls}"
        )
        assert job_id is not None or err is not None  # enqueue either succeeded or failed gracefully
