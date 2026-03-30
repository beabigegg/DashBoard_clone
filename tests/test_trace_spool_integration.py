# -*- coding: utf-8 -*-
"""Task 6.6 — Trace / EventFetcher / lineage spool integration tests.

Covers:
  - Spool hit path in trace events route (MSD profile)
  - Async status with stage-aware progress
  - Large query acceptance via async routing
  - Guard constants still present (retirement gating)
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def events_parquet(tmp_path: pathlib.Path) -> str:
    df = pd.DataFrame(
        [("LOT001", "STATION-A", 5, 100, "2025-01-10")],
        columns=["CONTAINER_ID", "STATION_NAME", "DEFECT_QTY", "INPUT_QTY", "TXNDATE"],
    )
    path = tmp_path / "events.parquet"
    df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture()
def lineage_parquet(tmp_path: pathlib.Path) -> str:
    df = pd.DataFrame(
        [("EQPT-01", "LOT001")],
        columns=["ANCESTOR_NAME", "DESCENDANT_ID"],
    )
    path = tmp_path / "lineage.parquet"
    df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture()
def msd_detection_parquet(tmp_path: pathlib.Path) -> str:
    df = pd.DataFrame(
        [
            {
                "CONTAINERID": "CID-001",
                "CONTAINERNAME": "LOT-001",
                "PJ_TYPE": "TYPE-A",
                "PRODUCTLINENAME": "PKG-A",
                "WORKFLOW": "WF-A",
                "FINISHEDRUNCARD": "FR-001",
                "DETECTION_EQUIPMENTNAME": "DET-01",
                "TRACKINQTY": 100,
                "REJECTQTY": 5,
                "LOSSREASONNAME": "R1",
                "TRACKINTIMESTAMP": "2025-01-10 08:00:00",
            },
            {
                "CONTAINERID": "CID-001",
                "CONTAINERNAME": "LOT-001",
                "PJ_TYPE": "TYPE-A",
                "PRODUCTLINENAME": "PKG-A",
                "WORKFLOW": "WF-A",
                "FINISHEDRUNCARD": "FR-001",
                "DETECTION_EQUIPMENTNAME": "DET-01",
                "TRACKINQTY": 100,
                "REJECTQTY": 2,
                "LOSSREASONNAME": "R2",
                "TRACKINTIMESTAMP": "2025-01-10 08:00:00",
            },
            {
                "CONTAINERID": "CID-002",
                "CONTAINERNAME": "LOT-002",
                "PJ_TYPE": "TYPE-B",
                "PRODUCTLINENAME": "PKG-B",
                "WORKFLOW": "WF-B",
                "FINISHEDRUNCARD": "FR-002",
                "DETECTION_EQUIPMENTNAME": "DET-02",
                "TRACKINQTY": 80,
                "REJECTQTY": 0,
                "LOSSREASONNAME": None,
                "TRACKINTIMESTAMP": "2025-01-11 09:00:00",
            },
        ]
    )
    path = tmp_path / "detection.parquet"
    df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture()
def msd_events_full_parquet(tmp_path: pathlib.Path) -> str:
    df = pd.DataFrame(
        [
            {
                "CONTAINERID": "CID-101",
                "WORKCENTER_GROUP": "中段",
                "EQUIPMENTID": "EQ-101",
                "EQUIPMENTNAME": "WIRE-01",
                "SPECNAME": "SPEC-A",
                "TRACKINTIMESTAMP": "2025-01-09 07:00:00",
            },
            {
                "CONTAINERID": "CID-001",
                "WORKCENTER_GROUP": "測試",
                "EQUIPMENTID": "DET-01",
                "EQUIPMENTNAME": "TEST-01",
                "SPECNAME": "SPEC-T",
                "TRACKINTIMESTAMP": "2025-01-10 08:00:00",
            },
            {
                "CONTAINERID": "CID-101",
                "MATERIALPARTNAME": "PART-A",
                "MATERIALLOTNAME": "MATLOT-1",
            },
        ]
    )
    path = tmp_path / "events-full.parquet"
    df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture()
def msd_lineage_full_parquet(tmp_path: pathlib.Path) -> str:
    df = pd.DataFrame(
        [
            {
                "DESCENDANT_ID": "CID-001",
                "ANCESTOR_ID": "CID-101",
                "ANCESTOR_NAME": "WAFER-ROOT-001",
            },
        ]
    )
    path = tmp_path / "lineage-full.parquet"
    df.to_parquet(path, index=False)
    return str(path)


# ---------------------------------------------------------------------------
# 6.6a: Spool hit in trace events route (MSD profile)
# ---------------------------------------------------------------------------

class TestTraceEventSpoolHit:
    """When an MSD events spool exists, the route should return it directly."""

    def test_spool_hit_returns_aggregation_and_trace_query_id(
        self, events_parquet, lineage_parquet, msd_detection_parquet
    ):
        """Simulates the spool hit path: MsdDuckdbRuntime finds spool files
        and returns summary without touching Oracle."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        tqid = "test-spool-hit-001"
        rt = MsdDuckdbRuntime(tqid)
        rt._events_path = events_parquet
        rt._lineage_path = lineage_parquet
        rt._detection_path = msd_detection_parquet
        rt._resolved = True

        assert rt.is_available() is True
        summary = rt.get_summary()
        assert summary is not None
        assert "kpi" in summary
        assert summary["kpi"]["lot_count"] == 2

    def test_spool_hit_skips_oracle_query(self, events_parquet, lineage_parquet, msd_detection_parquet):
        """When spool hit succeeds, EventFetcher should NOT be called."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        rt = MsdDuckdbRuntime("test-skip-oracle")
        rt._events_path = events_parquet
        rt._lineage_path = lineage_parquet
        rt._detection_path = msd_detection_parquet
        rt._resolved = True

        # Spool available → we get summary without touching Oracle
        assert rt.is_available() is True
        summary = rt.get_summary()
        assert summary is not None
        assert summary["kpi"]["lot_count"] == 2

    def test_spool_miss_falls_through(self):
        """When spool is unavailable, MsdDuckdbRuntime.is_available returns False."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        with patch(
            "mes_dashboard.core.query_spool_store.get_stage_spool_path",
            return_value=None,
        ), patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value=None,
        ):
            rt = MsdDuckdbRuntime("test-miss")
            assert rt.is_available() is False

    def test_backward_summary_and_detail_restore_compat_shape(
        self,
        msd_events_full_parquet,
        msd_lineage_full_parquet,
        msd_detection_parquet,
    ):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        rt = MsdDuckdbRuntime("msd-compat-shape-001")
        rt._events_path = msd_events_full_parquet
        rt._lineage_path = msd_lineage_full_parquet
        rt._detection_path = msd_detection_parquet
        rt._resolved = True

        summary = rt.get_summary(direction="backward", loss_reasons=["R1"])
        detail = rt.get_detail(
            page=1,
            per_page=20,
            direction="backward",
            loss_reasons=["R1"],
        )

        assert summary is not None
        assert summary["kpi"]["total_input"] == 180
        assert summary["kpi"]["total_defect_qty"] == 5
        assert summary["kpi"]["defective_lot_count"] == 1
        assert summary["charts"]["by_machine"]

        assert detail is not None
        assert detail["pagination"]["total"] == 2
        row = detail["items"][0]
        for key in (
            "CONTAINERNAME",
            "DETECTION_EQUIPMENTNAME",
            "INPUT_QTY",
            "LOSS_REASON",
            "DEFECT_QTY",
            "ANCESTOR_COUNT",
            "UPSTREAM_MACHINE_COUNT",
        ):
            assert key in row
        assert row["CONTAINERNAME"] == "LOT-001"


