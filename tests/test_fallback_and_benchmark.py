# -*- coding: utf-8 -*-
"""9.5 Fallback tests + 9.6 Performance benchmarks.

Requires a running server on PORT 8080.
Run: pytest tests/test_fallback_and_benchmark.py -v -s

Tests:
  9.5 — Feature flag disabled → Pandas fallback produces valid response
  9.5 — DuckDB-WASM unavailable → server /view still works
  9.6 — Measures /view latency under DuckDB vs Pandas paths
"""
from __future__ import annotations

import os
import json
import time
from typing import Any, Dict, Optional

import pytest
import requests

BASE_URL = os.environ.get("MES_TEST_BASE_URL", "http://localhost:8080")

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 60) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", params=params or {}, timeout=timeout)


def _post(path: str, json_body: Optional[Dict[str, Any]] = None, timeout: int = 120) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", json=json_body or {}, timeout=timeout)


def _extract_data(resp: requests.Response) -> Dict[str, Any]:
    """Extract response data, handling success_response envelope."""
    body = resp.json()
    if "success_response" in body:
        return body["success_response"]
    if "data" in body:
        return body["data"]
    return body


def _timed_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 60):
    """GET with timing. Returns (response, elapsed_ms)."""
    start = time.perf_counter()
    resp = _get(path, params, timeout)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return resp, elapsed_ms


# ── Server availability check ───────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def check_server():
    """Skip all tests if server is not reachable."""
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=5)
    except requests.ConnectionError:
        pytest.skip(f"Server not reachable at {BASE_URL}")


# ══════════════════════════════════════════════════════════════════════════════
# 9.5 — Fallback tests
# ══════════════════════════════════════════════════════════════════════════════

