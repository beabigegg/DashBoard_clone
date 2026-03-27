# -*- coding: utf-8 -*-
"""Task 5.7 — Parity tests: MSD DuckDB spool runtime vs legacy aggregation.

These tests verify that the MsdDuckdbRuntime produces results that are
structurally consistent with the legacy Oracle-path data shapes.  They use
synthetic parquet spool files so no Oracle or Redis dependency is required.
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
    # CONTAINER_ID, STATION_NAME, DEFECT_QTY, INPUT_QTY, TXNDATE
    ("LOT001", "TEST-A", 5, 100, "2025-01-10"),
    ("LOT001", "TEST-B", 3, 100, "2025-01-10"),
    ("LOT002", "TEST-A", 2, 50,  "2025-01-11"),
    ("LOT003", "TEST-A", 8, 200, "2025-01-12"),
    ("LOT003", "TEST-C", 1, 200, "2025-01-12"),
]

SAMPLE_LINEAGE = [
    # ANCESTOR_NAME, DESCENDANT_ID
    ("EQPT-01", "LOT001"),
    ("EQPT-01", "LOT002"),
    ("EQPT-02", "LOT003"),
]


def _make_events_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(
        SAMPLE_EVENTS,
        columns=["CONTAINER_ID", "STATION_NAME", "DEFECT_QTY", "INPUT_QTY", "TXNDATE"],
    )
    path = tmp_path / "events.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_lineage_parquet(tmp_path: pathlib.Path) -> pathlib.Path:
    df = pd.DataFrame(SAMPLE_LINEAGE, columns=["ANCESTOR_NAME", "DESCENDANT_ID"])
    path = tmp_path / "lineage.parquet"
    df.to_parquet(path, index=False)
    return path


@pytest.fixture()
def spool_paths(tmp_path):
    """Return (events_path_str, lineage_path_str)."""
    return str(_make_events_parquet(tmp_path)), str(_make_lineage_parquet(tmp_path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_with_paths(trace_query_id, events_path, lineage_path):
    """Create MsdDuckdbRuntime with pre-injected spool paths.

    Sets _resolved=True so _resolve_paths() does not overwrite the injected
    values when summary/detail/export methods are called.
    """
    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    rt = MsdDuckdbRuntime(trace_query_id)
    rt._events_path = events_path
    rt._lineage_path = lineage_path
    rt._resolved = True  # prevent spool-store lookup from overwriting
    return rt


# ---------------------------------------------------------------------------
# KPI parity
# ---------------------------------------------------------------------------

class TestKpiParity:
    def test_kpi_lot_count_matches_distinct_containers(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-kpi-001", events_path, lineage_path)
        summary = rt.get_summary()
        assert summary is not None
        kpi = summary["kpi"]
        # 3 distinct CONTAINER_IDs in SAMPLE_EVENTS
        assert kpi["lot_count"] == 3

    def test_kpi_defect_qty_is_sum(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-kpi-002", events_path, lineage_path)
        summary = rt.get_summary()
        kpi = summary["kpi"]
        expected_defect = sum(r[2] for r in SAMPLE_EVENTS)  # 5+3+2+8+1 = 19
        assert kpi["defect_qty"] == expected_defect

    def test_kpi_defect_rate_matches_manual_calculation(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-kpi-003", events_path, lineage_path)
        summary = rt.get_summary()
        kpi = summary["kpi"]
        total_defect = sum(r[2] for r in SAMPLE_EVENTS)
        total_input = sum(r[3] for r in SAMPLE_EVENTS)
        expected_rate = round(total_defect / total_input * 100, 2)
        assert kpi["defect_rate"] == expected_rate

    def test_kpi_keys_match_legacy_shape(self, spool_paths):
        """Verify the KPI dict has all keys expected by the frontend."""
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-kpi-shape", events_path, lineage_path)
        summary = rt.get_summary()
        kpi = summary["kpi"]
        for required_key in ("lot_count", "defect_qty", "input_qty", "defect_rate"):
            assert required_key in kpi, f"Missing KPI key: {required_key}"


# ---------------------------------------------------------------------------
# Charts parity
# ---------------------------------------------------------------------------

class TestChartsParity:
    def test_charts_by_station_present(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-charts-001", events_path, lineage_path)
        summary = rt.get_summary()
        charts = summary.get("charts", [])
        assert isinstance(charts, list)
        assert len(charts) > 0

    def test_charts_station_names_match_events(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-charts-002", events_path, lineage_path)
        summary = rt.get_summary()
        chart_stations = {c["station"] for c in summary["charts"]}
        expected_stations = {"TEST-A", "TEST-B", "TEST-C"}
        assert chart_stations == expected_stations

    def test_charts_defect_totals_match(self, spool_paths):
        """Sum of chart defect_qty must equal total from KPI."""
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-charts-003", events_path, lineage_path)
        summary = rt.get_summary()
        chart_total = sum(c["defect_qty"] for c in summary["charts"])
        kpi_total = summary["kpi"]["defect_qty"]
        assert chart_total == kpi_total


# ---------------------------------------------------------------------------
# Daily trend parity
# ---------------------------------------------------------------------------

class TestDailyTrendParity:
    def test_trend_dates_sorted(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-trend-001", events_path, lineage_path)
        summary = rt.get_summary()
        dates = [item["date"] for item in summary["daily_trend"]]
        assert dates == sorted(dates)

    def test_trend_covers_all_event_dates(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-trend-002", events_path, lineage_path)
        summary = rt.get_summary()
        trend_dates = {item["date"][:10] for item in summary["daily_trend"]}
        event_dates = {r[4][:10] for r in SAMPLE_EVENTS}
        assert event_dates.issubset(trend_dates)

    def test_trend_defect_sum_matches_kpi(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-trend-003", events_path, lineage_path)
        summary = rt.get_summary()
        trend_total = sum(item["defect_qty"] for item in summary["daily_trend"])
        kpi_total = summary["kpi"]["defect_qty"]
        assert trend_total == kpi_total


# ---------------------------------------------------------------------------
# Detail parity
# get_detail returns: {items, pagination: {page, per_page, total, total_pages}}
# ---------------------------------------------------------------------------

class TestDetailParity:
    def test_detail_returns_pagination_shape(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-detail-001", events_path, lineage_path)
        detail = rt.get_detail(page=1, per_page=10)
        assert detail is not None
        assert "items" in detail
        assert "pagination" in detail
        pagination = detail["pagination"]
        for key in ("page", "per_page", "total", "total_pages"):
            assert key in pagination, f"Missing pagination key: {key}"

    def test_detail_total_matches_events_rows(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-detail-002", events_path, lineage_path)
        detail = rt.get_detail(page=1, per_page=100)
        assert detail["pagination"]["total"] == len(SAMPLE_EVENTS)

    def test_detail_pagination_page_slicing(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-detail-page", events_path, lineage_path)
        page1 = rt.get_detail(page=1, per_page=3)
        page2 = rt.get_detail(page=2, per_page=3)
        assert len(page1["items"]) == 3
        assert len(page2["items"]) == len(SAMPLE_EVENTS) - 3

    def test_detail_row_keys_match_parquet_columns(self, spool_paths):
        """Detail items must include the original parquet column names."""
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-detail-keys", events_path, lineage_path)
        detail = rt.get_detail(page=1, per_page=10)
        assert detail is not None
        if detail["items"]:
            row = detail["items"][0]
            for required_key in ("CONTAINER_ID", "STATION_NAME", "DEFECT_QTY", "INPUT_QTY"):
                assert required_key in row, f"Missing detail row key: {required_key}"


# ---------------------------------------------------------------------------
# Export CSV parity
# ---------------------------------------------------------------------------

class TestExportCsvParity:
    def test_export_yields_bytes(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-export-001", events_path, lineage_path)
        chunks = list(rt.export_csv(chunk_size=2))
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, bytes)

    def test_export_has_header_row(self, spool_paths):
        events_path, lineage_path = spool_paths
        rt = _runtime_with_paths("test-export-002", events_path, lineage_path)
        chunks = list(rt.export_csv(chunk_size=100))
        full_csv = b"".join(chunks).decode("utf-8-sig", errors="replace")
        lines = [l for l in full_csv.splitlines() if l.strip()]
        assert len(lines) > 0
        header = lines[0]
        # Header must include column names from events parquet
        assert "CONTAINER_ID" in header or "STATION_NAME" in header

    def test_export_row_count_matches_events(self, spool_paths):
        events_path, lineage_path = spool_paths
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
        events_path, _ = spool_paths
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
