# -*- coding: utf-8 -*-
"""Unit tests: heavy_query_slot wiring inside the unified job core.

Companion to test_rq_semaphore_wiring.py. That suite covers the *legacy*
per-domain workers (query-tool/hold/resource/reject). This suite covers the
*unified* path — BaseChunkedDuckDBJob.run() and material_trace's overridden
run() — where EAP_ALARM/DOWNTIME/MATERIAL_TRACE (USE_UNIFIED_JOB=on by
default) issue their primary Oracle fetch. Before this wiring those jobs
bypassed HEAVY_QUERY_MAX_CONCURRENT entirely.

Covers:
  TestBaseRunSlotWiring      — base run() acquires exactly once around the Oracle
                               fan-out; slot released when the fan-out raises;
                               post_aggregate runs OUTSIDE the slot (Oracle-phase
                               only, D1).
  TestMaterialTraceSlotWiring — AST proof that the overridden run() brackets its
                               Oracle fetch with heavy_query_slot.
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path

import pytest

from mes_dashboard.core.base_chunked_duckdb_job import (
    BaseChunkedDuckDBJob,
    ChunkStrategy,
)


class _FakeAppendJob(BaseChunkedDuckDBJob):
    """Minimal concrete job (multi-parquet append path)."""

    namespace = "test_ns"
    chunk_strategy = ChunkStrategy.SINGLE
    requires_cross_chunk_reduction = False

    def pre_query(self) -> None:
        self._chunks = [{"i": 0}]

    def build_chunk_sql(self, chunk_params):  # pragma: no cover - not reached (fan-out mocked)
        return ("SELECT 1 FROM dual", {})

    def post_aggregate(self, job_duckdb_path):
        return "/tmp/test_ns/spool.parquet"


class _FakeReductionJob(_FakeAppendJob):
    """Minimal concrete job (shared-DuckDB reduction path)."""

    requires_cross_chunk_reduction = True


def _recording_slot(events):
    @contextmanager
    def _slot(owner):
        events.append(("acquire", owner))
        try:
            yield True
        finally:
            events.append(("release", owner))

    return _slot


class TestBaseRunSlotWiring:
    def test_append_path_acquires_slot_once(self, monkeypatch):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events = []
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_slot(events))

        job = _FakeAppendJob("job-append-1")
        post_aggregate_seen_events = []
        monkeypatch.setattr(job, "_fan_out_append", lambda chunks: None)
        monkeypatch.setattr(job, "_cleanup_chunk_parquet_dir", lambda jid: None)
        monkeypatch.setattr(job, "progress_report", lambda pct: None)
        # Record the slot state at the moment post_aggregate runs.
        monkeypatch.setattr(
            job,
            "post_aggregate",
            lambda p: (post_aggregate_seen_events.append(list(events)) or "/tmp/spool.parquet"),
        )

        spool = job.run()

        assert spool == "/tmp/spool.parquet"
        acquires = [e for e in events if e[0] == "acquire"]
        assert len(acquires) == 1, f"expected exactly one acquire, got {events}"
        assert acquires[0][1] == "test_ns:job-append-1"
        # post_aggregate must run AFTER the slot was released (Oracle-phase only, D1).
        assert post_aggregate_seen_events[0][-1] == ("release", "test_ns:job-append-1")

    def test_reduction_path_acquires_slot_once(self, monkeypatch):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events = []
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_slot(events))

        job = _FakeReductionJob("job-reduce-1")
        monkeypatch.setattr(job, "_make_job_duckdb_path", lambda: "/tmp/test_ns/job.duckdb")
        monkeypatch.setattr(job, "_fan_out_reduction", lambda chunks, path: None)
        monkeypatch.setattr(job, "_cleanup_job_duckdb", lambda p: None)
        monkeypatch.setattr(job, "progress_report", lambda pct: None)
        monkeypatch.setattr(job, "post_aggregate", lambda p: "/tmp/spool.parquet")

        job.run()

        acquires = [e for e in events if e[0] == "acquire"]
        assert len(acquires) == 1, f"expected exactly one acquire, got {events}"
        assert acquires[0][1] == "test_ns:job-reduce-1"

    def test_slot_released_when_fanout_raises(self, monkeypatch):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events = []
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_slot(events))

        job = _FakeAppendJob("job-boom-1")

        def _boom(chunks):
            raise RuntimeError("oracle down")

        monkeypatch.setattr(job, "_fan_out_append", _boom)
        monkeypatch.setattr(job, "_cleanup_chunk_parquet_dir", lambda jid: None)
        monkeypatch.setattr(job, "progress_report", lambda pct: None)

        with pytest.raises(RuntimeError, match="oracle down"):
            job.run()

        assert ("acquire", "test_ns:job-boom-1") in events
        assert ("release", "test_ns:job-boom-1") in events, "slot must release on exception"


class TestMaterialTraceSlotWiring:
    """AST proof: material_trace's overridden run() brackets its Oracle fetch.

    material_trace overrides run() so it cannot inherit the base class's slot;
    it must call heavy_query_slot itself. Behavioural construction of the job
    requires heavy Oracle/DuckDB setup, so we prove the wiring statically
    (test-discipline.md AST pattern).
    """

    def test_material_trace_run_references_heavy_query_slot(self):
        src_path = (
            Path(__file__).parent.parent
            / "src/mes_dashboard/services/material_trace_duckdb_runtime.py"
        )
        tree = ast.parse(src_path.read_text(encoding="utf-8"))

        run_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                run_fn = node
                break
        assert run_fn is not None, "run() not found in material_trace_duckdb_runtime.py"

        names = set()
        for node in ast.walk(run_fn):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr)
        assert "heavy_query_slot" in names, (
            "material_trace run() must bracket its Oracle fetch with heavy_query_slot"
        )
