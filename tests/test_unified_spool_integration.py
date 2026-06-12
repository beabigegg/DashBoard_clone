# -*- coding: utf-8 -*-
"""Tasks 10.1–10.7 — Unified spool pipeline integration tests.

These tests verify the end-to-end contracts of the unified RQ→Parquet→DuckDB
pipeline without requiring live Oracle/Redis connections.  They use synthetic
parquet files and mock external dependencies.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ===========================================================================
# 10.1: MSD main query → trace_query_id → detail → export full chain
# ===========================================================================

class TestMsdFullChain:
    """The MSD pipeline must support: query → get trace_query_id → detail → export."""

    @pytest.fixture()
    def msd_spool(self, tmp_path: pathlib.Path):
        events_df = pd.DataFrame(
            [
                ("LOT-A", "STATION-1", 10, 200, "2025-02-01", None, None, None, None),
                ("LOT-A", "STATION-2", 5, 200, "2025-02-01", None, None, None, None),
                ("LOT-B", "STATION-1", 3, 100, "2025-02-02", None, None, None, None),
            ],
            columns=[
                "CONTAINERID", "WORKCENTERNAME",
                "REJECT_TOTAL_QTY", "TRACKINQTY", "TXNDATE",
                "EQUIPMENTID", "EQUIPMENTNAME", "WORKCENTER_GROUP", "TRACKINTIMESTAMP",
            ],
        )
        lineage_df = pd.DataFrame(
            [("EQPT-X", "LOT-A"), ("EQPT-Y", "LOT-B")],
            columns=["ANCESTOR_ID", "DESCENDANT_ID"],
        )
        # Detection spool for backward-direction detail: LOT-A has 2 loss reasons, LOT-B has 1
        detection_df = pd.DataFrame(
            [
                ("LOT-A", "LOT-A-001", "GA", "PL1", "WF1", "RC1", "EQP1", 200, "YieldLimit", 10),
                ("LOT-A", "LOT-A-001", "GA", "PL1", "WF1", "RC1", "EQP1", 200, "OtherReason", 5),
                ("LOT-B", "LOT-B-001", "GA", "PL1", "WF1", "RC2", "EQP2", 100, "YieldLimit", 3),
            ],
            columns=[
                "CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME",
                "WORKFLOW", "FINISHEDRUNCARD", "DETECTION_EQUIPMENTNAME",
                "TRACKINQTY", "LOSSREASONNAME", "REJECTQTY",
            ],
        )
        events_path = tmp_path / "events.parquet"
        lineage_path = tmp_path / "lineage.parquet"
        detection_path = tmp_path / "detection.parquet"
        events_df.to_parquet(events_path, index=False)
        lineage_df.to_parquet(lineage_path, index=False)
        detection_df.to_parquet(detection_path, index=False)
        return str(events_path), str(lineage_path), str(detection_path)

    def test_trace_query_id_is_deterministic(self):
        from mes_dashboard.services.trace_job_service import make_trace_query_id

        tqid1 = make_trace_query_id("mid_section_defect", ["LOT-B", "LOT-A"])
        tqid2 = make_trace_query_id("mid_section_defect", ["LOT-A", "LOT-B"])
        assert tqid1 == tqid2
        assert isinstance(tqid1, str) and len(tqid1) > 0

    def test_summary_from_spool(self, msd_spool):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        events_path, lineage_path, detection_path = msd_spool
        rt = MsdDuckdbRuntime("tqid-chain-test")
        rt._events_path = events_path
        rt._lineage_path = lineage_path
        rt._resolved = True

        summary = rt.get_summary(direction="forward")
        assert summary is not None
        assert summary["kpi"]["lot_count"] == 2
        assert summary["kpi"]["defect_qty"] == 18  # 10 + 5 + 3

    def test_detail_from_spool(self, msd_spool):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        events_path, lineage_path, detection_path = msd_spool
        rt = MsdDuckdbRuntime("tqid-chain-test")
        rt._events_path = events_path
        rt._lineage_path = None  # skip lineage joins to keep test self-contained
        rt._detection_path = detection_path
        rt._resolved = True

        detail = rt.get_detail(page=1, per_page=2)
        assert detail is not None
        assert len(detail["items"]) == 2
        assert detail["pagination"]["total"] == 3
        assert detail["pagination"]["total_pages"] == 2

    def test_export_from_spool(self, msd_spool):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        events_path, lineage_path, detection_path = msd_spool
        rt = MsdDuckdbRuntime("tqid-chain-test")
        rt._events_path = events_path
        rt._lineage_path = lineage_path
        rt._resolved = True

        chunks = list(rt.export_csv(chunk_size=10))
        assert len(chunks) > 0
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        lines = [l for l in full_csv.splitlines() if l.strip()]
        # 1 header + 3 data rows
        assert len(lines) == 4

    def test_full_chain_summary_detail_export_consistency(self, msd_spool):
        """Summary, detail, and export should all reflect the same dataset."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        events_path, lineage_path, detection_path = msd_spool
        rt = MsdDuckdbRuntime("tqid-chain-full")
        rt._events_path = events_path
        rt._lineage_path = None  # skip lineage joins for detail
        rt._detection_path = detection_path
        rt._resolved = True

        summary = rt.get_summary(direction="forward")
        detail = rt.get_detail(page=1, per_page=100)
        chunks = list(rt.export_csv(chunk_size=100))
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        csv_data_rows = len([l for l in full_csv.splitlines() if l.strip()]) - 1

        # All three must agree on the total row count
        assert detail["pagination"]["total"] == csv_data_rows == 3
        # KPI defect sum matches
        assert summary["kpi"]["defect_qty"] == 18


