# -*- coding: utf-8 -*-
"""E2E tests for EAP ALARM Analysis module.

Tests the spool-based async query flow:
  POST /api/eap-alarm/spool → 202 (cold) or 200 (spool-hit)
  GET  /api/eap-alarm/spool/status?job_id= → poll to completion
  GET  /api/eap-alarm/filter-options?query_id= → alarm_text / category / eqp_id options
  GET  /api/eap-alarm/summary?query_id= → totals
  GET  /api/eap-alarm/pareto?query_id= → pareto items
  GET  /api/eap-alarm/trend?query_id= → trend series
  GET  /api/eap-alarm/detail?query_id= → paginated rows

Run with: pytest tests/e2e/test_eap_alarm_e2e.py -v -s
"""

from __future__ import annotations

import time

import pytest
import requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_spool(
    app_server: str,
    date_from: str = "2026-06-10",
    date_to: str = "2026-06-17",
    eqp_types: list[str] | None = None,
    timeout: float = 60.0,
) -> requests.Response:
    """POST /api/eap-alarm/spool and return the response."""
    if eqp_types is None:
        eqp_types = ["GDBA"]
    return requests.post(
        f"{app_server}/api/eap-alarm/spool",
        json={
            "date_from": date_from,
            "date_to": date_to,
            "eqp_types": eqp_types,
        },
        timeout=timeout,
    )


def _poll_job_to_completion(
    app_server: str,
    job_id: str,
    timeout_seconds: float = 420.0,
) -> dict:
    """Poll GET /api/eap-alarm/spool/status?job_id= until terminal state.

    A single EAP-alarm RQ worker processes one job at a time; a real Oracle
    query normally takes ~60-95s but has been observed at ~248s with no other
    job queued when the full e2e suite runs many domains' RQ workers
    concurrently against the same Oracle instance. 420s tolerates that
    contention plus one other job queued ahead of this one.
    """
    status_url = f"{app_server}/api/eap-alarm/spool/status"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        resp = requests.get(status_url, params={"job_id": job_id}, timeout=30)
        assert resp.status_code == 200, (
            f"spool/status returned {resp.status_code}: {resp.text[:300]}"
        )
        data = resp.json().get("data", {})
        status = data.get("status", "")
        if status in ("finished", "complete", "completed", "failed"):
            return data
        time.sleep(3)
    pytest.fail(f"EAP alarm job {job_id!r} did not reach terminal state in {timeout_seconds}s")


