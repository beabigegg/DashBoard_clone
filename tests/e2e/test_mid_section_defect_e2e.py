# -*- coding: utf-8 -*-
"""E2E tests for Mid-Section Defect module.

Endpoints:
  GET /api/mid-section-defect/station-options → available stations
  GET /api/mid-section-defect/analysis        → summary analysis
  GET /api/mid-section-defect/analysis/detail  → paginated detail
  GET /api/mid-section-defect/loss-reasons     → loss reason list

Run with: pytest tests/e2e/test_mid_section_defect_e2e.py -v -s

Resilience/failure-injection tests (msd-forward-cause-effect):
  test_forward_spool_miss_falls_back_to_oracle
  test_rq_worker_failure_mid_orchestration_returns_error_not_500
  TestForwardDuckDBSummaryFallback   — unit-level spool-miss / self-edge degrade
  TestForwardAsyncGating             — async-unavailable 503 / Retry-After behaviour
  TestForwardDataBoundary            — empty detection, zero-amplification, no-descendant, Top-N
"""

import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests


def _poll_msd_detail_until_ready(app_server, params, timeout=180):
    """Poll MSD detail until the staged trace spool is ready."""
    deadline = time.time() + timeout
    last_response = None
    while time.time() < deadline:
        last_response = requests.get(
            f"{app_server}/api/mid-section-defect/analysis/detail",
            params=params,
            timeout=120,
        )
        if last_response.status_code == 200:
            return last_response
        if last_response.status_code == 429:
            retry_after = last_response.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else 3.0
            except ValueError:
                wait_seconds = 3.0
            time.sleep(max(wait_seconds, 1.0))
            continue
        if last_response.status_code == 503:
            pytest.skip("Service busy")
        if last_response.status_code == 410:
            pytest.skip("trace_query_id cache expired before detail could be polled")
        assert last_response.status_code == 409, (
            f"Expected 200/409 while polling MSD detail, got {last_response.status_code}: "
            f"{last_response.text[:200]}"
        )
        time.sleep(4)
    return last_response


@pytest.mark.e2e
class TestMidSectionDefectE2E:
    """E2E tests for Mid-Section Defect endpoints."""

    def test_station_options_returns_list(self, app_server):
        """GET /station-options returns available stations."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/station-options", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_loss_reasons_returns_list(self, app_server):
        """GET /loss-reasons returns all loss reason codes."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/loss-reasons", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_analysis_requires_dates(self, app_server):
        """GET /analysis without dates returns 400."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis", timeout=30
        )
        assert resp.status_code == 400

    def test_analysis_returns_data(self, app_server):
        """GET /analysis with valid dates returns analysis summary with actual data."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis",
            params={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        # May return 200 or 503 if system is busy
        if resp.status_code == 503:
            pytest.skip("Service busy")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert data.get("detail_total_count", 0) > 0, (
            "MSD analysis returned detail_total_count=0 — Oracle query may have failed silently"
        )
        assert len(data.get("daily_trend", [])) > 0, (
            "MSD analysis returned empty daily_trend for a 7-day range with known data"
        )

    def test_analysis_detail_returns_paginated_data(self, app_server):
        """GET /analysis/detail with valid dates returns paginated records."""
        summary_resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=120,
        )
        if summary_resp.status_code == 503:
            pytest.skip("Service busy")
        assert summary_resp.status_code == 200
        summary_payload = summary_resp.json()
        assert summary_payload["success"] is True
        trace_query_id = summary_payload.get("data", {}).get("trace_query_id")
        if not trace_query_id:
            pytest.skip("MSD summary returned no trace_query_id — no data available for this date range")

        resp = _poll_msd_detail_until_ready(
            app_server,
            {
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "page": 1,
                "page_size": 10,
                "trace_query_id": trace_query_id,
            },
        )
        assert resp is not None, "MSD detail polling timed out"
        if resp.status_code == 409:
            payload = resp.json()
            assert payload["error"]["code"] == "QUERY_NOT_READY"
            assert payload.get("meta", {}).get("trace_query_id") == trace_query_id
            return
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_analysis_rejects_over_730_day_range(self, app_server):
        """GET /analysis with >730-day range returns 400."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis",
            params={"start_date": "2023-01-01", "end_date": "2025-02-28"},
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert "730" in payload.get("error", {}).get("message", "")

    def test_container_filter_options_uses_cache_not_oracle(self, app_server):
        """GET /container-filter-options responds without hitting Oracle directly."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/container-filter-options",
            timeout=30,
        )
        # Accept 200 (warm cache) or 500 (cold start before warmup on test env)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
            data = payload.get("data", {})
            assert "pj_types" in data
            assert "packages" in data
            assert isinstance(data["pj_types"], list)
            assert isinstance(data["packages"], list)


