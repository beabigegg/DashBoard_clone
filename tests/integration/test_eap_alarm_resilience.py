# -*- coding: utf-8 -*-
"""Resilience tests for EAP ALARM Analysis.

Tests:
  - test_oracle_failure_during_spool: RQ job fails on Oracle error → job status = failed
  - test_redis_failure_returns_503: Redis unavailable → 503
  - test_spool_miss_fine_filter_returns_410: fine-filter endpoint with expired spool → 410

pytestmark = pytest.mark.integration
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


# ── Oracle failure during spool ───────────────────────────────────────────────

def test_oracle_failure_during_spool(tmp_path, monkeypatch):
    """RQ job propagates Oracle error; complete_job called with error."""
    error_message = "ORA-00942: table or view does not exist"
    error_calls = []

    def mock_read_sql_slow(*args, **kwargs):
        raise Exception(error_message)

    monkeypatch.setattr("mes_dashboard.core.database.read_sql_df_slow", mock_read_sql_slow)
    monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
    monkeypatch.setattr(
        "mes_dashboard.services.async_query_job_service.update_job_progress",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "mes_dashboard.services.async_query_job_service.complete_job",
        lambda prefix, job_id, **kw: error_calls.append(kw),
    )
    monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))

    from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

    with pytest.raises(Exception, match="ORA-00942"):
        run_eap_alarm_query_job(
            job_id="test-oracle-fail",
            date_from="2025-01-01",
            date_to="2025-01-07",
            eqp_types=["GDBA"],
        )

    # complete_job must have been called with an error
    assert len(error_calls) >= 1, "complete_job must be called on Oracle failure"
    assert any("error" in call_kw and call_kw["error"] for call_kw in error_calls), (
        f"complete_job must be called with error kwarg on Oracle failure. Got: {error_calls}"
    )


# ── Redis failure returns 503 ─────────────────────────────────────────────────

def test_redis_failure_returns_503(monkeypatch):
    """When enqueue_job returns (None, error), POST /spool returns 503."""
    monkeypatch.setattr(
        "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
        lambda key: None,  # cold spool
    )
    monkeypatch.setattr(
        "mes_dashboard.services.async_query_job_service.enqueue_job",
        lambda **kw: (None, "Redis unavailable"),
    )
    monkeypatch.setattr(
        "mes_dashboard.core.permissions.get_owner_token",
        lambda: "test-user",
    )

    app = _make_app()
    with app.test_client() as client:
        resp = client.post(
            "/api/eap-alarm/spool",
            json={
                "date_from": "2025-01-01",
                "date_to": "2025-01-07",
                "eqp_types": ["GDBA"],
            },
            content_type="application/json",
        )

    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert data["success"] is False


# ── Spool miss on fine-filter endpoints returns 410 ───────────────────────────

@pytest.mark.parametrize("endpoint", [
    "/api/eap-alarm/filter-options?query_id=expired_key",
    "/api/eap-alarm/summary?query_id=expired_key",
    "/api/eap-alarm/pareto?query_id=expired_key",
    "/api/eap-alarm/trend?query_id=expired_key",
    "/api/eap-alarm/detail?query_id=expired_key",
])
def test_spool_miss_fine_filter_returns_410(endpoint, monkeypatch):
    """Fine-filter endpoints with expired/unknown spool → 410 CACHE_EXPIRED."""
    monkeypatch.setattr(
        "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
        lambda key: None,
    )

    app = _make_app()
    with app.test_client() as client:
        resp = client.get(endpoint)

    assert resp.status_code == 410, (
        f"Expected 410 for {endpoint}, got {resp.status_code}: {resp.get_json()}"
    )
    data = resp.get_json()
    assert data["success"] is False


# ── In-flight job: client abandons polling (page unload simulation) ───────────

def test_inflight_abort(monkeypatch):
    """In-flight job: client abandons poll mid-flight by never calling status again.

    EAP ALARM has no server-side abort endpoint (Type B, 7 endpoints total;
    api-contract rows 248-254).  The backend resilience surface for 'page unload'
    is: GET /spool/status returns a non-5xx response for a job still in
    'started' / 'queued' state, allowing the client to poll once and then stop
    without corrupting server state.
    """
    in_progress_status = {
        "success": True,
        "data": {
            "status": "started",
            "pct": 15,
            "progress": "Oracle 查詢中",
            "elapsed_seconds": 5,
            "query_id": "eap-alarm-inflight-001",
        },
        "meta": {},
    }

    monkeypatch.setattr(
        "mes_dashboard.services.async_query_job_service.get_job_status",
        lambda prefix, job_id: in_progress_status["data"],
    )

    app = _make_app()
    with app.test_client() as client:
        # Client polls once by job_id (in-flight: job exists but not done)
        # then abandons — simulates page unload. Status endpoint uses ?job_id=
        # for in-flight poll; ?query_id= is for spool-hit check.
        resp = client.get(
            "/api/eap-alarm/spool/status?job_id=eap-alarm-inflight-001"
        )

    # Status poll for an in-progress job must return non-5xx
    assert resp.status_code in (200, 202), (
        f"In-progress status poll must return 200/202, got {resp.status_code}: "
        f"{resp.get_json()}"
    )
    data = resp.get_json()
    assert data["success"] is True
    # Client can inspect status and decide to abandon; no server crash
    assert data["data"]["status"] in ("started", "queued", "pending", "running"), (
        f"In-flight status must be a non-terminal state: {data['data']['status']!r}"
    )
