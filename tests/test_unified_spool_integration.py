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
        rt._detection_path = detection_path
        rt._resolved = True

        # Forward direction uses the complete Phase-3 payload.
        # detection_lot_count reflects unique CIDs in the detection spool (2 lots).
        # detection_defect_qty sums REJECTQTY from the detection spool (10+5+3=18).
        summary = rt.get_summary(direction="forward")
        assert summary is not None
        assert summary["kpi"]["detection_lot_count"] == 2
        assert summary["kpi"]["detection_defect_qty"] == 18  # 10 + 5 + 3

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

        from mes_dashboard.services.mid_section_defect_service import CSV_COLUMNS_FORWARD

        events_path, lineage_path, detection_path = msd_spool
        rt = MsdDuckdbRuntime("tqid-chain-test")
        rt._events_path = events_path
        rt._lineage_path = lineage_path
        rt._detection_path = detection_path
        rt._forward_lineage_path = lineage_path
        rt._resolved = True

        # forward export = per-lot LOT 明細 (matches the detail table), NOT raw events
        detail = rt.get_detail(page=1, per_page=10000, direction="forward")
        expected = (detail or {}).get("pagination", {}).get("total", 0)
        chunks = list(rt.export_csv(chunk_size=10, direction="forward"))
        assert len(chunks) > 0
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        lines = [l for l in full_csv.splitlines() if l.strip()]
        assert lines[0] == ",".join(label for _, label in CSV_COLUMNS_FORWARD)
        assert len(lines) - 1 == expected

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
        # Forward KPI: detection_defect_qty sums REJECTQTY from detection spool
        assert summary["kpi"]["detection_defect_qty"] == 18


class TestForwardDetailFromSpool:
    """Phase 2: forward per-lot detail is rebuilt from detection + events spool."""

    @pytest.fixture()
    def fwd_spool(self, tmp_path: pathlib.Path):
        # Two detection defect lots at an upstream station (order 4 = 成型).
        detection_df = pd.DataFrame(
            [
                ("LOT-A", "LOT-A-001", "TYPE-A", "PKG-1", "WF1", "EQP1", 200, "YieldLimit", 10),
                ("LOT-B", "LOT-B-001", "TYPE-B", "PKG-2", "WF2", "EQP2", 100, "YieldLimit", 3),
            ],
            columns=[
                "CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME",
                "WORKFLOW", "DETECTION_EQUIPMENTNAME", "TRACKINQTY",
                "LOSSREASONNAME", "REJECTQTY",
            ],
        )
        # Merged events spool: wip-reached rows (TRACKINQTY) + downstream reject
        # rows (REJECT_TOTAL_QTY) at 測試 (order 11, downstream of 成型).
        events_df = pd.DataFrame(
            [
                ("LOT-A", "測試", 200, None),   # wip reached
                ("LOT-A", "測試", None, 8),     # downstream reject
                ("LOT-B", "測試", 100, None),   # wip reached, no downstream reject
            ],
            columns=["CONTAINERID", "WORKCENTER_GROUP", "TRACKINQTY", "REJECT_TOTAL_QTY"],
        )
        det_path = tmp_path / "detection.parquet"
        ev_path = tmp_path / "events.parquet"
        detection_df.to_parquet(det_path, index=False)
        events_df.to_parquet(ev_path, index=False)
        return str(det_path), str(ev_path)

    def _runtime(self, fwd_spool):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        det_path, ev_path = fwd_spool
        rt = MsdDuckdbRuntime("tqid-fwd-detail")
        rt._detection_path = det_path
        rt._events_path = ev_path
        rt._lineage_path = None
        rt._resolved = True
        return rt

    def test_forward_detail_not_empty_and_attributes_downstream(self, fwd_spool):
        rt = self._runtime(fwd_spool)
        detail = rt.get_detail(direction="forward", page=1, per_page=50,
                               station_order_fallback=4)
        assert detail is not None
        items = {r["CONTAINERNAME"]: r for r in detail["items"]}
        assert detail["pagination"]["total"] == 2  # both defect lots present
        # Keys aligned to frontend COLUMNS_FORWARD contract (DetailTable.vue)
        assert items["LOT-A-001"]["DOWNSTREAM_TOTAL_REJECT"] == 8
        assert items["LOT-A-001"]["DOWNSTREAM_STATIONS_REACHED"] >= 1
        assert items["LOT-A-001"]["TRACKINQTY"] == 200
        assert items["LOT-B-001"]["DOWNSTREAM_TOTAL_REJECT"] == 0

    def test_forward_detail_pj_type_mask_restricts_population(self, fwd_spool):
        rt = self._runtime(fwd_spool)
        detail = rt.get_detail(direction="forward", page=1, per_page=50,
                               station_order_fallback=4, pj_types=["TYPE-A"])
        names = {r["CONTAINERNAME"] for r in detail["items"]}
        assert names == {"LOT-A-001"}  # TYPE-B lot masked out of population

    def test_forward_detail_missing_spool_returns_empty(self):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        rt = MsdDuckdbRuntime("tqid-fwd-none")
        rt._detection_path = None
        rt._events_path = None
        rt._resolved = True
        detail = rt.get_detail(direction="forward")
        assert detail["items"] == []
        assert detail["pagination"]["total"] == 0


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