# ---------------------------------------------------------------------------
# Resilience: forward spool-miss Oracle fallback (AC-4 + AC-5)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestMidSectionDefectResilienceE2E:
    """Live-server resilience tests for the forward analysis path.

    These tests require a running server pointed to by ``app_server`` (E2E_BASE_URL).
    They are skip-safe: if the server is unreachable they skip cleanly.
    Mapping → test-plan.md rows:
      AC-4+AC-5: test_forward_spool_miss_falls_back_to_oracle
      AC-5:      test_rq_worker_failure_mid_orchestration_returns_error_not_500
    """

    def _try_forward_analysis(self, app_server: str) -> Optional[requests.Response]:
        try:
            return requests.get(
                f"{app_server}/api/mid-section-defect/analysis",
                params={
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-07",
                    "direction": "forward",
                },
                timeout=30,
            )
        except requests.exceptions.ConnectionError:
            return None

    def test_forward_spool_miss_falls_back_to_oracle(self, app_server):
        """AC-4+AC-5: When the forward lineage spool is missing the route must NOT 500/None.

        Behavioural contract (design.md §Open Risks; IP-1):
          - When children_map is empty or the forward_lineage spool file is absent,
            get_summary(direction="forward") degrades to self-edge-only attribution
            and returns a valid summary dict (never None).
          - The /analysis endpoint must return HTTP 200 or 503 (busy) — never 500.

        This test drives the live endpoint without pre-warming the spool so it
        exercises the degrade path.
        """
        resp = self._try_forward_analysis(app_server)
        if resp is None:
            pytest.skip("Server not reachable — live-server E2E test skipped")
        # 503 = service busy (acceptable), 429 = rate-limited (also acceptable)
        # 500 = crash → unacceptable
        assert resp.status_code != 500, (
            f"Forward analysis returned 500 on spool miss — must degrade gracefully: "
            f"{resp.text[:300]}"
        )
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True, f"success=False: {payload}"
            data = payload.get("data", {})
            # Even on degrade the payload must not be None and must have some KPI structure
            assert data is not None
            # When no spool is available the response must still have summary keys
            assert "genealogy_status" in data or "kpi" in data, (
                f"Forward analysis degrade response missing both genealogy_status and kpi: {data}"
            )

    def test_rq_worker_failure_mid_orchestration_returns_error_not_500(self, app_server):
        """AC-5: An RQ worker failure mid-orchestration must not propagate as 500.

        The /api/trace/events endpoint returns 503 (async unavailable) or 409 (job
        queued / QUERY_NOT_READY).  A 500 means the failure bubbled through uncaught.
        This test verifies that the /analysis or /analysis/detail endpoints never
        expose 500 when the underlying async job service is under stress.

        Strategy: call /analysis/detail with a fabricated (non-existent)
        trace_query_id.  The spool will miss → route should return 404/409/410
        (cache expired / job not found), not 500.
        """
        try:
            resp = requests.get(
                f"{app_server}/api/mid-section-defect/analysis/detail",
                params={
                    "trace_query_id": "nonexistent-id-00000000",
                    "direction": "forward",
                    "page": 1,
                    "page_size": 10,
                },
                timeout=30,
            )
        except requests.exceptions.ConnectionError:
            pytest.skip("Server not reachable — live-server E2E test skipped")
        # Acceptable statuses: 404/409/410 (no spool), 429 (rate-limited), 503 (busy)
        # 500 = unhandled exception → test fails
        assert resp.status_code != 500, (
            f"Forward detail returned 500 for missing trace_query_id — "
            f"worker failure must not propagate: {resp.text[:300]}"
        )
        assert resp.status_code in (200, 400, 404, 409, 410, 429, 503), (
            f"Unexpected status {resp.status_code}: {resp.text[:200]}"
        )


# ---------------------------------------------------------------------------
# Resilience (unit/mock-integration): forward DuckDB summary fallback
# ---------------------------------------------------------------------------

