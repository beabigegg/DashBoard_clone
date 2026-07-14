# -*- coding: utf-8 -*-
"""Chunk / size-limit boundary probe tests.

Exercises requests near each system size limit to verify:
- Correct HTTP status codes (413 when above hard limits)
- Graceful spillover (Parquet) rather than errors near result thresholds
- Auto-decomposition and merge for large date-range / ID-batch queries

All boundary labels are registered in the conftest session registry so that
pytest_terminal_summary emits a consolidated OK/UNEXPECTED table.

NOTE: Probes that require a dataset large enough to reach spillover thresholds
are marked with pytest.mark.skipif guards that detect insufficient data.
"""

import os
import time
import pytest
import requests
from datetime import date, timedelta

from stress_registry import record_chunk_boundary

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

_TIMEOUT = float(os.environ.get("STRESS_TIMEOUT", "60"))


def _post(base_url: str, path: str, payload: dict, expected_statuses=(200, 202)):
    """POST and return (status_code, response_json_or_None, elapsed_sec)."""
    start = time.time()
    try:
        resp = requests.post(
            f"{base_url}{path}",
            json=payload,
            timeout=_TIMEOUT,
        )
        elapsed = time.time() - start
        try:
            body = resp.json()
        except Exception:
            body = None
        return resp.status_code, body, elapsed
    except Exception as exc:
        return None, str(exc), time.time() - start


def _get(base_url: str, path: str, params: dict | None = None):
    start = time.time()
    try:
        resp = requests.get(f"{base_url}{path}", params=params, timeout=_TIMEOUT)
        elapsed = time.time() - start
        try:
            body = resp.json()
        except Exception:
            body = None
        return resp.status_code, body, elapsed
    except Exception as exc:
        return None, str(exc), time.time() - start


def _make_padded_payload(target_bytes: int) -> dict:
    """Build a JSON-serialisable dict whose serialised size is approximately target_bytes."""
    pad_needed = max(0, target_bytes - 50)
    return {"padding": "x" * pad_needed, "action": "probe"}


def _date_range(days_back: int):
    end = date.today()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────
# 8.1 — JSON body size boundary (256 KB hard limit)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestJsonBodyBoundary:
    """Probe the 256 KB JSON request body limit."""

    @pytest.mark.parametrize("label,size_bytes,expect_ok", [
        ("JSON body 200KB (below limit)", 200 * 1024, True),
        ("JSON body 255KB (at limit)",    255 * 1024, True),
        ("JSON body 300KB (above limit)", 300 * 1024, False),
    ])
    def test_json_body_boundary(self, base_url: str, label: str, size_bytes: int, expect_ok: bool):
        payload = _make_padded_payload(size_bytes)
        # POST to query-tool/resolve which validates body size (256 KB limit).
        # A 413 is expected when above limit; 400/422 for body within limit but invalid content.
        status, body, elapsed = _post(base_url, "/api/query-tool/resolve", payload)

        if status is None:
            record_chunk_boundary(label, "UNEXPECTED", f"connection error after {elapsed:.1f}s")
            pytest.skip(f"Server unreachable: {body}")

        if expect_ok:
            ok = status in (200, 202, 400, 422, 429)  # 400/422 = validation error but body was received
            record_chunk_boundary(label, "OK" if ok else "UNEXPECTED", f"HTTP {status}")
            assert ok, f"Expected server to accept {size_bytes//1024}KB body but got HTTP {status}"
        else:
            ok = status == 413
            record_chunk_boundary(label, "OK" if ok else "UNEXPECTED", f"HTTP {status}")
            assert ok, f"Expected HTTP 413 for {size_bytes//1024}KB body but got HTTP {status}"