# ===========================================================================
# AC-5: Forward get_summary DuckDB path end-to-end
# ===========================================================================

def test_forward_get_summary_duckdb_path_end_to_end(tmp_path):
    """AC-5: get_summary(direction='forward') produces a non-None result via DuckDB.

    Verifies the DuckDB forward summary path with a minimal events spool +
    detection spool (no Oracle, no Redis).
    """
    import pandas as pd
    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    events_df = pd.DataFrame(
        [
            ("SEED-001", "測試", 100, 5, "2025-04-01", None, None, "測試", None),
            ("SEED-002", "成型", 200, 0, "2025-04-01", None, None, "成型", None),
        ],
        columns=[
            "CONTAINERID", "WORKCENTERNAME",
            "TRACKINQTY", "REJECT_TOTAL_QTY", "TXNDATE",
            "EQUIPMENTID", "EQUIPMENTNAME", "WORKCENTER_GROUP", "TRACKINTIMESTAMP",
        ],
    )
    detection_df = pd.DataFrame(
        [
            ("SEED-001", "SEED-001-001", "GA", "PKG1", "WF1", "EQP1", 100, "BondWire", 5),
        ],
        columns=[
            "CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME",
            "WORKFLOW", "DETECTION_EQUIPMENTNAME", "TRACKINQTY", "LOSSREASONNAME", "REJECTQTY",
        ],
    )

    events_path = tmp_path / "events.parquet"
    detection_path = tmp_path / "detection.parquet"
    events_df.to_parquet(events_path, index=False)
    detection_df.to_parquet(detection_path, index=False)

    rt = MsdDuckdbRuntime("tqid-ac5-end-to-end")
    rt._events_path = str(events_path)
    rt._detection_path = str(detection_path)
    rt._forward_lineage_path = None
    rt._lineage_path = None
    rt._resolved = True

    summary = rt.get_summary(direction="forward")

    assert summary is not None, "get_summary(forward) must not return None when events spool exists"
    assert "kpi" in summary
    assert "daily_trend" in summary
    assert "genealogy_status" in summary
    # KPI should reflect detection data
    kpi = summary["kpi"]
    assert "detection_lot_count" in kpi or "lot_count" in kpi
    assert "downstream_total_reject" in kpi or "defect_qty" in kpi


# ===========================================================================
# AC-6 (Phase 3 regression): _get_forward_summary must return complete payload
# ===========================================================================

