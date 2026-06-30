# -*- coding: utf-8 -*-
"""Task 5.7 — Parity tests: MSD DuckDB spool runtime vs legacy aggregation.

These tests verify that the MsdDuckdbRuntime produces results that are
structurally consistent with the legacy Oracle-path data shapes.  They use
synthetic parquet spool files so no Oracle or Redis dependency is required.

The fixture data uses the forward-path events schema
(CONTAINERID, WORKCENTERNAME, REJECT_TOTAL_QTY, TRACKINQTY, TXNDATE, TRACKINTIMESTAMP) which is consumed
by ``get_summary(direction="forward")``, matching the actual upstream_history /
downstream_rejects spool column names.

Backward-path tests (``get_summary_with_detection``) require a detection spool
and are covered separately by :class:`TestBackwardSummary`.
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_EVENTS = [
    # CONTAINERID, WORKCENTER_GROUP, REJECT_TOTAL_QTY, TRACKINQTY, TXNDATE, TRACKINTIMESTAMP
    # All test records are "downstream" type: TXNDATE is set, TRACKINQTY is NULL.
    # Using WORKCENTER_GROUP (not WORKCENTERNAME) so the forward reconstruction finds them.
    ("LOT001", "TEST-A", 5, None, "2025-01-10", None),
    ("LOT001", "TEST-B", 3, None, "2025-01-10", None),
    ("LOT002", "TEST-A", 2, None, "2025-01-11", None),
    ("LOT003", "TEST-A", 8, None, "2025-01-12", None),
    ("LOT003", "TEST-C", 1, None, "2025-01-12", None),
]

# Detection spool for forward-path tests.
# LOT001/LOT002/LOT003 are the defect lots at upstream station (order 4 = 成型).
SAMPLE_FWD_DETECTION = [
    # CONTAINERID, CONTAINERNAME, PJ_TYPE, PRODUCTLINENAME, WORKFLOW,
    # DETECTION_EQUIPMENTNAME, TRACKINQTY, LOSSREASONNAME, REJECTQTY, TRACKINTIMESTAMP
    ("LOT001", "LOT001-NAME", "GA", "PKG-A", "WF-A", "EQ-01", 100, "REASON-A", 5, "2025-01-10"),
    ("LOT001", "LOT001-NAME", "GA", "PKG-A", "WF-A", "EQ-01", 100, "REASON-B", 3, "2025-01-10"),
    ("LOT002", "LOT002-NAME", "GA", "PKG-A", "WF-A", "EQ-02", 50, "REASON-A", 2, "2025-01-11"),
    ("LOT003", "LOT003-NAME", "GA", "PKG-B", "WF-B", "EQ-03", 200, "REASON-A", 8, "2025-01-12"),
    ("LOT003", "LOT003-NAME", "GA", "PKG-B", "WF-B", "EQ-03", 200, "REASON-C", 1, "2025-01-12"),
]

SAMPLE_LINEAGE = [
    # ANCESTOR_NAME, DESCENDANT_ID
    ("EQPT-01", "LOT001"),
    ("EQPT-01", "LOT002"),
    ("EQPT-02", "LOT003"),
]

# Detection spool for backward-path tests (Oracle column names)
SAMPLE_DETECTION = [
    ("LOT001", "LOT001-NAME", 100, 5, "REASON-A", "WKST-01", "EQ-01", "2025-01-10", "WORKFLOW-A", "PKG-A", "PJ-A", "RC-001"),
    ("LOT001", "LOT001-NAME", 100, 3, "REASON-B", "WKST-01", "EQ-01", "2025-01-10", "WORKFLOW-A", "PKG-A", "PJ-A", "RC-001"),
    ("LOT002", "LOT002-NAME", 50,  2, "REASON-A", "WKST-01", "EQ-02", "2025-01-11", "WORKFLOW-A", "PKG-A", "PJ-A", "RC-002"),
    ("LOT003", "LOT003-NAME", 200, 8, "REASON-A", "WKST-02", "EQ-03", "2025-01-12", "WORKFLOW-B", "PKG-B", "PJ-B", "RC-003"),
    ("LOT003", "LOT003-NAME", 200, 1, "REASON-C", "WKST-02", "EQ-03", "2025-01-12", "WORKFLOW-B", "PKG-B", "PJ-B", "RC-003"),
]

SAMPLE_BWD_LINEAGE = [
    # DESCENDANT_ID, ANCESTOR_ID, ANCESTOR_NAME, SEED_ROOT_NAME
    ("LOT001", "ANC001", "ANC-001-NAME", "ROOT-A"),
    ("LOT002", "ANC001", "ANC-001-NAME", "ROOT-A"),
    ("LOT003", "ANC002", "ANC-002-NAME", "ROOT-B"),
]

SAMPLE_BWD_EVENTS = [
    # CONTAINERID, WORKCENTER_GROUP, EQUIPMENTID, EQUIPMENTNAME, SPECNAME,
    # TRACKINTIMESTAMP, TRACKINQTY, CONTAINERNAME, MATERIALPARTNAME,
    # MATERIALLOTNAME, QTYCONSUMED, TXNDATE
    ("ANC001", "WC-GRP1", "EQ001", "EQ-NAME-01", "SPEC-A", "2025-01-09", 100, "ANC-001-NAME", None, None, None, "2025-01-09"),
    ("ANC002", "WC-GRP2", "EQ002", "EQ-NAME-02", "SPEC-B", "2025-01-11", 200, "ANC-002-NAME", None, None, None, "2025-01-11"),
]


def _make_events_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(
        SAMPLE_EVENTS,
        columns=["CONTAINERID", "WORKCENTER_GROUP", "REJECT_TOTAL_QTY", "TRACKINQTY", "TXNDATE", "TRACKINTIMESTAMP"],
    )
    path = tmp_path / "events.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_fwd_detection_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(
        SAMPLE_FWD_DETECTION,
        columns=[
            "CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME", "WORKFLOW",
            "DETECTION_EQUIPMENTNAME", "TRACKINQTY", "LOSSREASONNAME", "REJECTQTY", "TRACKINTIMESTAMP",
        ],
    )
    path = tmp_path / "fwd_detection.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_lineage_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(SAMPLE_LINEAGE, columns=["ANCESTOR_NAME", "DESCENDANT_ID"])
    path = tmp_path / "lineage.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_detection_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(
        SAMPLE_DETECTION,
        columns=[
            "CONTAINERID", "CONTAINERNAME", "TRACKINQTY", "REJECTQTY",
            "LOSSREASONNAME", "WORKCENTERNAME", "DETECTION_EQUIPMENTNAME",
            "TXNDATE", "WORKFLOW", "PRODUCTLINENAME", "PJ_TYPE", "FINISHEDRUNCARD",
        ],
    )
    path = tmp_path / "detection.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_bwd_lineage_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(
        SAMPLE_BWD_LINEAGE,
        columns=["DESCENDANT_ID", "ANCESTOR_ID", "ANCESTOR_NAME", "SEED_ROOT_NAME"],
    )
    path = tmp_path / "bwd_lineage.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_bwd_events_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(
        SAMPLE_BWD_EVENTS,
        columns=[
            "CONTAINERID", "WORKCENTER_GROUP", "EQUIPMENTID", "EQUIPMENTNAME",
            "SPECNAME", "TRACKINTIMESTAMP", "TRACKINQTY", "CONTAINERNAME",
            "MATERIALPARTNAME", "MATERIALLOTNAME", "QTYCONSUMED", "TXNDATE",
        ],
    )
    path = tmp_path / "bwd_events.parquet"
    df.to_parquet(path, index=False)
    return path


@pytest.fixture()
def spool_paths(tmp_path):
    """Return (events_path_str, lineage_path_str, fwd_detection_path_str) for forward-path tests."""
    return (
        str(_make_events_parquet(tmp_path)),
        str(_make_lineage_parquet(tmp_path)),
        str(_make_fwd_detection_parquet(tmp_path)),
    )


@pytest.fixture()
def backward_spool_paths(tmp_path):
    """Return (events_path, lineage_path, detection_path) for backward-path tests."""
    return (
        str(_make_bwd_events_parquet(tmp_path)),
        str(_make_bwd_lineage_parquet(tmp_path)),
        str(_make_detection_parquet(tmp_path)),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_with_paths(trace_query_id, events_path, lineage_path, detection_path=None, forward_lineage_path=None):
    """Create MsdDuckdbRuntime with pre-injected spool paths.

    Sets _resolved=True so _resolve_paths() does not overwrite the injected
    values when summary/detail/export methods are called.
    """
    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    rt = MsdDuckdbRuntime(trace_query_id)
    rt._events_path = events_path
    rt._lineage_path = lineage_path
    rt._detection_path = detection_path
    rt._forward_lineage_path = forward_lineage_path
    rt._resolved = True  # prevent spool-store lookup from overwriting
    return rt


# ---------------------------------------------------------------------------
# KPI parity (forward path)
# ---------------------------------------------------------------------------

class TestKpiParity:
    def test_kpi_lot_count_matches_distinct_containers(self, spool_paths):
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-kpi-001", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        assert summary is not None
        kpi = summary["kpi"]
        # 3 distinct CONTAINER_IDs in SAMPLE_FWD_DETECTION
        assert kpi["detection_lot_count"] == 3

    def test_kpi_defect_qty_is_sum(self, spool_paths):
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-kpi-002", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        kpi = summary["kpi"]
        # Sum of REJECTQTY from SAMPLE_FWD_DETECTION: 5+3+2+8+1 = 19
        expected_defect = sum(r[8] for r in SAMPLE_FWD_DETECTION)
        assert kpi["detection_defect_qty"] == expected_defect

    def test_kpi_downstream_reject_from_events(self, spool_paths):
        """Downstream total reject sums REJECT_TOTAL_QTY from events for defect lots."""
        events_path, lineage_path, det_path = spool_paths
        # station_order_fallback=0 means all WORKCENTER_GROUP stations are downstream
        rt = _runtime_with_paths("test-kpi-003", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward", station_order_fallback=0)
        kpi = summary["kpi"]
        # All 3 lots are defect lots; downstream rejects from SAMPLE_EVENTS = 5+3+2+8+1=19
        assert kpi["downstream_total_reject"] == sum(r[2] for r in SAMPLE_EVENTS)

    def test_kpi_keys_match_forward_shape(self, spool_paths):
        """Verify the forward KPI dict has all keys expected by the frontend."""
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-kpi-shape", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        kpi = summary["kpi"]
        for required_key in (
            "detection_lot_count", "detection_defect_qty", "tracked_lot_count",
            "downstream_stations_reached", "downstream_total_reject", "downstream_reject_rate",
        ):
            assert required_key in kpi, f"Missing forward KPI key: {required_key}"


# ---------------------------------------------------------------------------
# Charts parity (forward path)
# ---------------------------------------------------------------------------

class TestChartsParity:
    def test_charts_is_dict_with_forward_keys(self, spool_paths):
        """Forward charts must be a dict with the four downstream chart keys."""
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-charts-001", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        charts = summary.get("charts")
        assert isinstance(charts, dict), f"charts must be a dict, got {type(charts).__name__}"
        for key in ("by_downstream_station", "by_downstream_loss_reason",
                    "by_downstream_machine", "by_detection_machine"):
            assert key in charts, f"Missing chart key: {key}"

    def test_charts_downstream_station_names_match_events(self, spool_paths):
        """by_downstream_station entries must match WORKCENTER_GROUP values in events."""
        events_path, lineage_path, det_path = spool_paths
        # station_order_fallback=0 → all events rows treated as downstream
        rt = _runtime_with_paths("test-charts-002", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward", station_order_fallback=0)
        station_names = {c["name"] for c in summary["charts"]["by_downstream_station"]}
        expected = {"TEST-A", "TEST-B", "TEST-C"}
        assert station_names == expected

    def test_charts_detection_machine_matches_detection_spool(self, spool_paths):
        """by_detection_machine must reflect the detection equipmentname."""
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-charts-003", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        machine_names = {c["name"] for c in summary["charts"]["by_detection_machine"]}
        # SAMPLE_FWD_DETECTION has EQ-01, EQ-02, EQ-03 as DETECTION_EQUIPMENTNAME
        assert machine_names & {"EQ-01", "EQ-02", "EQ-03"}, (
            f"Expected EQ-01/EQ-02/EQ-03 in by_detection_machine, got {machine_names}"
        )


# ---------------------------------------------------------------------------
# Daily trend parity (forward path)
# ---------------------------------------------------------------------------

class TestDailyTrendParity:
    def test_trend_dates_sorted(self, spool_paths):
        """Daily trend dates must be in ascending order."""
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-trend-001", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        dates = [item["date"] for item in summary["daily_trend"]]
        assert dates == sorted(dates)

    def test_trend_covers_all_detection_dates(self, spool_paths):
        """Trend must cover dates present in the detection spool (TRACKINTIMESTAMP)."""
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-trend-002", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        trend_dates = {item["date"][:10] for item in summary["daily_trend"]}
        # Detection dates from SAMPLE_FWD_DETECTION TRACKINTIMESTAMP column (index 9)
        detection_dates = {r[9][:10] for r in SAMPLE_FWD_DETECTION}
        assert detection_dates.issubset(trend_dates), (
            f"Some detection dates missing from trend: {detection_dates - trend_dates}"
        )

    def test_trend_defect_sum_matches_detection_kpi(self, spool_paths):
        """Sum of daily trend defect_qty must match the detection defect total."""
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-trend-003", events_path, lineage_path, det_path)
        summary = rt.get_summary(direction="forward")
        trend_total = sum(item["defect_qty"] for item in summary["daily_trend"])
        # Total from detection spool REJECTQTY: 5+3+2+8+1=19
        expected = sum(r[8] for r in SAMPLE_FWD_DETECTION)
        assert trend_total == expected


# ---------------------------------------------------------------------------
# Detail parity (forward path — get_detail uses events spool directly)
# ---------------------------------------------------------------------------

class TestDetailParity:
    """Detail is only supported for backward direction (needs detection spool)."""

    def test_detail_returns_empty_for_forward_without_detection(self):
        """Forward detail without a detection spool returns empty (graceful degrade)."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        rt = MsdDuckdbRuntime("test-detail-fwd-no-det")
        rt._detection_path = None
        rt._events_path = None
        rt._resolved = True
        detail = rt.get_detail(page=1, per_page=10, direction="forward")
        assert detail is not None
        assert detail.get("items") == []
        assert detail.get("pagination", {}).get("total") == 0

    def test_detail_returns_pagination_shape(self, backward_spool_paths):
        events_path, lineage_path, detection_path = backward_spool_paths
        rt = _runtime_with_paths("test-detail-001", events_path, lineage_path, detection_path)
        detail = rt.get_detail(page=1, per_page=10, direction="backward")
        assert detail is not None
        assert "items" in detail
        assert "pagination" in detail
        pagination = detail["pagination"]
        for key in ("page", "per_page", "total", "total_pages"):
            assert key in pagination, f"Missing pagination key: {key}"

    def test_detail_pagination_page_slicing(self, backward_spool_paths):
        events_path, lineage_path, detection_path = backward_spool_paths
        rt = _runtime_with_paths("test-detail-page", events_path, lineage_path, detection_path)
        page1 = rt.get_detail(page=1, per_page=3, direction="backward")
        page2 = rt.get_detail(page=2, per_page=3, direction="backward")
        assert page1 is not None
        assert len(page1["items"]) == 3
        assert page2 is not None
        # Detection has 5 rows → 3 lots × (1 or 2 reasons) = 5 detail rows
        assert len(page2["items"]) == 2