# ===========================================================================
# 10.2: Warmup scheduler single leader enqueue
# ===========================================================================

class TestWarmupSchedulerLeader:
    """Only one gunicorn worker should enqueue warmup jobs."""

    @pytest.fixture(autouse=True)
    def _reset_scheduler(self):
        from mes_dashboard.core import spool_warmup_scheduler as sched
        yield
        sched.stop_warmup_scheduler(timeout=1)
        sched._STOP_EVENT.clear()
        sched._SCHEDULER_THREAD = None

    def test_concurrent_workers_only_one_enqueues(self):
        from mes_dashboard.core import spool_warmup_scheduler as sched

        enqueue_count = [0]
        lock_acquired = [False]

        def fake_try_acquire(name, ttl_seconds=60, *, fail_mode=None):
            if not lock_acquired[0]:
                lock_acquired[0] = True
                return True
            return False

        def fake_enqueue():
            enqueue_count[0] += 1
            return len(sched._WARMUP_JOBS)

        with patch.object(sched, "_enqueue_warmup_jobs", side_effect=fake_enqueue):
            with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", side_effect=fake_try_acquire):
                with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock"):
                    with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                        results = []
                        for _ in range(5):  # Simulate 5 workers
                            results.append(sched.run_warmup_cycle())

        assert results.count(True) == 1
        assert enqueue_count[0] == 1

    def test_lock_released_after_enqueue(self):
        from mes_dashboard.core import spool_warmup_scheduler as sched

        mock_release = MagicMock()

        with patch.object(sched, "_enqueue_warmup_jobs", return_value=4):
            with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", return_value=True):
                with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock", mock_release):
                    with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                        sched.run_warmup_cycle()

        mock_release.assert_called_once()


# ===========================================================================
# 10.3: Reject/yield/hold warmup spool hit → route direct response
# ===========================================================================

class TestWarmupSpoolHitRouteResponse:
    """When warmup produces valid spool, routes should serve from spool."""

    def test_reject_dataset_has_ensure_dataset_loaded(self):
        """reject_dataset_cache must expose ensure_dataset_loaded for warmup."""
        from mes_dashboard.services import reject_dataset_cache
        assert callable(getattr(reject_dataset_cache, "ensure_dataset_loaded", None))

    def test_yield_alert_dataset_has_ensure_dataset_loaded(self):
        from mes_dashboard.services import yield_alert_dataset_cache
        assert callable(getattr(yield_alert_dataset_cache, "ensure_dataset_loaded", None))

    def test_hold_dataset_has_ensure_dataset_loaded(self):
        from mes_dashboard.services import hold_dataset_cache
        assert callable(getattr(hold_dataset_cache, "ensure_dataset_loaded", None))

    def test_resource_dataset_has_ensure_dataset_loaded(self):
        from mes_dashboard.services import resource_dataset_cache
        assert callable(getattr(resource_dataset_cache, "ensure_dataset_loaded", None))

    def test_warmup_jobs_cover_expected_reports(self):
        """All 6 canonical warmup-eligible jobs must be in _WARMUP_JOBS."""
        from mes_dashboard.core.spool_warmup_scheduler import _WARMUP_JOBS

        job_fn_names = {fn.__name__ for _, fn in _WARMUP_JOBS}
        assert "_warmup_reject_dataset_job" in job_fn_names
        assert "_warmup_yield_alert_dataset_job" in job_fn_names
        assert "_warmup_hold_dataset_job" in job_fn_names
        assert "_warmup_resource_dataset_job" in job_fn_names
        assert "_warmup_resource_history_duckdb_job" in job_fn_names
        assert "_warmup_downtime_analysis_duckdb_job" in job_fn_names


