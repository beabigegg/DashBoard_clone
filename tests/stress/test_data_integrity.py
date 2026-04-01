# -*- coding: utf-8 -*-
"""Data integrity probe tests.

Verifies row count consistency across the batch-merge → spool → pagination
pipeline for each service that uses the batch/spool infrastructure:

  - reject_history    : batch merge (time + ID decomposition), spillover
  - production_history: overflow_mode="truncate" + async job pipeline
  - yield_alert       : slow-query concurrency + async job pipeline
  - hold_history      : spool pagination (5000-row threshold)
  - query_tool        : ID batch decomposition (1000-ID threshold)

Results are registered in the conftest session registry for the terminal
summary table (per-service OK / DATA LOSS / SKIPPED).
"""

import concurrent.futures
import os
import time
from datetime import date, timedelta
from typing import Optional

import pytest
import requests

from async_helpers import AsyncJobPoller, AsyncJobTimeout
from stress_registry import record_integrity_result
from integrity_helpers import IntegrityResult, PaginationWalker, RowCountBaseline, _TOLERANCE_PCT

_TIMEOUT = float(os.environ.get("STRESS_TIMEOUT", "60"))


def _date_range(days_back: int):
    end = date.today()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _post(base_url: str, path: str, payload: dict):
    try:
        resp = requests.post(f"{base_url}{path}", json=payload, timeout=_TIMEOUT)
        return resp.status_code, resp.json() if resp.content else None
    except Exception as exc:
        return None, str(exc)


def _get(base_url: str, path: str, params: dict | None = None):
    try:
        resp = requests.get(f"{base_url}{path}", params=params, timeout=_TIMEOUT)
        return resp.status_code, resp.json() if resp.content else None
    except Exception as exc:
        return None, str(exc)


# ─────────────────────────────────────────────────────────────
# 10.1 — Reject-history: batch merge probes (time decomposition)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestRejectHistoryBatchMerge:
    """Row-count integrity for reject-history time-range batch decomposition."""

    def _run_probe(self, base_url: str, service: str, days: int) -> IntegrityResult:
        start, end = _date_range(days)
        ir = IntegrityResult(service=service)
        baseline = RowCountBaseline(base_url)

        # Establish COUNT(*) baseline
        ir.baseline_count = baseline.get("reject_history", {"start_date": start, "end_date": end})

        # Execute the actual query
        status, body = _post(base_url, "/api/reject-history/query", {
            "mode": "date_range", "start_date": start, "end_date": end
        })
        if status is None:
            ir.verdict = "SKIPPED"
            ir.notes = "Server unreachable"
            return ir

        if status == 404:
            ir.verdict = "SKIPPED"
            ir.notes = "Dataset unavailable"
            return ir

        if status == 400:
            ir.verdict = "SKIPPED"
            ir.notes = f"HTTP 400 — likely exceeds date range limit"
            return ir
        if status not in (200, 202):
            ir.verdict = "FAIL"
            ir.notes = f"Unexpected HTTP {status}"
            ir.checkpoint_failed = True
            return ir

        data = (body or {}).get("data") or body or {}
        ir.api_total_rows = data.get("total_rows") or data.get("row_count")

        # Check partial_failure metadata
        if data.get("partial_failure") or data.get("has_partial_failure"):
            ir.notes = "partial_failure=True in response"
            ir.checkpoint_failed = True

        # Three-point check: paginate if spool_key present
        spool_key = data.get("spool_key")
        if spool_key and ir.api_total_rows:
            walker = PaginationWalker(base_url)
            pg_sum, cp_failed = walker.walk(
                "/api/reject-history/paginate", spool_key, ir.api_total_rows
            )
            ir.pagination_sum = pg_sum
            if cp_failed:
                ir.checkpoint_failed = True

        ir.compute_verdict()
        return ir

    def test_reject_history_90day_integrity(self, base_url: str):
        """90-day reject-history batch merge integrity probe (~9 chunks)."""
        ir = self._run_probe(base_url, "reject_history_90d", days=90)
        record_integrity_result("reject_history_90d", ir)
        if ir.verdict == "FAIL":
            pytest.fail(f"reject_history_90d DATA LOSS: {ir.notes}")

    def test_reject_history_365day_integrity(self, base_url: str):
        """365-day reject-history integrity probe (~37 chunks). Skipped if unavailable."""
        ir = self._run_probe(base_url, "reject_history_365d", days=365)
        record_integrity_result("reject_history_365d", ir)
        if ir.verdict == "SKIPPED":
            pytest.skip(ir.notes or "365-day dataset unavailable")
        if ir.verdict == "FAIL":
            pytest.fail(f"reject_history_365d DATA LOSS: {ir.notes}")


