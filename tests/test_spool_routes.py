# -*- coding: utf-8 -*-
"""Integration tests for spool route endpoints.

Coverage:
  - 400 validation: invalid namespace, invalid query_id format
  - 410 Gone: spool file missing / expired
  - 200 streaming: valid spool file streams parquet bytes
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── Namespace validation ──────────────────────────────────────────────────────

def test_unknown_namespace_returns_400(client):
    resp = client.get("/api/spool/unknown_ns/abc123.parquet")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_path_traversal_in_namespace_returns_400(client):
    resp = client.get("/api/spool/../etc/passwd/abc123.parquet")
    # Flask routing will either 404 or 400 — in either case, not 200.
    assert resp.status_code in (400, 404)


# ── query_id format validation ────────────────────────────────────────────────

def test_invalid_query_id_non_hex_returns_400(client):
    resp = client.get("/api/spool/yield_alert_dataset/not-hex-chars!.parquet")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_valid_namespace_but_missing_spool_returns_410(client):
    with patch(
        "mes_dashboard.routes.spool_routes.get_spool_file_path",
        return_value=None,
    ):
        resp = client.get("/api/spool/yield_alert_dataset/abc123.parquet")
    assert resp.status_code == 410


def test_valid_namespace_but_file_not_on_disk_returns_410(client):
    with patch(
        "mes_dashboard.routes.spool_routes.get_spool_file_path",
        return_value="/tmp/does_not_exist_xyz.parquet",
    ):
        resp = client.get("/api/spool/yield_alert_dataset/abc123.parquet")
    assert resp.status_code == 410


# ── Successful spool download ─────────────────────────────────────────────────

def test_valid_spool_streams_parquet(client, tmp_path):
    fake_parquet = tmp_path / "test.parquet"
    fake_parquet.write_bytes(b"PAR1" + b"\x00" * 12)  # minimal fake parquet magic
    with patch(
        "mes_dashboard.routes.spool_routes.get_spool_file_path",
        return_value=str(fake_parquet),
    ), patch(
        "mes_dashboard.routes.spool_routes.should_enforce_csrf",
        return_value=False,
    ):
        resp = client.get("/api/spool/yield_alert_dataset/abc123.parquet")
    assert resp.status_code == 200
    assert resp.content_type == "application/octet-stream"
    assert resp.data[:4] == b"PAR1"


# ── Allowed namespaces ────────────────────────────────────────────────────────

@pytest.mark.parametrize("ns", [
    "yield_alert_dataset",
    "reject_dataset",
    "resource_dataset",
    "hold_dataset",
    "downtime_analysis_base_events",
    "downtime_analysis_job_bridge",
    "wip_dataset",  # wip-rq-worker-chunks-cleanup
    "production_achievement",  # production-achievement-async-spool
    "uph_performance",  # add-uph-performance-page
])
def test_allowed_namespaces_pass_namespace_validation(client, ns):
    with patch(
        "mes_dashboard.routes.spool_routes.get_spool_file_path",
        return_value=None,
    ), patch(
        "mes_dashboard.routes.spool_routes.should_enforce_csrf",
        return_value=False,
    ):
        resp = client.get(f"/api/spool/{ns}/abc123.parquet")
    # Should reach spool-expired logic, not namespace-invalid
    assert resp.status_code == 410


def test_resource_dataset_stays_in_allowed_namespaces():
    """resource_dataset namespace must remain in spool_routes._ALLOWED_NAMESPACES (AC-8).

    This is a regression guard: resource-history-rq-async reuses the existing
    resource_dataset namespace (no new namespace was added). Removing it from
    _ALLOWED_NAMESPACES would cause HTTP 400 for all resource-history parquet downloads.
    """
    from mes_dashboard.routes import spool_routes
    assert "resource_dataset" in spool_routes._ALLOWED_NAMESPACES, (
        "'resource_dataset' must remain in spool_routes._ALLOWED_NAMESPACES "
        "(resource-history-rq-async reuses this namespace; removal causes HTTP 400)"
    )


def test_eap_alarm_in_allowed_namespaces():
    """eap_alarm namespace must be in spool_routes._ALLOWED_NAMESPACES.

    Added by change eap-alarm-analysis. Required for GET /api/spool/eap_alarm/<query_id>.parquet
    to work. Removal causes HTTP 400 for all EAP ALARM parquet downloads.
    """
    from mes_dashboard.routes import spool_routes
    assert "eap_alarm" in spool_routes._ALLOWED_NAMESPACES, (
        "'eap_alarm' must be in spool_routes._ALLOWED_NAMESPACES "
        "(eap-alarm-analysis adds this namespace; removal causes HTTP 400)"
    )


def test_wip_dataset_in_allowed_namespaces():
    """wip_dataset namespace must be in spool_routes._ALLOWED_NAMESPACES (AC-7).

    Added by change wip-rq-worker-chunks-cleanup. Required for
    GET /api/spool/wip_dataset/<query_id>.parquet to serve async WIP detail results.
    Removal causes HTTP 400 for all async WIP detail parquet downloads.
    """
    from mes_dashboard.routes import spool_routes
    assert "wip_dataset" in spool_routes._ALLOWED_NAMESPACES, (
        "'wip_dataset' must be in spool_routes._ALLOWED_NAMESPACES "
        "(wip-rq-worker-chunks-cleanup adds this namespace; removal causes HTTP 400)"
    )


def test_production_achievement_in_allowed_namespaces():
    """production_achievement namespace must be in spool_routes._ALLOWED_NAMESPACES.

    Added by change production-achievement-async-spool. Required for
    GET /api/spool/production_achievement/<query_id>.parquet to serve the
    SPECNAME-grain async spool. Removal causes HTTP 400 for all
    production-achievement parquet downloads (AC-3).
    """
    from mes_dashboard.routes import spool_routes
    assert "production_achievement" in spool_routes._ALLOWED_NAMESPACES, (
        "'production_achievement' must be in spool_routes._ALLOWED_NAMESPACES "
        "(production-achievement-async-spool adds this namespace; removal causes HTTP 400)"
    )


def test_uph_performance_in_allowed_namespaces():
    """uph_performance namespace must be in spool_routes._ALLOWED_NAMESPACES.

    Added by change add-uph-performance-page. Required for
    GET /api/spool/uph_performance/<query_id>.parquet to serve the UPH
    Performance async spool. Removal causes HTTP 400 for all UPH Performance
    parquet downloads.
    """
    from mes_dashboard.routes import spool_routes
    assert "uph_performance" in spool_routes._ALLOWED_NAMESPACES, (
        "'uph_performance' must be in spool_routes._ALLOWED_NAMESPACES "
        "(add-uph-performance-page adds this namespace; removal causes HTTP 400)"
    )
