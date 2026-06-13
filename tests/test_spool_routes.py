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