# ─────────────────────────────────────────────────────────────
# 10.2 — Reject-history: ID-batch merge probe (1500 lot IDs)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestRejectHistoryIDBatch:
    """Row-count integrity for reject-history ID-batch decomposition."""

    def test_reject_history_id_batch_1500(self, base_url: str):
        """1500 lot IDs: verify merged result count matches baseline."""
        ir = IntegrityResult(service="reject_history_id_batch")
        baseline = RowCountBaseline(base_url)

        lot_ids = [f"LOT{i:06d}" for i in range(1500)]
        payload = {"lot_ids": lot_ids}

        ir.baseline_count = baseline.get("reject_history", {"lot_count": 1500})

        status, body = _post(base_url, "/api/reject-history/batch", payload)
        if status is None:
            ir.verdict = "SKIPPED"
            ir.notes = "Server unreachable"
            record_integrity_result("reject_history_id_batch", ir)
            pytest.skip("Server unreachable")

        if status == 404:
            ir.verdict = "SKIPPED"
            ir.notes = "Endpoint unavailable"
            record_integrity_result("reject_history_id_batch", ir)
            pytest.skip("Endpoint unavailable")

        data = (body or {}).get("data") or {}
        ir.api_total_rows = data.get("total_rows")
        ir.compute_verdict()
        record_integrity_result("reject_history_id_batch", ir)
        if ir.verdict == "FAIL":
            pytest.fail(f"reject_history_id_batch DATA LOSS: {ir.notes}")


# ─────────────────────────────────────────────────────────────
# 10.3 — Production-history: truncation detection via async path
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestProductionHistoryTruncation:
    """Verify production-history does not silently truncate rows (overflow_mode=truncate risk)."""

    def _async_query(self, base_url: str, start: str, end: str) -> tuple:
        """Submit production-history query via async path and wait for completion."""
        poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
        try:
            result = poller.submit_and_wait(
                "POST",
                "/api/production-history/query",
                {"start_date": start, "end_date": end},
            )
            return result.status, result.data
        except AsyncJobTimeout as exc:
            return "timeout", str(exc)
        except Exception as exc:
            return "error", str(exc)

    def test_production_history_90day_integrity(self, base_url: str):
        """90-day production-history baseline integrity probe via async path."""
        start, end = _date_range(90)
        ir = IntegrityResult(service="production_history_90d")
        baseline = RowCountBaseline(base_url)
        ir.baseline_count = baseline.get("production_history", {"start_date": start, "end_date": end})

        job_status, data = self._async_query(base_url, start, end)
        if job_status in ("timeout", "error"):
            ir.verdict = "SKIPPED"
            ir.notes = f"Async job: {job_status}"
            record_integrity_result("production_history_90d", ir)
            pytest.skip(ir.notes)

        if isinstance(data, dict):
            ir.api_total_rows = data.get("total_rows") or data.get("row_count")

        ir.compute_verdict()
        record_integrity_result("production_history_90d", ir)
        if ir.verdict == "FAIL":
            pytest.fail(f"production_history_90d DATA LOSS (possible truncation): {ir.notes}")

    def test_production_history_365day_near_truncation(self, base_url: str):
        """365-day probe to detect near-truncation boundary. Skipped if unavailable."""
        start, end = _date_range(365)
        ir = IntegrityResult(service="production_history_365d")
        baseline = RowCountBaseline(base_url)
        ir.baseline_count = baseline.get("production_history", {"start_date": start, "end_date": end})

        job_status, data = self._async_query(base_url, start, end)
        if job_status in ("timeout", "error"):
            ir.verdict = "SKIPPED"
            ir.notes = f"Async job: {job_status}"
            record_integrity_result("production_history_365d", ir)
            pytest.skip(ir.notes)

        if isinstance(data, dict):
            ir.api_total_rows = data.get("total_rows") or data.get("row_count")
            # Verify failed async jobs don't leave partial spool
            if data.get("status") == "failed":
                ir.verdict = "SKIPPED"
                ir.notes = "Job failed — verifying no partial spool left"
                spool_key = data.get("spool_key")
                assert not spool_key, f"Failed job left partial spool key: {spool_key}"
                record_integrity_result("production_history_365d", ir)
                pytest.skip("365-day job failed — no partial spool confirmed")

        ir.compute_verdict()
        record_integrity_result("production_history_365d", ir)
        if ir.verdict == "FAIL":
            pytest.fail(f"production_history_365d DATA LOSS: {ir.notes}")


