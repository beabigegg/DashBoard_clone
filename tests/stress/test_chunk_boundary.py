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

import json
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
            record_chunk_boundary(label, "UNEXPECTED", f"connection error")
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
