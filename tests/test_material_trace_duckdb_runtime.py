# -*- coding: utf-8 -*-
"""Unit tests for material_trace_duckdb_runtime.py — DuckDB pagination helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch

from mes_dashboard.services.material_trace_duckdb_runtime import (
    MaterialTraceDuckdbRuntime,
    _SPOOL_NAMESPACE,
    _EXPORT_COLS,
    _EXPORT_HEADERS,
)


class TestSpoolNamespace:
    def test_spool_namespace_is_material_trace(self):
        assert _SPOOL_NAMESPACE == "material_trace"


class TestExportConfiguration:
    def test_export_cols_is_list(self):
        assert isinstance(_EXPORT_COLS, list)
        assert len(_EXPORT_COLS) > 0

    def test_export_headers_covers_all_cols(self):
        for col in _EXPORT_COLS:
            assert col in _EXPORT_HEADERS, f"Missing header for column: {col}"

    def test_containername_has_lot_id_header(self):
        assert _EXPORT_HEADERS["CONTAINERNAME"] == "LOT ID"


class TestMaterialTraceDuckdbRuntimeIsAvailable:
    def test_is_available_returns_false_when_no_spool(self):
        runtime = MaterialTraceDuckdbRuntime("abc123")
        with patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value=None,
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_miss"
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_hit"
        ):
            result = runtime.is_available()
        assert result is False

    def test_is_available_returns_false_when_file_missing(self):
        runtime = MaterialTraceDuckdbRuntime("abc123")
        with patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value="/tmp/nonexistent.parquet",
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_miss"
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_hit"
        ):
            result = runtime.is_available()
        assert result is False

    def test_is_available_returns_true_when_file_exists(self):
        runtime = MaterialTraceDuckdbRuntime("abc123")
        with patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value="/tmp/fake.parquet",
        ), patch(
            "pathlib.Path.exists",
            return_value=True,
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_hit"
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_miss"
        ):
            result = runtime.is_available()
        assert result is True

    def test_get_page_returns_none_when_unavailable(self):
        runtime = MaterialTraceDuckdbRuntime("abc123")
        with patch.object(runtime, "is_available", return_value=False):
            result = runtime.get_page(page=1, per_page=50)
        assert result is None

    def test_export_csv_returns_empty_generator_when_unavailable(self):
        runtime = MaterialTraceDuckdbRuntime("abc123")
        with patch.object(runtime, "is_available", return_value=False):
            rows = list(runtime.export_csv())
        assert rows == []

    def test_path_resolution_happens_once(self):
        runtime = MaterialTraceDuckdbRuntime("myhash")
        with patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value=None,
        ) as mock_spool, patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_miss"
        ), patch(
            "mes_dashboard.core.heavy_query_telemetry.record_spool_hit"
        ):
            runtime.is_available()
            runtime.is_available()
        # Path resolution should only call get_spool_file_path once (cached)
        mock_spool.assert_called_once()