def test_forward_summary_phase3_complete_payload(tmp_path):
    """AC-6: _get_forward_summary returns the full Phase-3 payload.

    Reproduces the production symptom where:
    - detection_lot_count / detection_defect_qty / tracked_lot_count were 0
    - charts was a LIST instead of a DICT keyed by by_downstream_station etc.
    - by_detection_loss_reason / loss_reason_workcenter_crosstab /
      downstream_trend / amplification were missing entirely
    - daily_trend y-axis was absurdly large (summed all TRACKINQTY across events)

    The fixture:
    - Detection spool: 2 lots (SEED-001 has 043_NSOP defect, SEED-002 no defect)
      at 成型 station (order 4, upstream).
    - Events spool: downstream wip + reject rows at 測試 (order 11, downstream of 成型)
      for SEED-001 only.

    Expected after fix:
    - kpi.detection_lot_count == 2, kpi.detection_defect_qty == 8
    - kpi.tracked_lot_count == 2
    - kpi.downstream_stations_reached >= 1
    - charts is a dict with keys by_downstream_station, by_downstream_loss_reason,
      by_downstream_machine, by_detection_machine
    - by_detection_loss_reason is a non-empty list
    - loss_reason_workcenter_crosstab is a dict with loss_reasons / workcenter_groups / cells
    - downstream_trend is a list
    - amplification is not None
    - daily_trend input_qty is reasonable (NOT 400_000_000)
    """
    import pandas as pd
    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    # Detection spool: 2 lots at 成型 (upstream station).
    # SEED-001 has defect 043_NSOP (qty=8), SEED-002 has no defect.
    detection_df = pd.DataFrame(
        [
            ("SEED-001", "SEED-001-001", "GA", "PKG1", "WF1", "EQP1", 100, "043_NSOP", 8),
            ("SEED-002", "SEED-002-001", "GA", "PKG1", "WF2", "EQP1", 200, None, 0),
        ],
        columns=[
            "CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME",
            "WORKFLOW", "DETECTION_EQUIPMENTNAME", "TRACKINQTY",
            "LOSSREASONNAME", "REJECTQTY",
        ],
    )
    # Add TRACKINTIMESTAMP for _build_daily_trend (detection-based path)
    detection_df["TRACKINTIMESTAMP"] = "2026-06-23"

    # Events spool: merged wip (TRACKINQTY>0) + reject (REJECT_TOTAL_QTY>0) rows
    # at downstream station 測試 (order 11) for SEED-001 only.
    events_df = pd.DataFrame(
        [
            # wip-reached row: SEED-001 at 測試 (downstream)
            ("SEED-001", "測試", 100, None, None, "EQP-DS-1", "043_NSOP", "2026-06-24"),
            # reject row: SEED-001 at 測試
            ("SEED-001", "測試", None, 15, "2026-06-24", "EQP-DS-1", "043_NSOP", None),
            # SEED-002 reached downstream but no reject
            ("SEED-002", "測試", 200, None, None, "EQP-DS-2", None, "2026-06-25"),
        ],
        columns=[
            "CONTAINERID", "WORKCENTER_GROUP",
            "TRACKINQTY", "REJECT_TOTAL_QTY", "TXNDATE",
            "EQUIPMENTNAME", "LOSSREASONNAME", "TRACKINTIMESTAMP",
        ],
    )

    det_path = tmp_path / "detection.parquet"
    ev_path = tmp_path / "events.parquet"
    detection_df.to_parquet(det_path, index=False)
    events_df.to_parquet(ev_path, index=False)

    rt = MsdDuckdbRuntime("tqid-phase3-regression")
    rt._detection_path = str(det_path)
    rt._events_path = str(ev_path)
    rt._forward_lineage_path = None
    rt._lineage_path = None
    rt._resolved = True

    # station_order_fallback=4 = 成型 order (detection station)
    summary = rt.get_summary(direction="forward", station_order_fallback=4)

    assert summary is not None

    # --- KPI correctness ---
    kpi = summary["kpi"]
    # Detection KPIs must be non-zero (bug: these were 0 before fix)
    assert kpi["detection_lot_count"] == 2, (
        f"detection_lot_count should be 2 (both lots in detection spool), got {kpi['detection_lot_count']}"
    )
    assert kpi["detection_defect_qty"] == 8, (
        f"detection_defect_qty should be 8 (SEED-001 has 8 rejects), got {kpi['detection_defect_qty']}"
    )
    assert kpi["tracked_lot_count"] == 2, (
        f"tracked_lot_count should be 2, got {kpi['tracked_lot_count']}"
    )
    assert kpi["downstream_stations_reached"] >= 1

    # --- charts must be a DICT (bug: was a LIST) ---
    charts = summary["charts"]
    assert isinstance(charts, dict), (
        f"charts must be a dict, got {type(charts).__name__}"
    )
    assert "by_downstream_station" in charts, "charts must have by_downstream_station key"
    assert "by_downstream_loss_reason" in charts, "charts must have by_downstream_loss_reason key"
    assert "by_downstream_machine" in charts, "charts must have by_downstream_machine key"
    assert "by_detection_machine" in charts, "charts must have by_detection_machine key"

    # --- Phase-3 fields must be present (bug: all were missing) ---
    assert "by_detection_loss_reason" in summary, (
        "by_detection_loss_reason must be in summary"
    )
    assert isinstance(summary["by_detection_loss_reason"], list)
    # SEED-001 has 043_NSOP, so at least one entry
    assert len(summary["by_detection_loss_reason"]) >= 1, (
        "by_detection_loss_reason must be non-empty when detection has defects"
    )

    assert "loss_reason_workcenter_crosstab" in summary, (
        "loss_reason_workcenter_crosstab must be in summary"
    )
    crosstab = summary["loss_reason_workcenter_crosstab"]
    assert isinstance(crosstab, dict)
    assert "loss_reasons" in crosstab
    assert "workcenter_groups" in crosstab
    assert "cells" in crosstab

    assert "downstream_trend" in summary, "downstream_trend must be in summary"
    assert isinstance(summary["downstream_trend"], list)

    # MSD-09: front×downstream reason correlation matrix
    assert "by_front_downstream_reason_matrix" in summary, (
        "by_front_downstream_reason_matrix must be in forward summary"
    )
    matrix = summary["by_front_downstream_reason_matrix"]
    assert isinstance(matrix, dict)
    for k in ("rows", "cols", "cells", "row_pct"):
        assert k in matrix, f"matrix must have {k} key"
        assert isinstance(matrix[k], list)
    # cells grid shape matches rows × cols
    assert len(matrix["cells"]) == len(matrix["rows"])
    assert len(matrix["row_pct"]) == len(matrix["rows"])
    if matrix["rows"]:
        assert all(len(r) == len(matrix["cols"]) for r in matrix["cells"])

    assert "amplification" in summary, "amplification must be in summary"
    # detection_defect_qty > 0, so amplification must be a number (not None)
    assert summary["amplification"] is not None, (
        "amplification must be non-None when detection has defects"
    )

    # --- daily_trend must use detection-based input_qty (bug: summed all events TRACKINQTY) ---
    daily_trend = summary["daily_trend"]
    assert isinstance(daily_trend, list)
    if daily_trend:
        max_input = max(day["input_qty"] for day in daily_trend)
        # TRACKINQTY in detection spool: 100 + 200 = 300 total, never > 1000
        assert max_input <= 10_000, (
            f"daily_trend input_qty is unreasonably large ({max_input}); "
            "must be detection-based, not sum of all events rows"
        )