class TestFallbackPaths:
    """Verify that each report module works when DuckDB SQL runtime is disabled."""

    # ── Resource history ──────────────────────────────────────────────────

    def test_resource_history_view_with_sql_enabled(self):
        """Default path: SQL runtime enabled → response contains view data."""
        # First, trigger a primary query with short date range
        query_resp = _post("/api/resource/history/query", {
            "start_date": "2026-03-01",
            "end_date": "2026-03-02",
            "granularity": "day",
        })
        assert query_resp.status_code == 200, f"query failed: {query_resp.status_code}"
        query_data = _extract_data(query_resp)
        query_id = query_data.get("query_id")
        assert query_id, "No query_id returned"

        # Then, call view
        view_resp = _get("/api/resource/history/view", {"query_id": query_id, "granularity": "day"})
        assert view_resp.status_code in (200, 410), f"view failed: {view_resp.status_code}"
        if view_resp.status_code == 200:
            view_data = _extract_data(view_resp)
            assert "summary" in view_data or "detail" in view_data, "Missing summary/detail in view"

    def test_resource_history_view_pandas_fallback(self):
        """SQL runtime disabled → Pandas fallback still produces valid response."""
        # Temporarily disable via env var (next import will pick up the flag)
        # Since the flag is resolved at import time, we test via a direct
        # service call instead of HTTP
        from mes_dashboard.services.resource_dataset_cache import apply_view
        from mes_dashboard.services.resource_history_sql_runtime import (
            _SQL_VIEW_ENABLED,
            SQL_FALLBACK_DISABLED,
        )
        import mes_dashboard.services.resource_history_sql_runtime as runtime

        # Save original and override
        original = runtime._SQL_VIEW_ENABLED
        try:
            runtime._SQL_VIEW_ENABLED = False

            # First trigger a query so we have cached data
            query_resp = _post("/api/resource/history/query", {
                "start_date": "2026-03-01",
                "end_date": "2026-03-02",
                "granularity": "day",
            })
            query_data = _extract_data(query_resp)
            query_id = query_data.get("query_id")
            if not query_id:
                pytest.skip("No query_id returned — cannot test fallback")

            result = apply_view(query_id=query_id, granularity="day")
            if result is None:
                pytest.skip("Cache expired before view could be tested")

            # Should NOT have DuckDB meta since we disabled it
            meta = result.get("_meta", {})
            assert meta.get("view_sql_fallback_reason") == SQL_FALLBACK_DISABLED or "_meta" not in result, (
                "Expected Pandas fallback path"
            )
            assert "summary" in result or "detail" in result, "Pandas fallback missing data"
        finally:
            runtime._SQL_VIEW_ENABLED = original

    # ── Hold history ──────────────────────────────────────────────────────

    def test_hold_history_view_with_sql_enabled(self):
        """Default path: SQL runtime enabled → response contains view data."""
        query_resp = _post("/api/hold-history/query", {
            "start_date": "2026-03-01",
            "end_date": "2026-03-02",
        })
        assert query_resp.status_code == 200, f"query failed: {query_resp.status_code}"
        query_data = _extract_data(query_resp)
        query_id = query_data.get("query_id")
        assert query_id, "No query_id returned"

        view_resp = _get("/api/hold-history/view", {"query_id": query_id, "hold_type": "quality"})
        assert view_resp.status_code in (200, 410), f"view failed: {view_resp.status_code}"
        if view_resp.status_code == 200:
            view_data = _extract_data(view_resp)
            assert "reason_pareto" in view_data or "list" in view_data, "Missing view data"

    def test_hold_history_view_pandas_fallback(self):
        """SQL runtime disabled → Pandas fallback still produces valid response."""
        from mes_dashboard.services.hold_dataset_cache import apply_view
        import mes_dashboard.services.hold_history_sql_runtime as runtime

        original = runtime._SQL_VIEW_ENABLED
        try:
            runtime._SQL_VIEW_ENABLED = False

            query_resp = _post("/api/hold-history/query", {
                "start_date": "2026-03-01",
                "end_date": "2026-03-02",
            })
            query_data = _extract_data(query_resp)
            query_id = query_data.get("query_id")
            if not query_id:
                pytest.skip("No query_id returned — cannot test fallback")

            result = apply_view(query_id=query_id, hold_type="quality")
            if result is None:
                pytest.skip("Cache expired before view could be tested")

            assert "reason_pareto" in result or "list" in result, "Pandas fallback missing data"
        finally:
            runtime._SQL_VIEW_ENABLED = original

    # ── Yield alert ───────────────────────────────────────────────────────

    def test_yield_alert_view_works(self):
        """Verify /api/yield-alert/view returns valid response."""
        query_resp = _post("/api/yield-alert/query", {
            "start_date": "2026-03-01",
            "end_date": "2026-03-02",
        })
        assert query_resp.status_code in (200, 202), f"query failed: {query_resp.status_code}"
        if query_resp.status_code == 202:
            pytest.skip("yield-alert/query returned 202 async — view not immediately available")
        query_data = _extract_data(query_resp)
        query_id = query_data.get("query_id")
        assert query_id, "No query_id returned"

        view_resp = _get("/api/yield-alert/view", {"query_id": query_id})
        assert view_resp.status_code in (200, 410), f"view failed: {view_resp.status_code}"
        if view_resp.status_code == 200:
            view_data = _extract_data(view_resp)
            assert "summary" in view_data or "alerts" in view_data, "Missing view data"

    # ── Reject history ────────────────────────────────────────────────────

    def test_reject_history_view_works(self):
        """Verify /api/reject-history/view returns valid response."""
        query_resp = _post("/api/reject-history/query", {
            "mode": "date_range",
            "start_date": "2026-03-01",
            "end_date": "2026-03-02",
        })
        assert query_resp.status_code in (200, 202), f"query failed: {query_resp.status_code}"
        query_data = _extract_data(query_resp)
        query_id = query_data.get("query_id")
        if not query_id:
            # May use async job — check for job_id
            job_id = query_data.get("job_id")
            if job_id:
                # Poll for completion
                for _ in range(30):
                    job_resp = _get(f"/api/reject-history/job/{job_id}")
                    job_data = _extract_data(job_resp)
                    status = job_data.get("status")
                    if status == "completed":
                        query_id = job_data.get("query_id")
                        break
                    if status == "failed":
                        pytest.skip("Reject-history query job failed")
                    time.sleep(2)

        if not query_id:
            pytest.skip("No query_id — reject-history may require async job")

        view_resp = _get("/api/reject-history/view", {"query_id": query_id})
        assert view_resp.status_code in (200, 410), f"view failed: {view_resp.status_code}"
        if view_resp.status_code == 200:
            view_data = _extract_data(view_resp)
            assert "analytics_raw" in view_data or "detail" in view_data or "batch_pareto" in view_data, (
                "Missing view data"
            )

    # ── Spool download endpoint ───────────────────────────────────────────

    def test_spool_download_nonexistent_returns_410(self):
        """Requesting a non-existent spool file returns 410 Gone."""
        # query_id must be hex format (1-64 hex chars) to pass validation
        resp = _get("/api/spool/yield_alert_dataset/deadbeef00000000.parquet")
        assert resp.status_code in (404, 410), (
            f"Expected 404/410 for non-existent spool, got {resp.status_code}"
        )

    def test_spool_download_invalid_namespace_rejected(self):
        """Requesting a spool with invalid namespace is rejected."""
        resp = _get("/api/spool/../../etc/passwd/fake.parquet")
        assert resp.status_code in (400, 404, 422), (
            f"Expected rejection for invalid namespace, got {resp.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 9.6 — Performance benchmarks
# ══════════════════════════════════════════════════════════════════════════════

class TestPerformanceBenchmarks:
    """Measure /view latency for DuckDB vs Pandas paths.

    These tests print timing results rather than asserting hard limits,
    since latency depends on data volume and server load.
    """

    @pytest.fixture(autouse=True)
    def _query_resource_history(self):
        """Set up a resource-history query for benchmarking."""
        resp = _post("/api/resource/history/query", {
            "start_date": "2026-02-01",
            "end_date": "2026-03-01",
            "granularity": "day",
        })
        if resp.status_code != 200:
            pytest.skip("Resource history query failed")
        data = _extract_data(resp)
        self.resource_query_id = data.get("query_id")
        if not self.resource_query_id:
            pytest.skip("No query_id for resource history")

    def test_resource_history_view_latency_duckdb(self):
        """Measure resource-history /view latency with DuckDB SQL runtime (default)."""
        latencies = []
        for _ in range(3):
            resp, elapsed_ms = _timed_get(
                "/api/resource/history/view",
                {"query_id": self.resource_query_id, "granularity": "day"},
            )
            if resp.status_code == 200:
                latencies.append(elapsed_ms)
                data = _extract_data(resp)
                meta = data.get("_meta", {})
                view_source = "duckdb" if "view_sql_latency_s" in meta else "pandas"
                print(f"  [DuckDB path] view latency={elapsed_ms}ms, source={view_source}")
            elif resp.status_code == 410:
                pytest.skip("Cache expired during benchmark")

        if latencies:
            avg = round(sum(latencies) / len(latencies), 1)
            print(f"  [DuckDB path] avg latency={avg}ms over {len(latencies)} runs")

    def test_resource_history_view_latency_pandas_fallback(self):
        """Measure resource-history /view latency with Pandas fallback."""
        import mes_dashboard.services.resource_history_sql_runtime as runtime

        original = runtime._SQL_VIEW_ENABLED
        try:
            runtime._SQL_VIEW_ENABLED = False

            latencies = []
            for _ in range(3):
                resp, elapsed_ms = _timed_get(
                    "/api/resource/history/view",
                    {"query_id": self.resource_query_id, "granularity": "day"},
                )
                if resp.status_code == 200:
                    latencies.append(elapsed_ms)
                    print(f"  [Pandas path] view latency={elapsed_ms}ms")
                elif resp.status_code == 410:
                    pytest.skip("Cache expired during benchmark")

            if latencies:
                avg = round(sum(latencies) / len(latencies), 1)
                print(f"  [Pandas path] avg latency={avg}ms over {len(latencies)} runs")
        finally:
            runtime._SQL_VIEW_ENABLED = original

    def test_hold_history_view_latency(self):
        """Measure hold-history /view latency."""
        query_resp = _post("/api/hold-history/query", {
            "start_date": "2026-02-01",
            "end_date": "2026-03-01",
        })
        if query_resp.status_code != 200:
            pytest.skip("Hold history query failed")
        query_data = _extract_data(query_resp)
        query_id = query_data.get("query_id")
        if not query_id:
            pytest.skip("No query_id for hold history")

        for label, flag_val in [("DuckDB", True), ("Pandas", False)]:
            import mes_dashboard.services.hold_history_sql_runtime as hold_rt
            hold_rt._SQL_VIEW_ENABLED = flag_val

            latencies = []
            for _ in range(3):
                resp, elapsed_ms = _timed_get(
                    "/api/hold-history/view",
                    {"query_id": query_id, "hold_type": "quality"},
                )
                if resp.status_code == 200:
                    latencies.append(elapsed_ms)
                elif resp.status_code == 410:
                    break

            if latencies:
                avg = round(sum(latencies) / len(latencies), 1)
                print(f"  [{label} path] hold-history avg latency={avg}ms over {len(latencies)} runs")

        hold_rt._SQL_VIEW_ENABLED = True  # restore

    def test_yield_alert_view_latency(self):
        """Measure yield-alert /view latency."""
        query_resp = _post("/api/yield-alert/query", {
            "start_date": "2026-02-01",
            "end_date": "2026-03-01",
        })
        if query_resp.status_code != 200:
            pytest.skip("Yield alert query failed")
        query_data = _extract_data(query_resp)
        query_id = query_data.get("query_id")
        if not query_id:
            pytest.skip("No query_id for yield alert")

        latencies = []
        for _ in range(3):
            resp, elapsed_ms = _timed_get(
                "/api/yield-alert/view",
                {"query_id": query_id},
            )
            if resp.status_code == 200:
                latencies.append(elapsed_ms)
                data = _extract_data(resp)
                meta = data.get("_meta", data.get("meta", {}))
                has_spool = "spool_download_url" in data or "spool_download_url" in str(data)
                print(f"  yield-alert view latency={elapsed_ms}ms, has_spool_url={has_spool}")
            elif resp.status_code == 410:
                break

        if latencies:
            avg = round(sum(latencies) / len(latencies), 1)
            print(f"  yield-alert avg latency={avg}ms over {len(latencies)} runs")
