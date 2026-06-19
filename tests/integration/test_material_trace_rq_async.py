# -*- coding: utf-8 -*-
"""Resilience and integration tests for material-trace unified RQ async pipeline.

Covers:
  R-1  Oracle fault injection mid-stream inside MaterialTraceJob.run() —
       job exits with FAILED status (complete_job called with error=),
       no orphan chunk parquets remain on disk after cleanup.

  R-2  Redis unavailable (flag=on, is_async_available()=False) — route
       returns 503 without any partial enqueue or side effect.  AC-3.

  R-3  Large ID-list (2500 IDs) decomposes into 3 batches of 1000/1000/500
       with no duplicates in the merged DuckDB result.  AC-8 at integration
       level with real DuckDB operations and mocked Oracle.

Marked ``pytest.mark.integration`` — requires --run-integration; no live Oracle
or Redis.  Oracle is mocked at the reader/service boundary; DuckDB operations
run against real temp files to prove spool integrity.

NOT marked integration_real: no GunicornHarness subprocess needed.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


# ---------------------------------------------------------------------------
# Arrow batch factory helpers
# ---------------------------------------------------------------------------

_SPOOL_SCHEMA = pa.schema([
    pa.field("CONTAINERID", pa.string()),
    pa.field("CONTAINERNAME", pa.string()),
    pa.field("PJ_WORKORDER", pa.string()),
    pa.field("WORKCENTERNAME", pa.string()),
    pa.field("MATERIALPARTNAME", pa.string()),
    pa.field("MATERIALLOTNAME", pa.string()),
    pa.field("VENDORLOTNUMBER", pa.string()),
    pa.field("QTYREQUIRED", pa.float64()),
    pa.field("QTYCONSUMED", pa.float64()),
    pa.field("EQUIPMENTNAME", pa.string()),
    pa.field("TXNDATE", pa.string()),
    pa.field("PRIMARY_CATEGORY", pa.string()),
    pa.field("SECONDARY_CATEGORY", pa.string()),
])


def _make_arrow_batch(
    container_ids: List[str],
    material_lot: str = "MLOT-001",
    workcenter: str = "WC-A",
) -> pa.RecordBatch:
    """Build a synthetic Arrow RecordBatch with the spool schema."""
    n = len(container_ids)
    return pa.RecordBatch.from_pydict({
        "CONTAINERID": container_ids,
        "CONTAINERNAME": [f"LOT-{c}" for c in container_ids],
        "PJ_WORKORDER": ["WO-001"] * n,
        "WORKCENTERNAME": [workcenter] * n,
        "MATERIALPARTNAME": ["PART-001"] * n,
        "MATERIALLOTNAME": [material_lot] * n,
        "VENDORLOTNUMBER": ["VND-001"] * n,
        "QTYREQUIRED": [10.0] * n,
        "QTYCONSUMED": [9.5] * n,
        "EQUIPMENTNAME": ["EQ-001"] * n,
        "TXNDATE": ["2026-01-01"] * n,
        "PRIMARY_CATEGORY": ["A"] * n,
        "SECONDARY_CATEGORY": ["B"] * n,
    })


# ===========================================================================
# R-1: Oracle fault injection mid-stream
# ===========================================================================

class TestOracleFaultMidStream:
    """R-1: Oracle connection error mid-stream.

    Verifies:
    - execute_material_trace_unified_job catches the error from job.run()
      and calls complete_job with an error= kwarg (FAILED status).
    - The chunk parquet directory is cleaned up by the finally block in run().
    - No orphan .parquet files remain in the chunk dir after fault.
    """

    def test_oracle_fault_job_status_failed(self, tmp_path, monkeypatch):
        """Oracle error mid-stream: complete_job called with error= (job FAILED)."""
        error_calls: List[Dict[str, Any]] = []

        # Mock progress/complete calls
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda prefix, job_id, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.complete_job",
            lambda prefix, job_id, **kw: error_calls.append({"prefix": prefix, "job_id": job_id, **kw}),
        )

        # Redirect chunk dir to tmp_path so we can inspect leftover files
        chunk_dir_root = tmp_path / "chunks"
        chunk_dir_root.mkdir()
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(chunk_dir_root))

        # Redirect spool dir so post_aggregate writes in tmp_path
        spool_dir = tmp_path / "spool" / "material_trace"
        spool_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path / "spool",
        )

        # pre_query helpers — bypass Oracle container-ID resolution
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_container_ids",
            lambda values: (["C-001", "C-002", "C-003"], {}, []),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_workcenter_names",
            lambda groups: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.filter_cache.get_workcenter_mapping",
            lambda: {},
        )

        # Oracle reader: raises after first batch (mid-stream fault injection)
        call_count = [0]

        def _faulty_chunk_iter(self, sql, params, chunk_size=5000):
            """Yield one good batch then raise an ORA-style exception."""
            call_count[0] += 1
            if call_count[0] == 1:
                yield _make_arrow_batch(["C-001"])
            raise Exception("ORA-03113: end-of-file on communication channel")

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _faulty_chunk_iter,
        )

        # register_spool_file — should never be called on fault
        spool_register_calls = [0]
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            lambda *a, **kw: (spool_register_calls.__setitem__(0, spool_register_calls[0] + 1) or True),
        )

        from mes_dashboard.services.material_trace_service import execute_material_trace_unified_job

        job_id = f"test-fault-{uuid.uuid4().hex[:8]}"
        # execute_material_trace_unified_job catches all exceptions internally
        execute_material_trace_unified_job(
            job_id=job_id,
            mode="lot",
            values=["LOT-001"],
            workcenter_groups=None,
        )

        # complete_job must have been called with error= kwarg (FAILED status)
        assert len(error_calls) >= 1, (
            "complete_job must be called at least once when Oracle faults mid-stream"
        )
        failed_calls = [c for c in error_calls if c.get("error")]
        assert failed_calls, (
            f"complete_job must be called with error= on Oracle fault. Got: {error_calls}"
        )
        # The job_id must match so the caller can poll status
        assert failed_calls[0]["job_id"] == job_id, (
            f"complete_job error call must use the original job_id. Got: {failed_calls[0]}"
        )

    def test_oracle_fault_no_orphan_chunk_parquets(self, tmp_path, monkeypatch):
        """Oracle fault: chunk parquet directory cleaned up by run() finally block.

        After a mid-stream Oracle error, the chunk dir must not exist or must be
        empty — no orphan partial parquet files should remain.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        chunk_dir_root = tmp_path / "chunks"
        chunk_dir_root.mkdir()
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(chunk_dir_root))

        spool_dir = tmp_path / "spool" / "material_trace"
        spool_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path / "spool",
        )

        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_container_ids",
            lambda values: (["C-001", "C-002"], {}, []),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_workcenter_names",
            lambda groups: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.filter_cache.get_workcenter_mapping",
            lambda: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            lambda *a, **kw: True,
        )

        # Fault after writing one chunk parquet
        wrote_chunk = [False]

        def _faulty_chunk_iter(self, sql, params, chunk_size=5000):
            wrote_chunk[0] = True
            yield _make_arrow_batch(["C-001"])
            # Second chunk raises mid-stream
            raise Exception("ORA-12541: TNS:no listener")

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _faulty_chunk_iter,
        )

        from mes_dashboard.services.material_trace_service import execute_material_trace_unified_job

        job_id = f"test-cleanup-{uuid.uuid4().hex[:8]}"
        execute_material_trace_unified_job(
            job_id=job_id,
            mode="lot",
            values=["LOT-001"],
            workcenter_groups=None,
        )

        # The chunk dir for this job must be gone (cleaned by run() finally)
        job_chunk_dir = chunk_dir_root / "material_trace" / job_id
        assert not job_chunk_dir.exists(), (
            f"Chunk dir must be cleaned up after Oracle fault. "
            f"Found leftover at: {job_chunk_dir}"
        )

        # Also verify no orphan .parquet files in the chunk root for this job
        leftover = list(chunk_dir_root.rglob(f"*{job_id}*/*.parquet"))
        assert not leftover, (
            f"No orphan chunk parquets should remain. Found: {leftover}"
        )

    def test_oracle_fault_no_spool_registration(self, tmp_path, monkeypatch):
        """Oracle fault: register_spool_file must NOT be called on mid-stream error.

        A partial or corrupt spool must not be registered; the spool store must
        remain clean so the next query attempt starts fresh.
        """
        spool_register_calls: List[Any] = []

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.complete_job",
            lambda *a, **kw: None,
        )

        chunk_dir_root = tmp_path / "chunks"
        chunk_dir_root.mkdir()
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(chunk_dir_root))

        spool_dir = tmp_path / "spool" / "material_trace"
        spool_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path / "spool",
        )

        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_container_ids",
            lambda values: (["C-001"], {}, []),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_workcenter_names",
            lambda groups: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.filter_cache.get_workcenter_mapping",
            lambda: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            lambda ns, qid, path, row_count, **kw: spool_register_calls.append(
                {"ns": ns, "qid": qid}
            ) or True,
        )

        def _faulty_chunk_iter(self, sql, params, chunk_size=5000):
            raise Exception("ORA-01017: invalid username/password")

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _faulty_chunk_iter,
        )

        from mes_dashboard.services.material_trace_service import execute_material_trace_unified_job

        execute_material_trace_unified_job(
            job_id=f"test-nospool-{uuid.uuid4().hex[:8]}",
            mode="lot",
            values=["LOT-001"],
            workcenter_groups=None,
        )

        assert not spool_register_calls, (
            f"register_spool_file must NOT be called on Oracle fault. "
            f"Got: {spool_register_calls}"
        )