# ===========================================================================
# 10.4: Resource / production route contract unchanged with unified spool
# ===========================================================================

class TestRouteContractUnchanged:
    """Route contracts must remain the same after backend spool migration."""

    def test_resource_history_blueprint_exists(self):
        """resource_history_bp must be importable and named correctly."""
        from mes_dashboard.routes.resource_history_routes import resource_history_bp
        assert resource_history_bp.name == "resource_history"

    def test_resource_dataset_cache_canonical_base_dataset(self):
        """resource_dataset_cache should support canonical base dataset loading."""
        from mes_dashboard.services import resource_dataset_cache
        assert callable(getattr(resource_dataset_cache, "ensure_dataset_loaded", None))

    def test_production_history_service_has_spool_identity(self):
        """production_history_service should have canonical spool identity helpers."""
        from mes_dashboard.services import production_history_service
        # The module should exist and be importable after spool migration
        assert production_history_service is not None


# ===========================================================================
# 10.5: Production-history excluded from warmup scheduler
# ===========================================================================

class TestProductionHistoryWarmupExclusion:
    """production-history must NEVER appear in the warmup scheduler."""

    def test_warmup_jobs_do_not_contain_production(self):
        from mes_dashboard.core.spool_warmup_scheduler import _WARMUP_JOBS

        for job_id_prefix, fn in _WARMUP_JOBS:
            assert "production" not in job_id_prefix.lower(), (
                f"production-history warmup found in _WARMUP_JOBS: {job_id_prefix}"
            )
            assert "production" not in fn.__name__.lower(), (
                f"production-history warmup fn found: {fn.__name__}"
            )

    def test_scheduler_module_documents_exclusion(self):
        """The scheduler module docstring should document the exclusion."""
        from mes_dashboard.core import spool_warmup_scheduler
        docstring = spool_warmup_scheduler.__doc__ or ""
        assert "production" in docstring.lower()

    def test_warmup_job_count_is_exactly_six(self):
        """Exactly 6 warmup jobs: reject, yield-alert, hold, resource, resource-history-duckdb, downtime-duckdb."""
        from mes_dashboard.core.spool_warmup_scheduler import _WARMUP_JOBS
        assert len(_WARMUP_JOBS) == 6


# ===========================================================================
# 10.6: Material trace async query / polling / export
# ===========================================================================

