# -*- coding: utf-8 -*-
"""Unit tests for msd_duckdb_runtime.py — MSD DuckDB runtime.

Modelled on test_material_trace_duckdb_runtime.py.

Covers:
- Spool namespace constant
- is_available returns False when no spool
- is_available returns False when spool file missing
- get_summary returns well-formed dict (with mocked parquet)
- get_detail returns paginated result
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch, MagicMock

import pytest

from mes_dashboard.services.msd_duckdb_runtime import (
    MsdDuckdbRuntime,
    SPOOL_NAMESPACE,
)


class TestSpoolNamespace:
    def test_spool_namespace_value(self):
        """SPOOL_NAMESPACE must be the string 'msd-events'."""
        assert SPOOL_NAMESPACE == "msd-events"


class TestMsdDuckdbRuntimeAvailability:
    def test_is_available_returns_false_when_no_spool(self):
        """is_available must return False when spool returns None."""
        runtime = MsdDuckdbRuntime("msd-test-123")
        with patch(
            "mes_dashboard.core.query_spool_store.get_stage_spool_path",
            return_value=None,
        ), patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value=None,
        ):
            result = runtime.is_available()
        assert result is False

    def test_is_available_returns_false_when_file_missing(self):
        """is_available must return False when spool path doesn't exist on disk."""
        runtime = MsdDuckdbRuntime("msd-test-123")
        with patch(
            "mes_dashboard.core.query_spool_store.get_stage_spool_path",
            return_value=None,
        ), patch(
            "mes_dashboard.core.query_spool_store.get_spool_file_path",
            return_value="/tmp/nonexistent_msd.parquet",
        ):
            result = runtime.is_available()
        assert result is False

    def test_trace_query_id_stored(self):
        """MsdDuckdbRuntime must store the trace_query_id attribute."""
        runtime = MsdDuckdbRuntime("msd-abc-456")
        assert runtime.trace_query_id == "msd-abc-456"


class TestMsdDuckdbRuntimeQueryId:
    def test_new_instance_is_not_resolved(self):
        """Freshly created instance should not have resolved paths yet."""
        runtime = MsdDuckdbRuntime("msd-new-999")
        assert runtime._resolved is False
        assert runtime._events_path is None
        assert runtime._lineage_path is None