# ---------------------------------------------------------------------------
# Export CSV parity (forward path)
# ---------------------------------------------------------------------------

class TestExportCsvParity:
    def test_export_yields_bytes(self, spool_paths):
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-export-001", events_path, lineage_path)
        chunks = list(rt.export_csv(chunk_size=2))
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, bytes)

    def test_export_has_header_row(self, spool_paths):
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-export-002", events_path, lineage_path)
        chunks = list(rt.export_csv(chunk_size=100))
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        lines = [l for l in full_csv.splitlines() if l.strip()]
        assert len(lines) > 0
        header = lines[0]
        # Header must include column names from events parquet
        assert "CONTAINERID" in header or "WORKCENTER_GROUP" in header

    def test_export_row_count_matches_events(self, spool_paths):
        events_path, lineage_path, det_path = spool_paths
        rt = _runtime_with_paths("test-export-003", events_path, lineage_path)
        chunks = list(rt.export_csv(chunk_size=100))
        # First chunk is the header (utf-8-sig), rest is data
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        lines = [l for l in full_csv.splitlines() if l.strip()]
        # 1 header + N data rows
        data_rows = len(lines) - 1
        assert data_rows == len(SAMPLE_EVENTS)


# ---------------------------------------------------------------------------
# is_available parity
# ---------------------------------------------------------------------------