# ─────────────────────────────────────────────────────────────
# 8.1 — Container ID batch size boundary (200 hard limit)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestContainerIDBatchBoundary:
    """Probe the container ID batch size limit."""

    @pytest.mark.parametrize("label,id_count,expect_ok", [
        ("Container ID batch 150 (below limit)", 150, True),
        ("Container ID batch 200 (at limit)",    200, True),
        ("Container ID batch 250 (above limit)", 250, False),
    ])
    def test_container_id_batch_boundary(self, base_url: str, label: str, id_count: int, expect_ok: bool):
        ids = [f"LOT{i:06d}" for i in range(id_count)]
        # lot-history enforces a 200-ID limit on container_ids (GET, comma-separated)
        status, body, elapsed = _get(
            base_url,
            "/api/query-tool/lot-history",
            params={"container_ids": ",".join(ids)},
        )

        if status is None:
            record_chunk_boundary(label, "UNEXPECTED", "connection error")
            pytest.skip(f"Server unreachable: {body}")

        if expect_ok:
            ok = status in (200, 202, 400, 422, 404, 429)
            record_chunk_boundary(label, "OK" if ok else "UNEXPECTED", f"HTTP {status}")
            assert ok, f"Expected server to accept {id_count} IDs but got HTTP {status}"
        else:
            ok = status == 413
            record_chunk_boundary(label, "OK" if ok else "UNEXPECTED", f"HTTP {status}")
            assert ok, f"Expected HTTP 413 for {id_count} IDs but got HTTP {status}"


# ─────────────────────────────────────────────────────────────
# 8.1 — Resource detail limit boundary (500 hard limit)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestResourceDetailLimitBoundary:
    """Probe the resource detail batch size limit."""

    @pytest.mark.parametrize("label,count,expect_ok", [
        ("Resource detail limit 400 (below)",  400, True),
        ("Resource detail limit 500 (at)",     500, True),
        ("Resource detail limit 600 (above)",  600, False),
    ])
    def test_resource_detail_limit_boundary(self, base_url: str, label: str, count: int, expect_ok: bool):
        # /api/resource/detail (POST) enforces a 500-row limit on the `limit` field
        payload = {"limit": count}
        status, body, elapsed = _post(base_url, "/api/resource/detail", payload)

        if status is None:
            record_chunk_boundary(label, "UNEXPECTED", "connection error")
            pytest.skip(f"Server unreachable: {body}")

        if expect_ok:
            ok = status in (200, 202, 400, 404, 422, 429, 500, 503)
            record_chunk_boundary(label, "OK" if ok else "UNEXPECTED", f"HTTP {status}")
            assert ok, f"Expected server to accept {count} resource IDs but got HTTP {status}"
        else:
            ok = status == 413
            record_chunk_boundary(label, "OK" if ok else "UNEXPECTED", f"HTTP {status}")
            assert ok, f"Expected HTTP 413 for {count} resource IDs but got HTTP {status}"


# ─────────────────────────────────────────────────────────────
# 8.2 — Result spillover boundary (~200K row threshold)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestResultSpilloverBoundary:
    """Probe result-set size near the 200K-row / 48MB spillover threshold.

    These tests adjust the date range to target different result set sizes.
    They are skipped when the dataset is insufficient to reach the threshold.
    """

    def _run_reject_query(self, base_url: str, start_date: str, end_date: str):
        payload = {"mode": "date_range", "start_date": start_date, "end_date": end_date}
        return _post(base_url, "/api/reject-history/query", payload)

    @pytest.mark.parametrize("label,days,expect_spillover", [
        ("Spillover probe ~100K rows (below)",  90,  False),
        ("Spillover probe ~190K rows (near)",   180, False),
        ("Spillover probe ~250K rows (above)",  365, True),
    ])
    def test_result_spillover_boundary(self, base_url: str, label: str, days: int, expect_spillover: bool):
        start, end = _date_range(days)
        status, body, elapsed = self._run_reject_query(base_url, start, end)

        if status is None:
            record_chunk_boundary(label, "UNEXPECTED", "connection error")
            pytest.skip("Server unreachable")

        if status in (404, 400):
            record_chunk_boundary(label, "OK", f"dataset/range limit — HTTP {status}")
            pytest.skip(f"Dataset insufficient or range limit for spillover probe (HTTP {status})")

        assert status in (200, 202), f"Unexpected HTTP {status} for spillover probe"

        if body and isinstance(body, dict):
            data = body.get("data") or {}
            spilled = data.get("spilled") or data.get("spool_key") is not None
            if expect_spillover:
                record_chunk_boundary(label, "OK" if spilled else "UNEXPECTED",
                                      f"spilled={spilled}, HTTP {status}")
            else:
                record_chunk_boundary(label, "OK", f"spilled={spilled}, HTTP {status}")
        else:
            record_chunk_boundary(label, "OK", f"HTTP {status}, {elapsed:.1f}s")