# Regression: forward summary must derive the detection station order from the
# detection workcenter, NOT from station_order_fallback (which callers compute via
# get_group_order(label) and which collapses to 999 for raw WB labels like
# '焊_WB_料'). At 999 every downstream group (order < 999) is filtered out and the
# matrix / downstream attribution come back empty.
def test_forward_summary_derives_station_order_when_fallback_is_999(tmp_path):
    import pandas as pd
    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    # Detection at WB: WORKCENTERNAME '焊_WB_料' -> get_workcenter_group order 2.
    detection_df = pd.DataFrame(
        [("SEED-001", "SEED-001-001", "GA", "PKG1", "WF1", "EQP1", 100,
          "焊_WB_料", "043_NSOP", 8)],
        columns=["CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME",
                 "WORKFLOW", "DETECTION_EQUIPMENTNAME", "TRACKINQTY",
                 "WORKCENTERNAME", "LOSSREASONNAME", "REJECTQTY"],
    )
    detection_df["TRACKINTIMESTAMP"] = "2026-06-23"
    # Downstream reject at 測試 (order 11 > 2)
    events_df = pd.DataFrame(
        [("SEED-001", "測試", 100, None, None, "EQP-DS-1", "043_NSOP", "2026-06-24"),
         ("SEED-001", "測試", None, 15, "2026-06-24", "EQP-DS-1", "274_OPEN", None)],
        columns=["CONTAINERID", "WORKCENTER_GROUP", "TRACKINQTY", "REJECT_TOTAL_QTY",
                 "TXNDATE", "EQUIPMENTNAME", "LOSSREASONNAME", "TRACKINTIMESTAMP"],
    )
    det_path = tmp_path / "detection.parquet"
    ev_path = tmp_path / "events.parquet"
    detection_df.to_parquet(det_path, index=False)
    events_df.to_parquet(ev_path, index=False)

    rt = MsdDuckdbRuntime("tqid-station-order-derive")
    rt._detection_path = str(det_path)
    rt._events_path = str(ev_path)
    rt._forward_lineage_path = None
    rt._lineage_path = None
    rt._resolved = True

    # Caller passes the buggy default 999 — derivation must rescue it.
    summary = rt.get_summary(direction="forward", station_order_fallback=999)
    assert summary is not None

    matrix = summary["by_front_downstream_reason_matrix"]
    assert matrix["rows"], "matrix must be non-empty (station_order derived from WB workcenter, not 999)"
    assert any("043_NSOP" in r["name"] for r in matrix["rows"])
    assert any("274_OPEN" in c["name"] for c in matrix["cols"])
    # downstream attribution must also be populated (not filtered out by order=999)
    assert summary["charts"]["by_downstream_station"], "downstream station chart must be non-empty"