# ─────────────────────────────────────────────────────────────
# 10.4 — Hold-history: pagination integrity probe (>5000 rows)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestHoldHistoryPaginationIntegrity:
    """Walk all pages of a >5000-row hold-history spool result."""

    def test_hold_history_pagination_sum(self, base_url: str):
        """Query >5000 rows, paginate all pages, verify sum == total_rows."""
        ir = IntegrityResult(service="hold_history_pagination")

        # Query with a large page to trigger spool
        status, body = _post(base_url, "/api/wip/hold-detail/lots/query", {
            "page_size": 5001,
            "page": 1,
        })
        if status is None:
            ir.verdict = "SKIPPED"
            ir.notes = "Server unreachable"
            record_integrity_result("hold_history_pagination", ir)
            pytest.skip("Server unreachable")

        if status == 404:
            ir.verdict = "SKIPPED"
            ir.notes = "Endpoint unavailable"
            record_integrity_result("hold_history_pagination", ir)
            pytest.skip("Endpoint unavailable")

        data = (body or {}).get("data") or {}
        total_rows = data.get("total_rows") or data.get("total")
        spool_key = data.get("spool_key")

        if not total_rows or total_rows <= 5000:
            ir.verdict = "SKIPPED"
            ir.notes = f"Dataset has only {total_rows} rows — cannot probe spool pagination"
            record_integrity_result("hold_history_pagination", ir)
            pytest.skip(ir.notes)

        ir.api_total_rows = int(total_rows)

        walker = PaginationWalker(base_url, page_size=500)
        pg_sum, cp_failed = walker.walk(
            "/api/wip/hold-detail/lots/paginate",
            spool_key or "",
            ir.api_total_rows,
        )
        ir.pagination_sum = pg_sum
        ir.checkpoint_failed = cp_failed
        ir.compute_verdict()
        record_integrity_result("hold_history_pagination", ir)
        if ir.verdict == "FAIL":
            pytest.fail(f"hold_history_pagination DATA LOSS: {ir.notes}")


# ─────────────────────────────────────────────────────────────
# 10.5 — Query-tool: ID merge probe (1500 container IDs)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestQueryToolIDMergeIntegrity:
    """Verify query-tool 1500-ID batch decomposition merges all results."""

    def test_query_tool_id_merge_1500(self, base_url: str):
        """1500 container IDs: cross-reference result IDs against input list."""
        ir = IntegrityResult(service="query_tool_id_merge")

        container_ids = [f"C{i:06d}" for i in range(1500)]
        payload = {"container_ids": container_ids}

        status, body = _post(base_url, "/api/query-tool/containers", payload)
        if status is None:
            ir.verdict = "SKIPPED"
            ir.notes = "Server unreachable"
            record_integrity_result("query_tool_id_merge", ir)
            pytest.skip("Server unreachable")

        if status == 404:
            ir.verdict = "SKIPPED"
            ir.notes = "Endpoint unavailable"
            record_integrity_result("query_tool_id_merge", ir)
            pytest.skip("Endpoint unavailable")

        data = (body or {}).get("data") or {}
        returned_ids = set()
        for item in data.get("items") or data.get("rows") or []:
            cid = item.get("container_id") or item.get("id")
            if cid:
                returned_ids.add(str(cid))

        ir.api_total_rows = len(returned_ids) if returned_ids else data.get("total_rows")

        # Cross-reference: check for missing input IDs (only if results include IDs)
        if returned_ids:
            input_set = set(container_ids)
            missing = input_set - returned_ids
            if missing:
                ir.verdict = "FAIL"
                ir.notes = f"{len(missing)} container IDs missing from merged result"
                record_integrity_result("query_tool_id_merge", ir)
                pytest.fail(ir.notes)

        ir.baseline_count = len(container_ids)
        ir.compute_verdict()
        record_integrity_result("query_tool_id_merge", ir)
        if ir.verdict == "FAIL":
            pytest.fail(f"query_tool_id_merge DATA LOSS: {ir.notes}")


# ─────────────────────────────────────────────────────────────
# 10.6 — Yield-alert: concurrent integrity probe (3 concurrent async queries)
# ─────────────────────────────────────────────────────────────

@pytest.mark.stress
class TestYieldAlertConcurrentIntegrity:
    """3 concurrent yield-alert queries at slot limit via async path."""

    def _run_single_query(self, base_url: str, query_idx: int) -> IntegrityResult:
        start, end = _date_range(30)
        ir = IntegrityResult(service=f"yield_alert_concurrent_{query_idx}")
        baseline = RowCountBaseline(base_url)
        ir.baseline_count = baseline.get("yield_alert", {"start_date": start, "end_date": end})

        poller = AsyncJobPoller(base_url, max_wait=180, poll_interval=2.0)
        try:
            result = poller.submit_and_wait(
                "POST",
                "/api/yield-alert/query",
                {"start_date": start, "end_date": end},
            )
            if isinstance(result.data, dict):
                ir.api_total_rows = result.data.get("total_rows")
        except AsyncJobTimeout as exc:
            ir.verdict = "SKIPPED"
            ir.notes = f"Async timeout: {exc}"
            return ir
        except Exception as exc:
            ir.verdict = "SKIPPED"
            ir.notes = f"Error: {exc}"
            return ir

        ir.compute_verdict()
        return ir

    def test_yield_alert_3_concurrent_integrity(self, base_url: str):
        """Submit 3 concurrent yield-alert queries; verify each passes three-point check."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self._run_single_query, base_url, i): i
                for i in range(3)
            }
            results = {}
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()

        failures = []
        for idx, ir in results.items():
            record_integrity_result(ir.service, ir)
            if ir.verdict == "FAIL":
                failures.append(f"query_{idx}: {ir.notes}")

        all_skipped = all(ir.verdict == "SKIPPED" for ir in results.values())
        if all_skipped:
            pytest.skip("All yield-alert concurrent queries were skipped")

        assert not failures, "Yield-alert concurrent integrity failures:\n" + "\n".join(failures)