# ─────────────────────────────────────────────────────────────
# 8.3 — Batch decomposition probes (date range + ID list)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestBatchDecompositionBoundary:
    """Probe batch decomposition and merge for large date ranges and ID lists.

    Uses minimum 1-quarter (90-day) date ranges to exercise real decomposition.
    """

    @pytest.mark.parametrize("label,days,expected_chunks", [
        ("Batch decomp 90-day (~9 chunks)",   90,  9),
        ("Batch decomp 180-day (~18 chunks)", 180, 18),
        ("Batch decomp 365-day (~37 chunks)", 365, 37),
    ])
    def test_date_range_batch_decomposition(self, base_url: str, label: str, days: int, expected_chunks: int):
        start, end = _date_range(days)
        payload = {"mode": "date_range", "start_date": start, "end_date": end}
        status, body, elapsed = _post(base_url, "/api/reject-history/query", payload)

        if status is None:
            record_chunk_boundary(label, "UNEXPECTED", "connection error")
            pytest.skip("Server unreachable")

        if days == 365 and status in (404, 400):
            record_chunk_boundary(label, "OK", f"dataset/range limit — HTTP {status}")
            pytest.skip(f"365-day range not available (HTTP {status})")

        assert status in (200, 202), f"Auto-chunked query returned unexpected HTTP {status}"
        assert elapsed < _TIMEOUT, f"Batch query timed out after {elapsed:.1f}s (limit {_TIMEOUT}s)"

        record_chunk_boundary(label, "OK", f"HTTP {status}, {elapsed:.1f}s")

    @pytest.mark.parametrize("label,id_count", [
        ("ID batch 800 (below threshold)",  800),
        ("ID batch 1500 (above threshold)", 1500),
    ])
    def test_id_batch_decomposition(self, base_url: str, label: str, id_count: int):
        ids = [f"LOT{i:06d}" for i in range(id_count)]
        payload = {"lot_ids": ids}
        start = time.time()
        status, body, elapsed = _post(base_url, "/api/reject-history/batch", payload)

        if status is None:
            record_chunk_boundary(label, "UNEXPECTED", "connection error")
            pytest.skip("Server unreachable")

        assert status in (200, 202, 404), f"Unexpected HTTP {status} for ID batch probe"
        assert elapsed < _TIMEOUT, f"ID batch timed out after {elapsed:.1f}s"

        record_chunk_boundary(label, "OK", f"HTTP {status}, {elapsed:.1f}s, {id_count} IDs")


# ─────────────────────────────────────────────────────────────
# 8.4 — Row-count chunk seam correctness (BQE-02 / BQE-03)
#
# These tests are Tier 1 unit tests embedded in the stress directory
# because they share the conftest.  They do NOT require a live server
# and are NOT marked @pytest.mark.stress — they run in the normal
# pytest suite.
# ─────────────────────────────────────────────────────────────