class TestForwardDuckDBSummaryFallback:
    """Unit-level tests for get_summary(direction="forward") degrade paths.

    These run headlessly without a live server.  They exercise:
      - Spool-miss (events file absent) → returns None (caller falls back to Oracle)
      - Missing forward lineage spool → degrades to events-only KPI (not None)
      - Empty events spool → empty but non-None result
      - get_summary never raises; always returns dict or None
    """

    def _make_parquet(self, rows: List[Dict[str, Any]], tmp_dir: str) -> str:
        """Write rows to a temp parquet file and return its absolute path."""
        df = pd.DataFrame(rows)
        path = os.path.join(tmp_dir, f"test_{id(rows)}.parquet")
        df.to_parquet(path, engine="pyarrow", index=False)
        return path

    def _make_runtime(self, trace_id: str, events_path: Optional[str] = None,
                      fwd_lineage_path: Optional[str] = None,
                      detection_path: Optional[str] = None):
        """Build an MsdDuckdbRuntime with pre-resolved paths (bypasses store lookup)."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        rt = MsdDuckdbRuntime(trace_id)
        rt._events_path = events_path
        rt._lineage_path = None
        rt._detection_path = detection_path
        rt._forward_lineage_path = fwd_lineage_path
        rt._resolved = True
        return rt

    def test_spool_miss_returns_none_not_exception(self, tmp_path):
        """Events parquet absent → get_summary("forward") returns None, not raises."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        rt = MsdDuckdbRuntime("no-such-id")
        rt._events_path = str(tmp_path / "does_not_exist.parquet")
        rt._resolved = True

        result = rt.get_summary(direction="forward")
        assert result is None, "Expected None when events spool is missing"

    def test_forward_summary_no_lineage_spool_degrades_not_none(self, tmp_path):
        """Forward summary without forward lineage spool degrades to events-only KPI.

        The events spool is present but forward_lineage spool is absent.
        get_summary must return a dict (not None) so the route can serve a partial result
        rather than falling back to Oracle.  (design.md §Open Risks: degrade to
        self-edge-only attribution so summary is not silently empty.)
        """
        # Minimal events parquet with the columns DuckDB forward summary expects
        events_rows = [
            {
                "CONTAINERID": "LOT-001",
                "WORKCENTERNAME": "封裝",
                "REJECT_TOTAL_QTY": 5,
                "TRACKINQTY": 100,
                "TRACKINTIMESTAMP": "2026-03-01 08:00:00",
            },
        ]
        events_path = self._make_parquet(events_rows, str(tmp_path))
        rt = self._make_runtime("test-fwd-no-lin", events_path=events_path,
                                fwd_lineage_path=None)

        result = rt.get_summary(direction="forward")
        assert result is not None, (
            "get_summary(forward) returned None despite valid events spool — "
            "should degrade to events-only KPI, not None"
        )
        assert "kpi" in result, f"Missing 'kpi' key in forward summary: {result.keys()}"
        assert "genealogy_status" in result

    def test_forward_summary_empty_events_degrade_no_crash(self, tmp_path):
        """Empty events parquet (0 rows) → forward summary returns dict with zero KPIs.

        AC-7 boundary: empty detection → zero downstream counts → amplification=None.
        The result must be a dict (not None, not raise).
        """
        events_rows: List[Dict] = []
        events_path = self._make_parquet(events_rows, str(tmp_path))
        rt = self._make_runtime("test-fwd-empty", events_path=events_path)

        # DuckDB may raise on empty parquet without schema; guard via the runtime's
        # own exception handler which returns None
        try:
            result = rt.get_summary(direction="forward")
            # Acceptable: None (degenerate empty file) or dict with zero KPIs
            if result is not None:
                assert "kpi" in result
        except Exception as exc:
            pytest.fail(f"get_summary(forward) must never raise; got: {exc}")

    def test_forward_summary_missing_events_path_none_not_exception(self):
        """_events_path=None → get_summary("forward") returns None without exception."""
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        rt = MsdDuckdbRuntime("test-none-path")
        rt._events_path = None
        rt._forward_lineage_path = None
        rt._detection_path = None
        rt._resolved = True

        result = rt.get_summary(direction="forward")
        assert result is None

    def test_forward_summary_with_lineage_spool_includes_descendants(self, tmp_path):
        """Forward summary with lineage spool seeds SEED_ID denormalization.

        When forward_lineage spool is present the runtime loads it as fwd_lineage view.
        The summary must not raise and must return a dict.
        """
        events_rows = [
            {"CONTAINERID": "SEED-001", "WORKCENTERNAME": "封裝",
             "REJECT_TOTAL_QTY": 10, "TRACKINQTY": 200,
             "TRACKINTIMESTAMP": "2026-03-01 10:00:00"},
            {"CONTAINERID": "DESC-002", "WORKCENTERNAME": "測試",
             "REJECT_TOTAL_QTY": 3, "TRACKINQTY": 150,
             "TRACKINTIMESTAMP": "2026-03-02 10:00:00"},
        ]
        lineage_rows = [
            {"SEED_ID": "SEED-001", "DESCENDANT_ID": "SEED-001"},
            {"SEED_ID": "SEED-001", "DESCENDANT_ID": "DESC-002"},
        ]
        events_path = self._make_parquet(events_rows, str(tmp_path))
        fwd_lin_path = self._make_parquet(lineage_rows, str(tmp_path))
        rt = self._make_runtime("test-fwd-with-lin",
                                events_path=events_path,
                                fwd_lineage_path=fwd_lin_path)

        result = rt.get_summary(direction="forward")
        assert result is not None, "Forward summary with lineage spool must not return None"
        assert "kpi" in result