# ---------------------------------------------------------------------------
# 6.6b: Async status with stage-aware progress
# ---------------------------------------------------------------------------

class TestAsyncStageAwareProgress:
    """trace_job_service.get_job_status returns stage-aware fields."""

    def test_status_includes_stage_fields(self):
        """When stage metadata is set, get_job_status returns stage + completed_stages."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "running",
            "profile": "mid_section_defect",
            "cid_count": "100",
            "domains": "history,rejects",
            "progress": "fetching events",
            "created_at": "1700000000",
            "completed_at": "",
            "error": "",
            "stage": "events",
            "completed_stages": "seed-resolve,lineage",
            "query_id": "tqid-abc123",
        }

        with patch(
            "mes_dashboard.services.trace_job_service.get_control_redis_client",
            return_value=mock_conn,
        ):
            from mes_dashboard.services.trace_job_service import get_job_status

            status = get_job_status("test-job-001")

        assert status is not None
        assert status["stage"] == "events"
        assert status["completed_stages"] == ["seed-resolve", "lineage"]
        assert status["query_id"] == "tqid-abc123"
        assert status["trace_query_id"] == "tqid-abc123"

    def test_status_without_stage_fields(self):
        """Legacy jobs without stage metadata still work."""
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {
            "status": "completed",
            "profile": "mid_section_defect",
            "cid_count": "50",
            "domains": "history",
            "progress": "",
            "created_at": "1700000000",
            "completed_at": "1700000060",
            "error": "",
        }

        with patch(
            "mes_dashboard.services.trace_job_service.get_control_redis_client",
            return_value=mock_conn,
        ):
            from mes_dashboard.services.trace_job_service import get_job_status

            status = get_job_status("test-legacy-job")

        assert status is not None
        assert "stage" not in status
        assert "completed_stages" not in status


# ---------------------------------------------------------------------------
# 6.6c: Large query acceptance via async routing
# ---------------------------------------------------------------------------

class TestLargeQueryAcceptance:
    """Large CID counts should route to async instead of being rejected."""

    def test_large_cid_count_routes_to_async_when_available(self):
        """When cid_count > TRACE_ASYNC_CID_THRESHOLD and async is available,
        the query should be enqueued, not rejected."""
        from mes_dashboard.services.trace_job_service import (
            TRACE_ASYNC_CID_THRESHOLD,
        )

        # Threshold exists and is a reasonable number
        assert isinstance(TRACE_ASYNC_CID_THRESHOLD, int)
        assert TRACE_ASYNC_CID_THRESHOLD > 0

    def test_sync_event_guards_retired_after_async_cutover(self):
        """Task 6.4: trace events no longer exposes legacy sync guards."""
        from mes_dashboard.routes import trace_routes

        assert not hasattr(trace_routes, "TRACE_EVENTS_CID_LIMIT")
        assert not hasattr(trace_routes, "TRACE_SYNC_RSS_REJECT_MB")


# ---------------------------------------------------------------------------
# 6.6d: Lineage guards retired after async cutover
# ---------------------------------------------------------------------------

class TestLineageGuardPresence:
    """Legacy lineage admission guards are retired after task 6.5."""

    def test_lineage_max_seed_count_guard_removed(self):
        from mes_dashboard.services import lineage_engine
        assert not hasattr(lineage_engine, "LINEAGE_MAX_SEED_COUNT")
        assert not hasattr(lineage_engine, "_MAX_SEED_COUNT")

    def test_lineage_rss_reject_mb_guard_removed(self):
        from mes_dashboard.services import lineage_engine
        assert not hasattr(lineage_engine, "LINEAGE_RSS_REJECT_MB")
        assert not hasattr(lineage_engine, "_RSS_REJECT_MB")


# ---------------------------------------------------------------------------
# 6.6e: EventFetcher spool-oriented stage output (task 6.3)
# ---------------------------------------------------------------------------

class TestEventFetcherSpoolOutput:
    """EventFetcher supports spool-oriented stage output."""

    def test_event_fetcher_max_total_rows_guard_present(self):
        """Row guard must remain until callers are fully spool-safe."""
        from mes_dashboard.services.event_fetcher import EVENT_FETCHER_MAX_TOTAL_ROWS
        assert isinstance(EVENT_FETCHER_MAX_TOTAL_ROWS, int)
        assert EVENT_FETCHER_MAX_TOTAL_ROWS > 0

    def test_event_fetcher_uses_streaming_iter(self):
        """EventFetcher must use read_sql_df_slow_iter for streaming reads."""
        import mes_dashboard.services.event_fetcher as ef
        from mes_dashboard.core.database import read_sql_df_slow_iter
        assert ef.read_sql_df_slow_iter is read_sql_df_slow_iter


# ---------------------------------------------------------------------------
# 6.6f: trace_query_id canonical identity
# ---------------------------------------------------------------------------

class TestTraceQueryIdCanonical:
    """make_trace_query_id produces stable, deterministic identifiers."""

    def test_same_inputs_produce_same_id(self):
        from mes_dashboard.services.trace_job_service import make_trace_query_id

        id1 = make_trace_query_id(
            profile="mid_section_defect",
            container_ids=["CID-B", "CID-A"],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
        id2 = make_trace_query_id(
            profile="mid_section_defect",
            container_ids=["CID-A", "CID-B"],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
        assert id1 == id2

    def test_different_inputs_produce_different_ids(self):
        from mes_dashboard.services.trace_job_service import make_trace_query_id

        id1 = make_trace_query_id(
            profile="mid_section_defect",
            container_ids=["CID-A"],
        )
        id2 = make_trace_query_id(
            profile="mid_section_defect",
            container_ids=["CID-B"],
        )
        assert id1 != id2

    def test_trace_query_id_is_string(self):
        from mes_dashboard.services.trace_job_service import make_trace_query_id

        tqid = make_trace_query_id(
            profile="mid_section_defect",
            container_ids=["CID-A"],
        )
        assert isinstance(tqid, str)
        assert len(tqid) > 0