class TestChunkSeam:
    """Verify that decompose_by_row_count produces seam-correct ranges."""

    def _import(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
        from mes_dashboard.services.batch_query_engine import decompose_by_row_count
        return decompose_by_row_count

    def test_rn_start_row_included(self):
        """First row of each chunk (rn == start_row) is included."""
        fn = self._import()
        chunks = fn(100, rows_per_chunk=40)
        # First chunk: start_row = 1
        assert chunks[0]["start_row"] == 1
        # Second chunk: start_row = 41
        assert chunks[1]["start_row"] == 41

    def test_rn_end_row_included(self):
        """Last row of each chunk (rn == end_row) is included."""
        fn = self._import()
        chunks = fn(100, rows_per_chunk=40)
        # First chunk ends at 40
        assert chunks[0]["end_row"] == 40
        # Second chunk ends at 80
        assert chunks[1]["end_row"] == 80
        # Third chunk ends at 100
        assert chunks[2]["end_row"] == 100

    def test_no_row_duplicated_across_adjacent_chunks(self):
        """No row number appears in two consecutive chunks."""
        fn = self._import()
        chunks = fn(150, rows_per_chunk=50)
        for i in range(len(chunks) - 1):
            end_i = chunks[i]["end_row"]
            start_next = chunks[i + 1]["start_row"]
            assert start_next == end_i + 1, (
                f"chunk {i} ends at {end_i} but chunk {i+1} starts at {start_next} "
                "(gap or overlap)"
            )

    def test_no_row_dropped_at_adjacent_chunk_boundary(self):
        """No row number is skipped between consecutive chunks."""
        fn = self._import()
        total = 300
        chunks = fn(total, rows_per_chunk=100)
        all_rows = []
        for c in chunks:
            all_rows.extend(range(c["start_row"], c["end_row"] + 1))
        assert len(all_rows) == total
        assert sorted(all_rows) == list(range(1, total + 1))

    def test_boundary_mid_logical_group_no_split_artifact(self):
        """When chunk boundary falls mid-group (same TRACKINTIMESTAMP), the
        decompose function still produces correct non-overlapping ranges.

        The application-level concern (cross-shift merge spanning chunks) is
        an ADR-0003 concern for downtime; this test verifies that the pure
        arithmetic boundary is correct regardless of logical grouping.
        """
        fn = self._import()
        # 5 rows in a "logical group" spanning chunk boundary at row 3
        # Rows 1-3 in chunk 1, rows 4-5 in chunk 2
        chunks = fn(5, rows_per_chunk=3)
        assert len(chunks) == 2
        assert chunks[0] == {"start_row": 1, "end_row": 3}
        assert chunks[1] == {"start_row": 4, "end_row": 5}


class TestOrderByTieStability:
    """Verify that the ORDER BY keys documented in BQE-03 are present in paged SQL files."""

    def _sql_path(self, relative: str) -> "Path":  # noqa: F821
        import os
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent.parent
        return base / "src" / "mes_dashboard" / "sql" / relative

    def test_production_history_tie_stable_across_chunks(self):
        """production_history paged SQL must include TRACKINTIMESTAMP ASC, CONTAINERID."""
        p = self._sql_path("production_history/main_query_paged.sql")
        if not p.exists():
            pytest.skip("main_query_paged.sql not yet created")
        text = p.read_text(encoding="utf-8").upper()
        assert "TRACKINTIMESTAMP" in text
        assert "CONTAINERID" in text
        assert "ROW_NUMBER()" in text

    def test_reject_dataset_tie_stable(self):
        """reject_history paged SQL must include TXN_DAY, CONTAINERNAME."""
        p = self._sql_path("reject_history/list_paged.sql")
        if not p.exists():
            pytest.skip("list_paged.sql not yet created")
        text = p.read_text(encoding="utf-8").upper()
        assert "TXN_DAY" in text
        assert "CONTAINERNAME" in text
        assert "ROW_NUMBER()" in text

    def test_hold_dataset_tie_stable(self):
        """hold_history paged SQL must include HOLDTXNDATE, CONTAINERID."""
        p = self._sql_path("hold_history/list_paged.sql")
        if not p.exists():
            pytest.skip("list_paged.sql not yet created")
        text = p.read_text(encoding="utf-8").upper()
        assert "HOLDTXNDATE" in text
        assert "CONTAINERID" in text
        assert "ROW_NUMBER()" in text


# ─────────────────────────────────────────────────────────────
# AC-8 — Material-trace 1000-ID batch decomposition boundary
#
# Design: implementation-plan.md IP-3
#   MaterialTraceJob uses _IN_BATCH_SIZE = 1000 (material_trace_service.py L47)
#   and ChunkStrategy.ID_LIST.  IDs must be decomposed into ≤1000 per batch.
#
# These tests do NOT require Oracle or a live server.  They probe the pure
# arithmetic of decompose_by_ids at the 999 / 1000 / 1001 boundary.
# Marked @pytest.mark.stress to align with the ci-gates.md weekly gate tier.
# ─────────────────────────────────────────────────────────────


@pytest.mark.stress
class TestMaterialTrace1000IdBoundary:
    """AC-8: ID-list decomposition boundary at exactly 999 / 1000 / 1001 IDs.

    Verifies that material-trace batch decomposition produces the correct
    number of batches and that every ID appears in exactly one batch.
    No Oracle / live server required — pure arithmetic assertion.

    Referenced by test-plan.md: tests/stress/test_chunk_boundary.py::test_material_trace_1000_id_boundary
    """

    _BATCH_SIZE = 1000  # matches material_trace_service._IN_BATCH_SIZE

    @staticmethod
    def _decompose_by_ids(ids: list, batch_size: int) -> list[list]:
        """Pure-Python replica of the material-trace ID decomposition.

        Mirrors the logic at material_trace_service.py L216–217:
            for i in range(0, max(len(exact_tokens), 1), _IN_BATCH_SIZE):
                batch = exact_tokens[i : i + _IN_BATCH_SIZE]

        Returns a list of batches (each a list of IDs).
        The implementation always yields at least one batch (empty-list safe).
        """
        n = max(len(ids), 1)
        return [ids[i: i + batch_size] for i in range(0, n, batch_size)]

    @pytest.mark.parametrize("n_ids,expected_batches,max_batch_size", [
        (999,  1, 999),   # below threshold: single batch of 999
        (1000, 1, 1000),  # exactly at threshold: single batch of 1000
        (1001, 2, 1000),  # one over: two batches; second has 1 ID
        (2000, 2, 1000),  # exactly 2× threshold: two batches of 1000
        (2001, 3, 1000),  # 2× + 1: three batches; third has 1 ID
        (5000, 5, 1000),  # 5×: five batches of 1000 (max AC-5 soak scale)
    ])
    def test_material_trace_1000_id_boundary(
        self, n_ids: int, expected_batches: int, max_batch_size: int
    ) -> None:
        """ID list of size n_ids decomposes into expected_batches batches, each ≤ max_batch_size."""
        ids = [f"LOT{i:06d}" for i in range(n_ids)]
        batches = self._decompose_by_ids(ids, self._BATCH_SIZE)

        # Correct batch count
        assert len(batches) == expected_batches, (
            f"n_ids={n_ids}: expected {expected_batches} batches, got {len(batches)}"
        )

        # No batch exceeds the batch size
        for idx, batch in enumerate(batches):
            assert len(batch) <= max_batch_size, (
                f"Batch {idx} has {len(batch)} IDs > {max_batch_size} (batch_size={self._BATCH_SIZE})"
            )

        # All IDs are present and none are duplicated
        all_ids_in_batches = [id_ for batch in batches for id_ in batch]
        assert len(all_ids_in_batches) == n_ids, (
            f"n_ids={n_ids}: total IDs across batches is {len(all_ids_in_batches)} (mismatch)"
        )
        assert sorted(all_ids_in_batches) == ids, (
            f"n_ids={n_ids}: IDs across batches do not match input exactly (gap or dup)"
        )

        record_chunk_boundary(
            f"Material-trace 1000-ID boundary n={n_ids}",
            "OK",
            f"{len(batches)} batches, max_size={max(len(b) for b in batches)}",
        )

    def test_material_trace_empty_id_list_produces_one_batch(self) -> None:
        """Empty ID list produces exactly one (empty) batch — mirrors service L216 guard."""
        batches = self._decompose_by_ids([], self._BATCH_SIZE)
        # The service uses max(len(ids), 1) so one iteration is always performed
        assert len(batches) == 1, f"Expected 1 batch for empty input, got {len(batches)}"
        assert batches[0] == [], f"Expected empty batch, got {batches[0]}"
        record_chunk_boundary("Material-trace empty ID list", "OK", "1 empty batch")


# ─────────────────────────────────────────────────────────────
# production-achievement-overhaul: D6 closing-chunk fetch-completeness fix
# (PA-15) at STRESS SCALE — dozens-to-hundreds of daily TIME chunks per a
# many-day date range, not the 2-3 day hand-picked fixtures in
# tests/test_production_achievement_unified_job.py::TestChunkSeamReaggregation.
# D6 was a real, previously-shipped data-correctness bug (systematic N-shift
# under-count at the range-closing seam); this is the only place that fix is
# exercised at range sizes that actually occur in production (當月/自訂區間
# CumulativeView can span a full month or more), not merely a toy 1-4 day
# fixture.
#
# No Oracle/Redis/live server required — pure DuckDB/filesystem I/O against
# the REAL ProductionAchievementJob.pre_query()/post_aggregate() (mirrors
# tests/stress/test_production_achievement_stress.py's Oracle-fetch-mocked
# idiom). Marked @pytest.mark.stress (per this file's own precedent comment
# at TestMaterialTrace1000IdBoundary above) so it runs only via the Tier-5
# `stress-tests.yml` dispatch, not the Tier-1 unmarked-class filter.
# ─────────────────────────────────────────────────────────────


def _pa_write_chunk_parquet(chunk_dir, name: str, rows: list) -> None:
    """Write a fake per-chunk parquet using the RAW Oracle-cursor column
    names, mirroring tests/test_production_achievement_unified_job.py's
    _write_chunk_parquet (PACKAGE_LF as the 5th nullable column,
    production-achievement-overhaul PA-09)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({
        "OUTPUT_DATE": pa.array([r["OUTPUT_DATE"] for r in rows], type=pa.date32()),
        "SHIFT_CODE": pa.array([r["SHIFT_CODE"] for r in rows], type=pa.string()),
        "SPECNAME": pa.array([r["SPECNAME"] for r in rows], type=pa.string()),
        "PACKAGE_LF": pa.array([r.get("PACKAGE_LF") for r in rows], type=pa.string()),
        "ACTUAL_OUTPUT_QTY": pa.array([r["ACTUAL_OUTPUT_QTY"] for r in rows], type=pa.int64()),
    })
    pq.write_table(table, str(chunk_dir / name))


def _make_pa_job_for_d6_stress(job_id: str, start_date: str, end_date: str):
    from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob
    return ProductionAchievementJob(
        job_id=job_id, params={"start_date": start_date, "end_date": end_date}
    )


@pytest.mark.stress
class TestProductionAchievementD6ClosingChunkStress:
    """D6/PA-15 closing-chunk fetch-completeness fix at stress-scale chunk
    counts. The D6 closing chunk [end_date+1 00:00:00, end_date+1 07:30:00)
    must be included EXACTLY ONCE per query regardless of range size, with
    zero leakage or duplication across ANY of the many chunk seams spanned
    by a long date range — not just the final (closing-chunk) seam.

    Referenced by test-plan.md § Stress: "a many-day date-range query at
    stress-scale chunk counts ... asserting the D6 closing chunk ... is
    included EXACTLY ONCE per query regardless of range size, with zero
    leakage or duplication across any chunk seam" — the highest-value
    stress test in this change: D6 was a real, previously-shipped
    data-correctness bug (systematic N-shift under-count), and this is the
    only place the fix is tested at scale rather than on 2-3 day fixtures.
    """

    @pytest.mark.parametrize("n_days", [30, 90, 180])
    def test_pre_query_appends_exactly_one_closing_chunk_regardless_of_range_size(self, n_days):
        """pre_query() must build exactly n_days regular whole-day chunks
        PLUS exactly ONE D6 closing chunk — last position, never
        duplicated, never omitted — at every stress-scale range length."""
        start = date(2024, 1, 1)
        end = start + timedelta(days=n_days - 1)
        job = _make_pa_job_for_d6_stress(
            f"d6-scale-{n_days}", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
        job.pre_query()

        assert len(job._chunks) == n_days + 1, (
            f"n_days={n_days}: expected {n_days} regular + 1 closing chunk, "
            f"got {len(job._chunks)}"
        )

        regular_chunks = job._chunks[:-1]
        closing_chunk = job._chunks[-1]

        regular_starts = [c["start_date"] for c in regular_chunks]
        assert len(set(regular_starts)) == n_days, (
            "duplicate or missing regular chunk start_date at stress scale"
        )
        assert all(c["chunk_end_excl"].endswith(" 00:00:00") for c in regular_chunks), (
            "every regular chunk's chunk_end_excl must be exactly midnight"
        )

        closing_candidates = [c for c in job._chunks if c["chunk_end_excl"].endswith("07:30:00")]
        assert len(closing_candidates) == 1, (
            f"Expected exactly ONE D6 closing chunk at n_days={n_days}, found "
            f"{len(closing_candidates)}: {closing_candidates}"
        )

        # NOTE: expected_closing_start is a plain `date` -- `date + timedelta`
        # truncates to whole days only (date.__add__ uses just the .days
        # component), so the 07:30:00 time-of-day is appended as a string
        # rather than via timedelta arithmetic on the date itself (the real
        # worker computes this from a `datetime`, where the same arithmetic
        # is safe -- see production_achievement_worker.py pre_query()).
        expected_closing_start = end + timedelta(days=1)
        assert closing_chunk == {
            "start_date": expected_closing_start.strftime("%Y-%m-%d"),
            "chunk_end_excl": expected_closing_start.strftime("%Y-%m-%d") + " 07:30:00",
        }

        # No duplicate chunk entries anywhere in the full n_days+1 list.
        seen = [tuple(sorted(c.items())) for c in job._chunks]
        assert len(seen) == len(set(seen)), (
            f"duplicate chunk entries detected in pre_query() output at n_days={n_days}"
        )

        record_chunk_boundary(
            f"PA D6 pre_query chunk-count n_days={n_days}",
            "OK",
            f"{len(job._chunks)} chunks ({n_days} regular + 1 closing), no duplicates",
        )

    @pytest.mark.parametrize("n_days", [30, 90, 180])
    def test_closing_chunk_merged_exactly_once_zero_leakage_at_scale(
        self, n_days, tmp_path, monkeypatch
    ):
        """Simulates the REAL seam-straddling pattern (PA-03: an N-shift's
        pre-07:30 morning tail attributes back to the PREVIOUS calendar
        day) at EVERY one of the n_days regular day-to-day seams, PLUS the
        D6 closing-chunk seam for the LAST day — the seam D6 fixes and
        that, pre-D6, was silently dropped entirely (never fetched).
        Confirms every seam merges into exactly one row (its own SUM),
        with zero leakage into the following day's own group and zero
        duplication, across the WHOLE range — not merely the last
        (closing-chunk) seam or a 2-3 day toy fixture."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        start = date(2024, 1, 1)
        end = start + timedelta(days=n_days - 1)
        job = _make_pa_job_for_d6_stress(
            f"d6-merge-{n_days}", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
        job._spool_key = f"d6-merge-key-{n_days}"
        job._spool_path = str(tmp_path / "spool" / f"{job._spool_key}.parquet")
        chunk_dir = job._make_chunk_parquet_dir(job.job_id)

        SPEC, PKG = "SPEC-STRESS", "PKG-STRESS"
        EVENING_QTY, TAIL_QTY, D_QTY = 10, 3, 7

        # Chunk index i (0-based) is day (start + i)'s own Oracle fetch
        # window. It always carries day_i's D-shift + own evening N-shift;
        # for i > 0 it ALSO carries the PREVIOUS day's morning N-shift tail
        # (PA-03 attributes that tail back to day_{i-1}, but its
        # TRACKOUTTIMESTAMP falls inside chunk i's window) — this is the
        # real seam every TIME-chunked day boundary produces, replicated at
        # every one of the n_days-1 regular boundaries.
        for i in range(n_days):
            day_i = start + timedelta(days=i)
            rows = [
                {"OUTPUT_DATE": day_i, "SHIFT_CODE": "D", "SPECNAME": SPEC, "PACKAGE_LF": PKG, "ACTUAL_OUTPUT_QTY": D_QTY},
                {"OUTPUT_DATE": day_i, "SHIFT_CODE": "N", "SPECNAME": SPEC, "PACKAGE_LF": PKG, "ACTUAL_OUTPUT_QTY": EVENING_QTY},
            ]
            if i > 0:
                prev_day = start + timedelta(days=i - 1)
                rows.append({
                    "OUTPUT_DATE": prev_day, "SHIFT_CODE": "N", "SPECNAME": SPEC,
                    "PACKAGE_LF": PKG, "ACTUAL_OUTPUT_QTY": TAIL_QTY,
                })
            _pa_write_chunk_parquet(chunk_dir, f"chunk-{i:04d}-0000.parquet", rows)

        # D6 closing chunk: the LAST day's own morning tail. Pre-D6, this
        # window [end+1 00:00, end+1 07:30) was NEVER fetched at all (no
        # regular chunk covers it — the range-closing under-count D6 fixes).
        _pa_write_chunk_parquet(chunk_dir, f"chunk-{n_days:04d}-0000.parquet", [
            {"OUTPUT_DATE": end, "SHIFT_CODE": "N", "SPECNAME": SPEC, "PACKAGE_LF": PKG, "ACTUAL_OUTPUT_QTY": TAIL_QTY},
        ])

        t_start = time.time()
        job.post_aggregate(None)
        elapsed = time.time() - t_start

        import duckdb
        con = duckdb.connect()
        try:
            rows_out = {
                (r[0], r[1]): r[2]
                for r in con.execute(
                    f"SELECT output_date, shift_code, actual_output_qty "
                    f"FROM read_parquet('{job._spool_path}') "
                    f"WHERE SPECNAME = '{SPEC}' AND PACKAGE_LF = '{PKG}'"
                ).fetchall()
            }
        finally:
            con.close()

        # Exactly 2 rows/day (D + N) across n_days days — no more, no
        # fewer, despite n_days-1 regular seams + 1 closing-chunk seam all
        # straddling in this fixture. A plain-concat bug (instead of
        # GROUP BY SUM) would inflate this well past 2*n_days.
        assert len(rows_out) == 2 * n_days, (
            f"n_days={n_days}: expected {2 * n_days} distinct (date, shift) rows, "
            f"got {len(rows_out)} -- seam duplication or collapse at stress scale"
        )

        for i in range(n_days):
            day_i = start + timedelta(days=i)
            assert rows_out[(day_i, "D")] == D_QTY, (
                f"day index {i}: D-shift row corrupted by an unrelated seam merge"
            )
            assert rows_out[(day_i, "N")] == EVENING_QTY + TAIL_QTY, (
                f"day index {i}: seam not merged into exactly one SUMmed row "
                f"(expected {EVENING_QTY + TAIL_QTY}, got {rows_out[(day_i, 'N')]})"
            )

        # The LAST day's N-shift total specifically exercises the D6
        # closing-chunk seam (its tail has NO regular next-day chunk to
        # come from — only the closing chunk supplies it).
        assert rows_out[(end, "N")] == EVENING_QTY + TAIL_QTY, (
            "D6 closing-chunk contribution is not merged into the last day's "
            "own N-shift group exactly once"
        )

        # Zero leakage: no row was ever attributed to end_date+1 as a side
        # effect of fetching the D6 closing chunk.
        leaked_date = end + timedelta(days=1)
        assert (leaked_date, "N") not in rows_out, (
            f"D6 closing-chunk fetch leaked into {leaked_date}'s own N-shift group"
        )

        assert elapsed < 30.0, (
            f"post_aggregate over {n_days + 1} chunk parquets took {elapsed:.1f}s "
            "-- investigate non-linear scaling in the re-aggregation GROUP BY"
        )

        record_chunk_boundary(
            f"PA D6 closing-chunk merge n_days={n_days}",
            "OK",
            f"{n_days + 1} chunks -> {len(rows_out)} rows in {elapsed:.2f}s, "
            "zero leakage/duplication across every seam",
        )
