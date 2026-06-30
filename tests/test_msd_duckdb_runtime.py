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

from unittest.mock import patch


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


class TestBackwardAttributionNoFanout:
    """Regression: backward upstream attribution must NOT inflate defect_qty via the
    lineage×events JOIN fan-out. A defect lot whose ancestor has multiple event rows
    at the same machine/material must count that lot's defect_qty exactly ONCE, so a
    single dimension can never exceed the cohort total (the GWMA-0007=366 > total=252
    bug)."""

    def _conn(self):
        import duckdb
        import pandas as pd
        conn = duckdb.connect()
        # one defect lot D1 (reject 100, input 1000)
        detection = pd.DataFrame([
            {"CONTAINERID": "D1", "REJECTQTY": 100, "TRACKINQTY": 1000, "LOSSREASONNAME": "X"},
        ])
        # D1's ancestor is A1
        lineage = pd.DataFrame([{"ANCESTOR_ID": "A1", "DESCENDANT_ID": "D1"}])
        # A1 passed machine M1 / material P1 in THREE event rows (fan-out trigger)
        events = pd.DataFrame([
            {"CONTAINERID": "A1", "WORKCENTER_GROUP": "WB", "EQUIPMENTNAME": "M1",
             "EQUIPMENTID": "E1", "MATERIALPARTNAME": "P1", "MATERIALLOTNAME": "L1"},
            {"CONTAINERID": "A1", "WORKCENTER_GROUP": "WB", "EQUIPMENTNAME": "M1",
             "EQUIPMENTID": "E1", "MATERIALPARTNAME": "P1", "MATERIALLOTNAME": "L1"},
            {"CONTAINERID": "A1", "WORKCENTER_GROUP": "WB", "EQUIPMENTNAME": "M1",
             "EQUIPMENTID": "E1", "MATERIALPARTNAME": "P1", "MATERIALLOTNAME": "L1"},
        ])
        conn.register("detection", detection)
        conn.register("lineage", lineage)
        conn.register("events", events)
        return conn

    def test_machine_chart_counts_defect_once(self):
        rt = MsdDuckdbRuntime("t-fanout-machine")
        out = rt._compute_machine_chart(self._conn())
        m1 = next(r for r in out if r["name"] == "M1")
        assert m1["defect_qty"] == 100, "defect_qty must be the lot's reject (100), not 3×100"
        assert m1["lot_count"] == 1
        assert m1["input_qty"] == 1000
        # invariant: no single machine exceeds the cohort total defect (100)
        assert max(r["defect_qty"] for r in out) <= 100

    def test_material_chart_counts_defect_once(self):
        rt = MsdDuckdbRuntime("t-fanout-material")
        out = rt._compute_material_chart(self._conn())
        p1 = next(r for r in out if r["name"] == "P1")
        assert p1["defect_qty"] == 100
        assert p1["lot_count"] == 1

    def test_raw_machine_attribution_counts_defect_once(self):
        rt = MsdDuckdbRuntime("t-fanout-rawmachine")
        out = rt._compute_raw_machine_attribution(self._conn())
        m1 = next(r for r in out if r["EQUIPMENT_NAME"] == "M1")
        assert m1["DEFECT_QTY"] == 100
        assert m1["DETECTION_LOT_COUNT"] == 1

    def test_raw_materials_attribution_counts_defect_once(self):
        rt = MsdDuckdbRuntime("t-fanout-rawmat")
        out = rt._compute_raw_materials_attribution(self._conn())
        p1 = next(r for r in out if r["MATERIAL_PART_NAME"] == "P1")
        assert p1["DEFECT_QTY"] == 100
        assert p1["DETECTION_LOT_COUNT"] == 1