class TestIsAvailableParity:
    def test_is_available_returns_true_when_paths_set(self, spool_paths):
        events_path, *_ = spool_paths
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        rt = MsdDuckdbRuntime("test-avail-001")
        rt._events_path = events_path
        rt._lineage_path = None
        rt._resolved = True  # prevent spool-store lookup
        assert rt.is_available() is True

    def test_is_available_returns_false_when_no_path(self):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        with patch(
            "mes_dashboard.core.query_spool_store.get_stage_spool_path",
            return_value=None,
        ), patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value=None,
        ):
            rt = MsdDuckdbRuntime("test-avail-002")
            # _resolve_paths is called; both helpers return None → _events_path = None
            assert rt.is_available() is False

    def test_summary_returns_none_when_events_missing(self):
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        rt = MsdDuckdbRuntime("test-avail-003")
        rt._events_path = None
        rt._lineage_path = None
        rt._resolved = True
        assert rt.get_summary() is None


# ---------------------------------------------------------------------------
# Backward summary parity (get_summary_with_detection)
# ---------------------------------------------------------------------------

class TestBackwardSummary:
    def test_backward_summary_returns_all_chart_keys(self, backward_spool_paths):
        events_path, lineage_path, detection_path = backward_spool_paths
        rt = _runtime_with_paths("test-bwd-001", events_path, lineage_path, detection_path)
        summary = rt.get_summary(direction="backward")
        assert summary is not None
        charts = summary["charts"]
        for key in ("by_machine", "by_detection_machine", "by_material", "by_wafer_root", "by_loss_reason", "by_workflow"):
            assert key in charts, f"Missing chart key: {key}"

    def test_backward_summary_has_attribution_keys(self, backward_spool_paths):
        events_path, lineage_path, detection_path = backward_spool_paths
        rt = _runtime_with_paths("test-bwd-002", events_path, lineage_path, detection_path)
        summary = rt.get_summary(direction="backward")
        assert summary is not None
        assert "attribution" in summary
        assert "materials_attribution" in summary

    def test_backward_wafer_root_uses_seed_root_name(self, backward_spool_paths):
        events_path, lineage_path, detection_path = backward_spool_paths
        rt = _runtime_with_paths("test-bwd-003", events_path, lineage_path, detection_path)
        summary = rt.get_summary(direction="backward")
        assert summary is not None
        roots = summary["charts"]["by_wafer_root"]
        root_names = {r["name"] for r in roots}
        # Should use SEED_ROOT_NAME (ROOT-A, ROOT-B) not inferred roots
        assert root_names == {"ROOT-A", "ROOT-B"}

    def test_backward_kpi_has_required_keys(self, backward_spool_paths):
        events_path, lineage_path, detection_path = backward_spool_paths
        rt = _runtime_with_paths("test-bwd-004", events_path, lineage_path, detection_path)
        summary = rt.get_summary(direction="backward")
        assert summary is not None
        kpi = summary["kpi"]
        # Backward KPI uses detection-spool field names
        for required_key in ("lot_count", "total_defect_qty", "total_input", "total_defect_rate"):
            assert required_key in kpi, f"Missing KPI key: {required_key}"