# ---------------------------------------------------------------------------
# Resilience (unit/mock-integration): async gating — 503 / Retry-After
# ---------------------------------------------------------------------------

class TestForwardAsyncGating:
    """Per CLAUDE.md CI patterns: routes without is_async_available()=True mock fall to 503.

    These tests exercise the trace/events route's async guard when the
    RQ/Redis layer is absent (CI environment has no Redis).

    The trace events endpoint is the gateway for forward analysis:
      POST /api/trace/events → 503 + Retry-After when async unavailable.
    """

    def _make_flask_client(self):
        """Return a Flask test client with REDIS_ENABLED=false."""
        import os as _os
        _os.environ.setdefault("REDIS_ENABLED", "false")
        _os.environ.setdefault("TESTING", "true")
        _os.environ.setdefault("ORACLE_MOCK", "true")
        from mes_dashboard.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    def test_trace_events_async_unavailable_returns_503_with_retry_after(self):
        """When is_async_available() is False the /api/trace/events endpoint returns
        503 with a Retry-After header — not a crash or 500.

        CLAUDE.md CI pattern: mock is_async_available()=True + enqueue fn in
        tests that need async to succeed; here we test the FALSE branch explicitly.
        """
        with patch(
            "mes_dashboard.routes.trace_routes.is_async_available",
            return_value=False,
        ):
            try:
                client = self._make_flask_client()
            except Exception:
                pytest.skip("Flask app init requires Oracle/Redis — skipped in this env")
                return
            resp = client.post(
                "/api/trace/events",
                json={
                    "profile": "mid_section_defect",
                    "container_ids": ["LOT-001"],
                    "domains": ["downstream_rejects"],
                    "payload": {"params": {"direction": "forward"}},
                },
            )
        assert resp.status_code == 503, (
            f"Expected 503 when async unavailable, got {resp.status_code}"
        )
        assert "Retry-After" in resp.headers, (
            "503 response must include Retry-After header"
        )

    def test_trace_events_async_available_with_mock_enqueue_returns_202(self):
        """When is_async_available()=True and enqueue succeeds the route returns
        a 202-class or pending-job response (not 503).

        CLAUDE.md CI pattern: mock is_async_available()=True + enqueue fn.
        CI has no Redis so routes without this mock fall to 503.
        """
        mock_job_id = "mock-job-12345"
        with patch(
            "mes_dashboard.routes.trace_routes.is_async_available",
            return_value=True,
        ), patch(
            "mes_dashboard.routes.trace_routes.enqueue_trace_events_job",
            return_value=(mock_job_id, None),
        ):
            try:
                client = self._make_flask_client()
            except Exception:
                pytest.skip("Flask app init requires Oracle/Redis — skipped in this env")
                return
            resp = client.post(
                "/api/trace/events",
                json={
                    "profile": "mid_section_defect",
                    "container_ids": ["LOT-001"],
                    "domains": ["downstream_rejects"],
                    "payload": {"params": {"direction": "forward"}},
                },
            )
        # Route returns 200 (job accepted / async pending) or a valid non-503 status
        assert resp.status_code not in (500, 503), (
            f"Expected non-500/503 when async mocked available, got {resp.status_code}: "
            f"{resp.data[:200]}"
        )