# ===========================================================================
# R-2: Redis unavailable + flag=on → 503, no side effect
# ===========================================================================

class TestRedisUnavailableReturns503:
    """R-2: AC-3 — flag=on + is_async_available()=False → HTTP 503.

    The route must:
    - Return 503 with success=False and Retry-After header.
    - Not call enqueue_query_job (no partial enqueue side effect).
    - Never fall back to the legacy synchronous path (D4: no sync fallback).
    """

    def test_redis_unavailable_returns_503(self, monkeypatch):
        """flag=on + is_async_available=False → 503 SERVICE_UNAVAILABLE."""
        enqueue_calls: List[Any] = []

        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB",
            True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_duckdb_runtime.MaterialTraceDuckdbRuntime.is_available",
            lambda self: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )
        # is_async_available returns False (Redis down)
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: False,
        )
        # Track any enqueue calls (must be zero)
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: enqueue_calls.append((a, kw)) or (None, "blocked", 503),
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/material-trace/query",
                json={"mode": "lot", "values": ["LOT-REDIS-DOWN-001"]},
                content_type="application/json",
            )

        assert resp.status_code == 503, (
            f"flag=on + Redis down must return 503, got {resp.status_code}: {resp.get_json()}"
        )
        data = resp.get_json()
        assert data["success"] is False, "503 response must have success=False"
        # Retry-After header must be present (D4 contract)
        assert resp.headers.get("Retry-After"), (
            "503 from flag=on path must include Retry-After header"
        )
        # enqueue_query_job must NOT be called on is_async_available=False
        assert not enqueue_calls, (
            f"enqueue_query_job must NOT be called when is_async_available()=False. "
            f"Got calls: {enqueue_calls}"
        )

    def test_redis_unavailable_no_legacy_fallback(self, monkeypatch):
        """flag=on + Redis down: legacy enqueue_job must NOT be called (no sync fallback).

        D4: always-async path with no fallback.  If the route silently fell back
        to the legacy path, the caller would get a 202 for a job that runs on the
        legacy (memory-bounded) path — violating D4 and AC-3.
        """
        legacy_enqueue_calls: List[Any] = []

        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB",
            True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_duckdb_runtime.MaterialTraceDuckdbRuntime.is_available",
            lambda self: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: False,
        )
        # Track legacy enqueue_job (top-level import in material_trace_routes)
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.enqueue_job",
            lambda **kw: legacy_enqueue_calls.append(kw) or ("job-legacy-001", None),
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/material-trace/query",
                json={"mode": "workorder", "values": ["WO-001"]},
                content_type="application/json",
            )

        assert resp.status_code == 503
        assert not legacy_enqueue_calls, (
            f"Legacy enqueue_job must NOT be called when flag=on and Redis is down. "
            f"D4: no sync fallback. Got calls: {legacy_enqueue_calls}"
        )

    def test_flag_on_async_available_enqueues_returns_202(self, monkeypatch):
        """flag=on + is_async_available=True: route returns 202 with job_id.

        Positive control: verify the unified path works correctly when Redis is up,
        so R-2 negative assertions aren't vacuously true due to a broken route.
        """
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB",
            True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_duckdb_runtime.MaterialTraceDuckdbRuntime.is_available",
            lambda self: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda job_type, owner, params, *, sync_fallback_allowed=True, job_id=None: (
                job_id or "mt-unified-001",
                None,
                None,
            ),
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/material-trace/query",
                json={"mode": "lot", "values": ["LOT-ASYNC-OK-001"]},
                content_type="application/json",
            )

        assert resp.status_code == 202, (
            f"flag=on + async available must return 202, got {resp.status_code}: {resp.get_json()}"
        )
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]
        assert "query_hash" in data["data"]