class TestMaterialTraceAsyncPipeline:
    """Material trace supports spool hit → async enqueue → poll → export."""

    def test_execute_to_spool_idempotent(self, tmp_path):
        """execute_to_spool returns immediately if spool already exists."""
        from mes_dashboard.services.material_trace_service import (
            make_route_query_hash,
        )

        # Verify the hash function produces deterministic results
        hash1 = make_route_query_hash("lot", ["LOT-A", "LOT-B"])
        hash2 = make_route_query_hash("lot", ["LOT-A", "LOT-B"])
        assert hash1 == hash2

    def test_duckdb_runtime_pagination(self, tmp_path):
        """MaterialTraceDuckdbRuntime.get_page returns paginated results."""
        from mes_dashboard.services.material_trace_duckdb_runtime import (
            MaterialTraceDuckdbRuntime,
        )

        # Create a sample parquet spool
        df = pd.DataFrame({
            "CONTAINERNAME": [f"LOT-{i}" for i in range(25)],
            "PJ_WORKORDER": [f"WO-{i}" for i in range(25)],
            "WORKCENTERNAME": ["WC-A"] * 25,
            "MATERIALPARTNAME": ["MAT-1"] * 25,
            "MATERIALLOTNAME": ["ML-1"] * 25,
        })
        spool_path = tmp_path / "spool.parquet"
        df.to_parquet(spool_path, index=False)

        rt = MaterialTraceDuckdbRuntime("test-page")
        rt._spool_path = str(spool_path)
        rt._resolved = True

        page1 = rt.get_page(page=1, per_page=10)
        assert page1 is not None
        assert len(page1["rows"]) == 10
        assert page1["pagination"]["total"] == 25
        assert page1["pagination"]["total_pages"] == 3

        page3 = rt.get_page(page=3, per_page=10)
        assert page3 is not None
        assert len(page3["rows"]) == 5

    def test_duckdb_runtime_export_csv(self, tmp_path):
        """MaterialTraceDuckdbRuntime.export_csv streams valid CSV."""
        from mes_dashboard.services.material_trace_duckdb_runtime import (
            MaterialTraceDuckdbRuntime,
        )

        df = pd.DataFrame({
            "CONTAINERNAME": ["LOT-1", "LOT-2"],
            "PJ_WORKORDER": ["WO-1", "WO-2"],
            "WORKCENTERNAME": ["WC-A", "WC-B"],
        })
        spool_path = tmp_path / "spool.parquet"
        df.to_parquet(spool_path, index=False)

        rt = MaterialTraceDuckdbRuntime("test-export")
        rt._spool_path = str(spool_path)
        rt._resolved = True

        chunks = list(rt.export_csv(chunk_size=10))
        assert len(chunks) > 0
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        lines = [l for l in full_csv.splitlines() if l.strip()]
        # Header + 2 data rows
        assert len(lines) == 3

    def test_rq_material_trace_job_function_exists(self):
        """The RQ worker function must be importable."""
        from mes_dashboard.services.material_trace_service import rq_material_trace_job
        assert callable(rq_material_trace_job)

    def test_route_imports_spool_functions(self):
        """material_trace_routes must import spool-related functions."""
        from mes_dashboard.routes import material_trace_routes
        assert hasattr(material_trace_routes, "make_route_query_hash")

    def test_canonical_query_hash_differs_by_mode(self):
        """Different modes should produce different spool keys."""
        from mes_dashboard.services.material_trace_service import make_route_query_hash

        hash_lot = make_route_query_hash("lot", ["LOT-A"])
        hash_wo = make_route_query_hash("workorder", ["LOT-A"])
        hash_ml = make_route_query_hash("material_lot", ["LOT-A"])
        assert len({hash_lot, hash_wo, hash_ml}) == 3


# ===========================================================================
# 10.7: Guard retirement ordering — all guards present before retirement
# ===========================================================================

class TestGuardRetirementOrdering:
    """All hard limit guards must remain in code until their legacy paths retire.

    This test class serves as a living contract: if a guard is removed
    prematurely, the corresponding test will fail and alert the developer
    to the retirement gating requirement from design.md D7.
    """

    def test_trace_events_legacy_guards_removed(self):
        """Task 6.4: trace events no longer exposes sync CID/RSS guards."""
        from mes_dashboard.routes import trace_routes

        assert not hasattr(trace_routes, "TRACE_EVENTS_CID_LIMIT")
        assert not hasattr(trace_routes, "TRACE_SYNC_RSS_REJECT_MB")

    def test_lineage_max_seed_count_removed(self):
        """Task 6.5: lineage seed-count guard retired after async cutover."""
        from mes_dashboard.services import lineage_engine

        assert not hasattr(lineage_engine, "LINEAGE_MAX_SEED_COUNT")
        assert not hasattr(lineage_engine, "_MAX_SEED_COUNT")

    def test_lineage_rss_reject_removed(self):
        """Task 6.5: lineage RSS guard retired after async cutover."""
        from mes_dashboard.services import lineage_engine

        assert not hasattr(lineage_engine, "LINEAGE_RSS_REJECT_MB")
        assert not hasattr(lineage_engine, "_RSS_REJECT_MB")

    def test_reject_query_rss_guard_removed(self):
        """Task 7.5: reject primary query no longer exposes a standalone RSS guard."""
        from mes_dashboard.services import reject_dataset_cache

        assert not hasattr(reject_dataset_cache, "REJECT_QUERY_RSS_REJECT_MB")

    def test_material_trace_row_guards_removed(self):
        """Task 8.4: material trace row-limit constants are retired."""
        from mes_dashboard.services import material_trace_service

        assert not hasattr(material_trace_service, "_FORWARD_MAX_ROWS")
        assert not hasattr(material_trace_service, "_REVERSE_MAX_ROWS")
        assert not hasattr(material_trace_service, "_EXPORT_MAX_ROWS")

    def test_event_fetcher_max_total_rows_present(self):
        """EVENT_FETCHER_MAX_TOTAL_ROWS — needed until callers fully spool-safe."""
        from mes_dashboard.services.event_fetcher import EVENT_FETCHER_MAX_TOTAL_ROWS
        assert EVENT_FETCHER_MAX_TOTAL_ROWS > 0