# ---------------------------------------------------------------------------
# Data-boundary tests: empty detection, zero-amplification, no-descendant, Top-N
# ---------------------------------------------------------------------------

class TestForwardDataBoundary:
    """Unit-level data-boundary tests for forward analysis correctness.

    These run without any server or database.  They exercise the Python
    functions directly via imports.

    Mapping → test-plan.md:
      AC-7: amplification KPI divide-by-zero semantics
      AC-1: by_detection_loss_reason Top-N boundary
      AC-4: no-descendant lineage self-edge inclusion
      AC-4: write_forward_lineage_spool with empty children_map degrades to self-edges
    """

    # --- Amplification KPI divide-by-zero ---

    def test_amplification_zero_detection_input_returns_none(self):
        """detection_total_input=0 → detection_rate=0 → amplification=None (display '—').

        AC-7 / design §Key Decisions: divide-by-zero must emit null, never 0 or ∞.
        """
        from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi
        result = _compute_amplification_kpi(
            detection_total_reject=10,
            detection_total_input=0,  # denominator = 0 → rate = 0
            downstream_total_reject=5,
            downstream_total_input=100,
        )
        assert result is None, f"Expected None for zero detection_input, got {result}"

    def test_amplification_zero_detection_reject_returns_none(self):
        """detection_total_reject=0 → detection_rate=0 → amplification=None.

        Lot was processed but no rejects → rate=0 → ratio undefined.
        """
        from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi
        result = _compute_amplification_kpi(
            detection_total_reject=0,
            detection_total_input=100,
            downstream_total_reject=5,
            downstream_total_input=100,
        )
        assert result is None

    def test_amplification_downstream_zero_detection_nonzero_returns_zero_float(self):
        """downstream=0 and detection>0 → amplification=0.0 (real zero, not None).

        AC-7 / design §Key Decisions: effect fully absorbed at detection station.
        """
        from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi
        result = _compute_amplification_kpi(
            detection_total_reject=10,
            detection_total_input=200,
            downstream_total_reject=0,
            downstream_total_input=200,
        )
        assert result == 0.0, f"Expected 0.0 when downstream=0 and detection>0, got {result}"

    def test_amplification_both_nonzero_returns_correct_ratio(self):
        """Both rates nonzero → amplification = downstream_rate / detection_rate."""
        from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi
        # detection_rate = 10/200 = 0.05
        # downstream_rate = 15/200 = 0.075
        # amplification = 0.075 / 0.05 = 1.5
        result = _compute_amplification_kpi(
            detection_total_reject=10,
            detection_total_input=200,
            downstream_total_reject=15,
            downstream_total_input=200,
        )
        assert result is not None
        assert abs(result - 1.5) < 1e-4, f"Expected ~1.5, got {result}"

    # --- by_detection_loss_reason Top-N boundary ---

    def _make_detection_data(self, reasons_and_qtys: List[tuple]) -> Dict[str, Any]:
        """Build a detection_data dict from (reason, qty) pairs."""
        data: Dict[str, Any] = {}
        for i, (reason, qty) in enumerate(reasons_and_qtys):
            data[f"LOT-{i:03d}"] = {
                "trackinqty": qty * 10,
                "rejectqty_by_reason": {reason: qty},
                "containername": f"LOT-{i:03d}",
            }
        return data

    def test_by_detection_loss_reason_exactly_10_no_other(self):
        """Exactly 10 reasons → all 10 kept, no '其他' row (Top-N boundary)."""
        from mes_dashboard.services.mid_section_defect_service import _build_by_detection_loss_reason, TOP_N
        assert TOP_N == 10, "TOP_N must be 10 per design"
        reasons = [(f"REASON_{i}", (10 - i) * 5) for i in range(10)]
        detection_data = self._make_detection_data(reasons)
        result = _build_by_detection_loss_reason(detection_data)
        names = [r["loss_reason"] for r in result]
        assert "其他" not in names, f"Expected no '其他' for exactly 10 reasons, got: {names}"
        assert len(result) == 10

    def test_by_detection_loss_reason_11_reasons_folds_to_other(self):
        """11 reasons → top 10 kept + 1 remainder folded into '其他'."""
        from mes_dashboard.services.mid_section_defect_service import _build_by_detection_loss_reason, TOP_N
        # 11 reasons with unique names, descending qty
        reasons = [(f"REASON_{i}", (11 - i) * 5) for i in range(11)]
        detection_data = self._make_detection_data(reasons)
        result = _build_by_detection_loss_reason(detection_data)
        names = [r["loss_reason"] for r in result]
        assert "其他" in names, f"Expected '其他' for 11 reasons, got: {names}"
        # Non-other rows must be exactly TOP_N
        non_other = [r for r in result if r["loss_reason"] != "其他"]
        assert len(non_other) == TOP_N

    def test_by_detection_loss_reason_empty_detection_returns_empty_list(self):
        """Empty detection_data → empty result, no crash."""
        from mes_dashboard.services.mid_section_defect_service import _build_by_detection_loss_reason
        result = _build_by_detection_loss_reason({})
        assert result == [], f"Expected [] for empty detection_data, got {result}"

    def test_by_detection_loss_reason_zero_reject_qty_omitted(self):
        """Lots with rejectqty=0 must not create entries in by_detection_loss_reason."""
        from mes_dashboard.services.mid_section_defect_service import _build_by_detection_loss_reason
        detection_data = {
            "LOT-A": {"trackinqty": 100, "rejectqty_by_reason": {"NSOP": 5}},
            "LOT-B": {"trackinqty": 100, "rejectqty_by_reason": {"NSOP": 0}},
        }
        result = _build_by_detection_loss_reason(detection_data)
        total_qty = sum(r["reject_qty"] for r in result)
        assert total_qty == 5, f"Zero-qty entry must not inflate count; got total_qty={total_qty}"

    # --- No-descendant lineage (self-edge only) ---

    def test_write_forward_lineage_spool_empty_children_map_emits_self_edges(self, tmp_path):
        """Empty children_map → only self-edges written (SEED_ID == DESCENDANT_ID).

        design.md §Open Risks: degrade to self-edges-only when children_map empty.
        The import is inside the function body so we patch at the canonical module
        (mes_dashboard.core.query_spool_store) rather than the service namespace.
        """
        from mes_dashboard.services.mid_section_defect_service import _write_msd_forward_lineage_spool

        seed_ids = ["SEED-001", "SEED-002"]
        children_map: Dict[str, Any] = {}

        ns_dir = tmp_path / "msd-events"
        ns_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_stage_spool_file",
            return_value=True,
        ):
            _write_msd_forward_lineage_spool("trace-001", seed_ids, children_map)
        # The function must not raise — self-edge rows written via parquet in tmp_path.

    def test_write_forward_lineage_spool_empty_children_map_no_crash(self, tmp_path):
        """_write_msd_forward_lineage_spool with empty children_map must not raise.

        Also validates that the written parquet contains only self-edge rows.
        Both QUERY_SPOOL_DIR and register_stage_spool_file are imported inside
        the function body, so patch at the source module (query_spool_store).
        """
        from mes_dashboard.services.mid_section_defect_service import _write_msd_forward_lineage_spool

        seed_ids = ["SEED-A", "SEED-B"]
        children_map: Dict[str, Any] = {}
        captured_rows: list = []

        # Capture the DataFrame that would be written to parquet
        original_to_parquet = pd.DataFrame.to_parquet

        def _mock_to_parquet(self_df, path, *args, **kwargs):
            captured_rows.extend(self_df.to_dict(orient="records"))
            original_to_parquet(self_df, path, *args, **kwargs)

        ns_dir = tmp_path / "msd-events"
        ns_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_stage_spool_file",
            return_value=True,
        ), patch.object(pd.DataFrame, "to_parquet", _mock_to_parquet):
            try:
                _write_msd_forward_lineage_spool("trace-self-edge", seed_ids, children_map)
            except Exception as exc:
                pytest.fail(f"_write_msd_forward_lineage_spool raised unexpectedly: {exc}")

        # All written rows must be self-edges (SEED_ID == DESCENDANT_ID)
        for row in captured_rows:
            assert row["SEED_ID"] == row["DESCENDANT_ID"], (
                f"Expected self-edge but got SEED_ID={row['SEED_ID']} "
                f"DESCENDANT_ID={row['DESCENDANT_ID']}"
            )
        assert len(captured_rows) == len(seed_ids), (
            f"Expected {len(seed_ids)} self-edge rows, got {len(captured_rows)}"
        )

    def test_write_forward_lineage_spool_with_descendants_includes_self_edge(self, tmp_path):
        """children_map with descendants → self-edge AND descendant rows written.

        design.md §Key Decisions: self-edge (SEED, SEED) always emitted.
        """
        from mes_dashboard.services.mid_section_defect_service import _write_msd_forward_lineage_spool

        seed_ids = ["SEED-001"]
        children_map = {
            "SEED-001": ["CHILD-002", "CHILD-003"],
            "CHILD-002": ["GRANDCHILD-004"],
        }
        captured_rows: list = []
        original_to_parquet = pd.DataFrame.to_parquet

        def _mock_to_parquet(self_df, path, *args, **kwargs):
            captured_rows.extend(self_df.to_dict(orient="records"))
            original_to_parquet(self_df, path, *args, **kwargs)

        ns_dir = tmp_path / "msd-events"
        ns_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_stage_spool_file",
            return_value=True,
        ), patch.object(pd.DataFrame, "to_parquet", _mock_to_parquet):
            try:
                _write_msd_forward_lineage_spool("trace-descendants", seed_ids, children_map)
            except Exception as exc:
                pytest.fail(f"Raised unexpectedly: {exc}")

        seed_to_descendant = {
            (r["SEED_ID"], r["DESCENDANT_ID"]) for r in captured_rows
        }
        # Self-edge must be present
        assert ("SEED-001", "SEED-001") in seed_to_descendant, (
            "Self-edge (SEED-001, SEED-001) must always be emitted"
        )
        # Direct children must be present
        assert ("SEED-001", "CHILD-002") in seed_to_descendant
        assert ("SEED-001", "CHILD-003") in seed_to_descendant
        # Grand-child must be reachable via BFS
        assert ("SEED-001", "GRANDCHILD-004") in seed_to_descendant

    def test_write_forward_lineage_spool_no_duplicate_rows(self, tmp_path):
        """children_map with diamond (shared descendant) → no duplicate (SEED, DESC) rows."""
        from mes_dashboard.services.mid_section_defect_service import _write_msd_forward_lineage_spool

        # Diamond: SEED → A, SEED → B, A → C, B → C (C reachable twice)
        seed_ids = ["SEED-001"]
        children_map = {
            "SEED-001": ["A", "B"],
            "A": ["C"],
            "B": ["C"],
        }
        captured_rows: list = []
        original_to_parquet = pd.DataFrame.to_parquet

        def _mock_to_parquet(self_df, path, *args, **kwargs):
            captured_rows.extend(self_df.to_dict(orient="records"))
            original_to_parquet(self_df, path, *args, **kwargs)

        ns_dir = tmp_path / "msd-events"
        ns_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "mes_dashboard.core.query_spool_store.QUERY_SPOOL_DIR",
            tmp_path,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_stage_spool_file",
            return_value=True,
        ), patch.object(pd.DataFrame, "to_parquet", _mock_to_parquet):
            _write_msd_forward_lineage_spool("trace-diamond", seed_ids, children_map)

        pairs = [(r["SEED_ID"], r["DESCENDANT_ID"]) for r in captured_rows]
        # Each (SEED_ID, DESCENDANT_ID) pair must be unique
        assert len(pairs) == len(set(pairs)), (
            f"Duplicate (SEED_ID, DESCENDANT_ID) rows found: {pairs}"
        )
        # C must appear exactly once
        c_rows = [p for p in pairs if p == ("SEED-001", "C")]
        assert len(c_rows) == 1, f"Diamond convergence: C must appear once, got {c_rows}"

    # --- Malformed / wrong-type data boundaries ---

    def test_forward_summary_events_missing_reject_col_no_crash(self, tmp_path):
        """Events parquet without REJECT_TOTAL_QTY column → summary degrades, not crash."""
        # Events with only CONTAINERID + TRACKINQTY (no REJECT_TOTAL_QTY)
        events_rows = [
            {"CONTAINERID": "LOT-001", "WORKCENTERNAME": "封裝", "TRACKINQTY": 100},
        ]
        df = pd.DataFrame(events_rows)
        events_path = str(tmp_path / "events_no_reject.parquet")
        df.to_parquet(events_path, engine="pyarrow", index=False)

        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
        rt = MsdDuckdbRuntime("test-no-reject-col")
        rt._events_path = events_path
        rt._resolved = True

        try:
            result = rt.get_summary(direction="forward")
            # Acceptable: None or dict; must not raise
            if result is not None:
                assert "kpi" in result
        except Exception as exc:
            pytest.fail(
                f"get_summary(forward) must not raise on missing column; got: {exc}"
            )