# ===========================================================================
# R-3: Large ID-list decomposes into correct batches, no duplicates
# ===========================================================================

class TestLargeIDListDecomposition:
    """R-3: 2500 IDs decompose into 3 batches; DuckDB merge has no duplicates.

    AC-8 at integration level: uses real DuckDB operations with mocked Oracle.
    Each Oracle IN-list batch returns synthetic rows; post_aggregate merges them
    via SELECT DISTINCT and writes to a spool parquet.  Verifies:
    - Exactly 3 chunk SQL calls (ceil(2500/1000) = 3).
    - Result rowcount equals the DISTINCT row count (no duplicates introduced
      by the chunk merge).
    - Spool parquet is registered and readable.
    """

    def test_2500_ids_decompose_into_3_batches(self, tmp_path, monkeypatch):
        """MaterialTraceJob.pre_query decomposes 2500 container IDs into 3 chunks."""
        # Bypass Oracle container resolution: return 2500 IDs directly
        container_ids = [f"C-{i:05d}" for i in range(2500)]
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_container_ids",
            lambda values: (container_ids, {}, []),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_workcenter_names",
            lambda groups: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.filter_cache.get_workcenter_mapping",
            lambda: {},
        )

        from mes_dashboard.services.material_trace_duckdb_runtime import MaterialTraceJob

        job = MaterialTraceJob(
            job_id="test-decomp-2500",
            params={"mode": "lot", "values": ["LOT-BIG"], "workcenter_groups": None},
        )
        job.pre_query()

        assert len(job._chunks) == 3, (
            f"2500 IDs must decompose into 3 chunks (1000/1000/500). "
            f"Got {len(job._chunks)} chunks"
        )
        # Verify batch sizes: 1000, 1000, 500
        batch_sizes = [len(chunk["batch"]) for chunk in job._chunks]
        assert batch_sizes == [1000, 1000, 500], (
            f"Expected batch sizes [1000, 1000, 500], got {batch_sizes}"
        )
        # Verify no duplicates across batches
        all_ids = [cid for chunk in job._chunks for cid in chunk["batch"]]
        assert len(all_ids) == len(set(all_ids)), (
            "No ID should appear in more than one batch"
        )
        assert len(all_ids) == 2500, "All 2500 IDs must be covered across batches"

    def test_2500_ids_merged_no_duplicates_real_duckdb(self, tmp_path, monkeypatch):
        """2500 IDs → 3 Oracle batches → DuckDB merge → spool has no duplicates.

        Oracle returns unique rows per batch (synthetic, no overlap).  After
        post_aggregate SELECT DISTINCT, the spool parquet must have exactly 2500
        rows (one per container ID, dedup on 4-col key).
        """
        container_ids = [f"C-{i:05d}" for i in range(2500)]
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_container_ids",
            lambda values: (container_ids, {}, []),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_workcenter_names",
            lambda groups: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.filter_cache.get_workcenter_mapping",
            lambda: {},
        )

        # Redirect chunk dir and spool dir to tmp_path
        chunk_dir_root = tmp_path / "chunks"
        chunk_dir_root.mkdir()
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(chunk_dir_root))

        spool_dir = tmp_path / "spool" / "material_trace"
        spool_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path / "spool",
        )

        registered: List[Dict[str, Any]] = []
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            lambda ns, qid, path, row_count, **kw: (
                registered.append({"ns": ns, "qid": qid, "path": str(path), "rows": row_count}) or True
            ),
        )

        # Oracle returns one batch at a time, each batch covers its slice of IDs
        # We track which batch (chunk_idx) we're on by call count
        call_count = [0]

        def _batched_chunk_iter(self, sql, params, chunk_size=5000):
            """Return unique rows for this batch: 1000 rows for batch 0&1, 500 for batch 2."""
            batch_idx = call_count[0]
            call_count[0] += 1
            start = batch_idx * 1000
            end = min(start + 1000, 2500)
            batch_ids = [f"C-{i:05d}" for i in range(start, end)]
            # Each row is unique: different CONTAINERID, MATERIALLOTNAME differs per row
            yield _make_arrow_batch(
                container_ids=batch_ids,
                material_lot=f"MLOT-batch-{batch_idx}",
                workcenter="WC-A",
            )

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _batched_chunk_iter,
        )

        from mes_dashboard.services.material_trace_duckdb_runtime import MaterialTraceJob

        job_id = f"test-dedup-{uuid.uuid4().hex[:8]}"
        job = MaterialTraceJob(
            job_id=job_id,
            params={"mode": "lot", "values": ["LOT-BIG"], "workcenter_groups": None},
        )
        spool_path = job.run()

        # Spool parquet must be written (non-empty result)
        assert spool_path, "run() must return a non-empty spool path for 2500 rows"
        assert pathlib.Path(spool_path).exists(), (
            f"Spool parquet must exist at: {spool_path}"
        )

        # Verify spool rowcount = 2500 unique rows
        spool_table = pq.read_table(spool_path)
        actual_rows = len(spool_table)
        assert actual_rows == 2500, (
            f"Spool must contain exactly 2500 unique rows (2500 distinct containers). "
            f"Got {actual_rows}"
        )

        # Verify no CONTAINERID duplicates
        container_col = spool_table.column("CONTAINERID").to_pylist()
        assert len(container_col) == len(set(container_col)), (
            f"Spool must have no duplicate CONTAINERIDs. "
            f"Found {len(container_col) - len(set(container_col))} duplicates."
        )

        # register_spool_file must have been called exactly once
        assert len(registered) == 1, (
            f"register_spool_file must be called exactly once. Got: {registered}"
        )
        assert registered[0]["rows"] == 2500, (
            f"Registered row_count must be 2500. Got: {registered[0]['rows']}"
        )

        # Oracle was called exactly 3 times (one per batch)
        assert call_count[0] == 3, (
            f"Oracle chunk_iter must be called 3 times for 2500 IDs (3 batches). "
            f"Got {call_count[0]} calls"
        )

        # Chunk dir must be cleaned up after successful run
        job_chunk_dir = chunk_dir_root / "material_trace" / job_id
        assert not job_chunk_dir.exists(), (
            f"Chunk dir must be cleaned up after successful run. "
            f"Still exists: {job_chunk_dir}"
        )

    def test_duplicate_input_ids_produce_no_extra_rows(self, tmp_path, monkeypatch):
        """Duplicate input values in ID list produce no duplicate rows in spool.

        Passes 10 IDs where each ID appears twice (20 total inputs).  Oracle
        returns one row per unique container.  DuckDB SELECT DISTINCT must
        deduplicate to exactly 10 rows.
        """
        # 10 unique IDs, each repeated twice → 20 input values
        unique_ids = [f"C-DUP-{i:03d}" for i in range(10)]
        duplicated_input = unique_ids + unique_ids  # 20 values

        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_container_ids",
            lambda values: (duplicated_input, {}, []),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_service._resolve_workcenter_names",
            lambda groups: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.filter_cache.get_workcenter_mapping",
            lambda: {},
        )

        chunk_dir_root = tmp_path / "chunks"
        chunk_dir_root.mkdir()
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(chunk_dir_root))

        spool_dir = tmp_path / "spool" / "material_trace"
        spool_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path / "spool",
        )

        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            lambda *a, **kw: True,
        )

        # Oracle: return both copies of each ID (simulating Oracle IN-list returning
        # duplicate rows when the same ID appears twice in the IN clause)
        call_count = [0]

        def _dup_chunk_iter(self, sql, params, chunk_size=5000):
            call_count[0] += 1
            # Oracle may return all 20 input IDs (with duplicates) in one batch
            yield _make_arrow_batch(
                container_ids=duplicated_input,
                material_lot="MLOT-DUP",
                workcenter="WC-B",
            )

        monkeypatch.setattr(
            "mes_dashboard.core.oracle_arrow_reader.OracleArrowReader.chunk_iter",
            _dup_chunk_iter,
        )

        from mes_dashboard.services.material_trace_duckdb_runtime import MaterialTraceJob

        job = MaterialTraceJob(
            job_id=f"test-dup-{uuid.uuid4().hex[:8]}",
            params={"mode": "lot", "values": unique_ids, "workcenter_groups": None},
        )
        spool_path = job.run()

        assert spool_path, "run() must produce a spool for 10 unique containers"
        spool_table = pq.read_table(spool_path)
        actual_rows = len(spool_table)

        # SELECT DISTINCT on [CONTAINERID, MATERIALLOTNAME, WORKCENTERNAME, TXNDATE]
        # must reduce 20 duplicate rows to 10 unique rows
        assert actual_rows == 10, (
            f"DuckDB SELECT DISTINCT must deduplicate 20 duplicate input rows to 10. "
            f"Got {actual_rows} rows"
        )