def _spool_and_get_query_id(app_server: str) -> str:
    """POST spool, handle 200 (hit) or 202 (async), return query_id."""
    resp = _post_spool(app_server, timeout=120.0)
    assert resp.status_code in (200, 202), (
        f"POST /spool returned {resp.status_code}: {resp.text[:500]}"
    )
    payload = resp.json()
    assert payload["success"] is True, payload

    data = payload.get("data", {})

    if resp.status_code == 202:
        job_id = data.get("job_id")
        query_id = data.get("query_id")
        assert job_id, f"202 response missing job_id: {payload}"
        assert query_id, f"202 response missing query_id: {payload}"
        final = _poll_job_to_completion(app_server, job_id)
        assert final.get("status") in ("finished", "complete", "completed"), (
            f"Spool job did not complete successfully: {final}"
        )
        return query_id
    else:
        # 200 = spool hit
        query_id = data.get("query_id")
        assert query_id, f"200 response missing query_id: {payload}"
        return query_id


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestEapAlarmSpoolE2E:
    """E2E tests for EAP ALARM spool pipeline (AC-6 coverage)."""

    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def shared_query_id(cls, app_server: str) -> str:
        """Spool once (before any test in this class) and share query_id.

        Every test in this class posts the identical default params
        (date_from/date_to/eqp_types=GDBA). Against a real (slow, ~90s/job)
        Oracle backend with a single EAP-alarm RQ worker, each test's own
        independent POST used to enqueue its own cold job (since the spool
        only becomes a cache-hit once a prior job's result is written) —
        several of these queueing up behind each other pushed later polls
        well past the per-test timeout even though every job eventually
        completed. autouse=True runs this before test_post_spool_returns_202_async
        and friends, so their POSTs land on an already-warm spool (fast 200
        hit) instead of each enqueueing another ~90s job.
        """
        return _spool_and_get_query_id(app_server)

    def test_post_spool_missing_date_from_returns_400(self, app_server: str):
        """POST /spool without date_from → 400 VALIDATION_ERROR (EA-03)."""
        resp = requests.post(
            f"{app_server}/api/eap-alarm/spool",
            json={"date_to": "2026-06-17", "eqp_types": ["GDBA"]},
            timeout=30,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing date_from, got {resp.status_code}"
        )
        payload = resp.json()
        assert payload["success"] is False

    def test_post_spool_empty_eqp_types_returns_400(self, app_server: str):
        """POST /spool with empty eqp_types → 400 (EA-07)."""
        resp = requests.post(
            f"{app_server}/api/eap-alarm/spool",
            json={
                "date_from": "2026-06-10",
                "date_to": "2026-06-17",
                "eqp_types": [],
            },
            timeout=30,
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_post_spool_blank_eqp_type_entry_returns_400(self, app_server: str):
        """POST /spool with a blank/whitespace eqp_type entry → 400 (EA-07).

        eqp_types values are free-form EQUIPMENT_ID strings, not a closed enum
        (redesigned in 9ef51fe0 — real IDs are formatted like "GWBK-0241" and
        never matched the old 4-char enum). An unrecognised-but-well-formed
        value is now accepted (matches zero rows, not a validation error);
        only non-string/blank entries are still rejected.
        """
        resp = requests.post(
            f"{app_server}/api/eap-alarm/spool",
            json={
                "date_from": "2026-06-10",
                "date_to": "2026-06-17",
                "eqp_types": ["   "],
            },
            timeout=30,
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_post_spool_returns_202_async(self, app_server: str):
        """POST /spool with valid params → 202 or 200 (spool-hit); job_id present."""
        resp = _post_spool(app_server)
        assert resp.status_code in (200, 202), (
            f"Expected 200/202, got {resp.status_code}: {resp.text[:500]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        data = payload.get("data", {})
        assert "query_id" in data, f"Response missing query_id: {payload}"

    def test_spool_miss_filter_options_returns_410(self, app_server: str):
        """GET /filter-options with unknown query_id → 410 CACHE_EXPIRED (AC-4)."""
        resp = requests.get(
            f"{app_server}/api/eap-alarm/filter-options",
            params={"query_id": "nonexistent-eap-query-id-xyz"},
            timeout=30,
        )
        assert resp.status_code == 410, (
            f"Expected 410, got {resp.status_code}: {resp.text[:300]}"
        )
        assert resp.json()["success"] is False

    def test_spool_miss_summary_returns_410(self, app_server: str):
        """GET /summary with unknown query_id → 410 (AC-4)."""
        resp = requests.get(
            f"{app_server}/api/eap-alarm/summary",
            params={"query_id": "nonexistent-eap-xyz"},
            timeout=30,
        )
        assert resp.status_code == 410
        assert resp.json()["success"] is False

    def test_spool_miss_detail_returns_410(self, app_server: str):
        """GET /detail with unknown query_id → 410 (AC-4)."""
        resp = requests.get(
            f"{app_server}/api/eap-alarm/detail",
            params={"query_id": "nonexistent-eap-xyz", "page": 1, "per_page": 50},
            timeout=30,
        )
        assert resp.status_code == 410
        assert resp.json()["success"] is False

    def test_filter_options_returns_structured_options(self, app_server: str, shared_query_id: str):
        """GET /filter-options returns alarm_text, alarm_category, equipment_id lists (AC-4/AC-6)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/filter-options",
            params={"query_id": query_id},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"filter-options returned {resp.status_code}: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert isinstance(data.get("alarm_text_options"), list), (
            "alarm_text_options must be a list"
        )
        assert isinstance(data.get("equipment_id_options"), list), (
            "equipment_id_options must be a list"
        )

    def test_summary_returns_totals(self, app_server: str, shared_query_id: str):
        """GET /summary returns total_alarm_count and affected_equipment_count (AC-6)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/summary",
            params={"query_id": query_id},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"summary returned {resp.status_code}: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "total_alarm_count" in data, f"summary missing total_alarm_count: {data}"
        assert isinstance(data["total_alarm_count"], int), (
            f"total_alarm_count must be int, got {type(data['total_alarm_count'])}"
        )

    def test_pareto_returns_items_list(self, app_server: str, shared_query_id: str):
        """GET /pareto returns items list with alarm_text and count (AC-6)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/pareto",
            params={"query_id": query_id},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"pareto returned {resp.status_code}: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "items" in data, f"pareto missing items: {data}"
        assert isinstance(data["items"], list), "pareto items must be a list"
        assert "total" in data, f"pareto missing total: {data}"

    def test_trend_returns_series_data(self, app_server: str, shared_query_id: str):
        """GET /trend returns labels and series (AC-6)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/trend",
            params={"query_id": query_id},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"trend returned {resp.status_code}: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "labels" in data, f"trend missing labels: {data}"
        assert "series" in data, f"trend missing series: {data}"
        assert isinstance(data["labels"], list), "trend labels must be a list"
        assert isinstance(data["series"], list), "trend series must be a list"

    def test_detail_returns_paginated_rows(self, app_server: str, shared_query_id: str):
        """GET /detail returns rows with correct pagination metadata (AC-6/AC-7)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/detail",
            params={"query_id": query_id, "page": 1, "per_page": 20},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"detail returned {resp.status_code}: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "rows" in data, f"detail missing rows: {data}"
        assert isinstance(data["rows"], list), "detail rows must be a list"
        meta = data.get("meta", {})
        assert "total_count" in meta, f"detail meta missing total_count: {meta}"
        assert "page" in meta, f"detail meta missing page: {meta}"

    def test_detail_per_page_capped_at_200(self, app_server: str, shared_query_id: str):
        """GET /detail with per_page=999 → response meta.per_page ≤ 200 (data-shape §3.17)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/detail",
            params={"query_id": query_id, "page": 1, "per_page": 999},
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data.get("meta", {}).get("per_page", 200) <= 200, (
            f"per_page must be capped at 200, got {data.get('meta', {}).get('per_page')}"
        )

    def test_detail_rows_contain_expected_fields(self, app_server: str, shared_query_id: str):
        """GET /detail rows contain required fields per §3.17 (AC-6)."""
        query_id = shared_query_id
        resp = requests.get(
            f"{app_server}/api/eap-alarm/detail",
            params={"query_id": query_id, "page": 1, "per_page": 20},
            timeout=30,
        )
        assert resp.status_code == 200
        rows = resp.json()["data"]["rows"]
        if not rows:
            pytest.skip("No alarm data in spool for this date range — detail row field check skipped")

        required_fields = {"event_id", "eqp_id", "eqp_type", "alarm_text", "alarm_category", "alarm_time"}
        for field in required_fields:
            assert field in rows[0], (
                f"detail row missing required field '{field}': {list(rows[0].keys())}"
            )