# ===========================================================================
# Flag-off smoke: legacy path validation + dispatch
# ===========================================================================

class TestFlagOffLegacyPathSmoke:
    """Smoke tests for the flag=off (legacy) path — route dispatch and validation.

    Covers the AC-1 surface at integration level: with MATERIAL_TRACE_USE_UNIFIED_JOB=False
    the route must use the legacy enqueue_job path, not the unified is_async_available/
    enqueue_query_job path.  No live Oracle or Redis required.
    """

    def test_flag_off_validation_path_returns_400(self, monkeypatch):
        """flag=off: POST /api/material-trace/query without mode returns 400.

        Regression guard: if the flag branch broke validation short-circuit, this
        would return 503 instead of 400.
        """
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB",
            False,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/material-trace/query",
                json={},
                content_type="application/json",
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_flag_off_enqueues_legacy_job_returns_202(self, monkeypatch):
        """flag=off: valid POST (spool cold) calls legacy enqueue_job, not unified.

        AC-1: with MATERIAL_TRACE_USE_UNIFIED_JOB=False the route must call
        enqueue_job (legacy), not is_async_available or enqueue_query_job (unified).
        """
        captured: dict = {}

        def _mock_legacy_enqueue(**kwargs):
            captured.update(kwargs)
            return ("mt-legacy-smoke-001", None)

        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB",
            False,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.enqueue_job",
            _mock_legacy_enqueue,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_duckdb_runtime.MaterialTraceDuckdbRuntime.is_available",
            lambda self: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "smoke-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/material-trace/query",
                json={"mode": "lot", "values": ["LOT-SMOKE-001"]},
                content_type="application/json",
            )

        assert resp.status_code == 202, (
            f"flag=off expected 202 from legacy enqueue, got {resp.status_code}: {resp.get_json()}"
        )
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]
        # legacy enqueue_job was called (not unified enqueue_query_job)
        assert "queue_name" in captured or "worker_fn" in captured, (
            f"Legacy enqueue_job must be called with queue_name/worker_fn. Captured: {captured}"
        )

    def test_flag_off_enqueue_exception_returns_503_no_partial(self, monkeypatch):
        """flag=off + enqueue exception → 503, no partial or corrupt response.

        When enqueue_job raises (RQ/Redis crash), the route must catch it and
        return 503, not 200/202 or an unhandled 500.
        """

        def _failing_enqueue(**kwargs):
            raise RuntimeError("Simulated Redis connection refused")

        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB",
            False,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.enqueue_job",
            _failing_enqueue,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.material_trace_duckdb_runtime.MaterialTraceDuckdbRuntime.is_available",
            lambda self: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "fault-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/material-trace/query",
                json={"mode": "lot", "values": ["LOT-FAULT-001"]},
                content_type="application/json",
            )

        assert resp.status_code == 503, (
            f"flag=off + enqueue exception must return 503, got {resp.status_code}"
        )
        data = resp.get_json()
        assert data["success"] is False

