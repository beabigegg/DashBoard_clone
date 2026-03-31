# -*- coding: utf-8 -*-
"""Integration tests for dashboard route endpoints.

Coverage:
  - Success envelope shape: /kpi, /workcenter_cards, /detail, /ou_trend, /heatmap
  - Error path: internal_error returned when service returns None
  - Response conforms to API contract (success: true, data: {...})
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

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


# ── /api/dashboard/kpi ────────────────────────────────────────────────────────

@patch("mes_dashboard.routes.dashboard_routes.query_dashboard_kpi")
@patch("mes_dashboard.routes.dashboard_routes.cache_get", return_value=None)
@patch("mes_dashboard.routes.dashboard_routes.cache_set")
def test_kpi_success_envelope(mock_set, mock_get, mock_kpi, client):
    mock_kpi.return_value = {"total": 100, "ou_pct": 75.0}
    resp = client.post("/api/dashboard/kpi", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "total" in data["data"] or "ou_pct" in data["data"]


@patch("mes_dashboard.routes.dashboard_routes.query_dashboard_kpi")
@patch("mes_dashboard.routes.dashboard_routes.cache_get", return_value=None)
def test_kpi_returns_500_when_service_returns_none(mock_get, mock_kpi, client):
    mock_kpi.return_value = None
    resp = client.post("/api/dashboard/kpi", json={})
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["success"] is False


@patch("mes_dashboard.routes.dashboard_routes.cache_get")
def test_kpi_uses_cache_hit(mock_get, client):
    mock_get.return_value = {"total": 50, "ou_pct": 80.0}
    resp = client.post("/api/dashboard/kpi", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# ── /api/dashboard/workcenter_cards ──────────────────────────────────────────

@patch("mes_dashboard.routes.dashboard_routes.query_workcenter_cards")
@patch("mes_dashboard.routes.dashboard_routes.cache_get", return_value=None)
@patch("mes_dashboard.routes.dashboard_routes.cache_set")
def test_workcenter_cards_success(mock_set, mock_get, mock_cards, client):
    mock_cards.return_value = [{"workcenter": "DB", "prd": 5}]
    resp = client.post("/api/dashboard/workcenter_cards", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


@patch("mes_dashboard.routes.dashboard_routes.query_workcenter_cards")
@patch("mes_dashboard.routes.dashboard_routes.cache_get", return_value=None)
def test_workcenter_cards_500_when_none(mock_get, mock_cards, client):
    mock_cards.return_value = None
    resp = client.post("/api/dashboard/workcenter_cards", json={})
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["success"] is False


# ── /api/dashboard/detail ─────────────────────────────────────────────────────

@patch("mes_dashboard.routes.dashboard_routes.query_resource_detail_with_job")
def test_detail_success_envelope(mock_detail, client):
    import pandas as pd
    mock_df = pd.DataFrame([{"RESOURCEID": "GW01", "STATUS": "PRD"}])
    mock_detail.return_value = (mock_df, "2026-03-31T00:00:00")
    resp = client.post("/api/dashboard/detail", json={"limit": 10, "offset": 0})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "records" in data["data"]
    assert "count" in data["data"]


@patch("mes_dashboard.routes.dashboard_routes.query_resource_detail_with_job")
def test_detail_500_when_df_is_none(mock_detail, client):
    mock_detail.return_value = (None, None)
    resp = client.post("/api/dashboard/detail", json={})
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["success"] is False


# ── /api/dashboard/ou_trend ──────────────────────────────────────────────────

@patch("mes_dashboard.routes.dashboard_routes.query_ou_trend")
@patch("mes_dashboard.routes.dashboard_routes.cache_get", return_value=None)
@patch("mes_dashboard.routes.dashboard_routes.cache_set")
def test_ou_trend_success(mock_set, mock_get, mock_trend, client):
    mock_trend.return_value = [{"date": "2026-03-01", "ou_pct": 78.0}]
    resp = client.post("/api/dashboard/ou_trend", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# ── /api/dashboard/heatmap ────────────────────────────────────────────────────

@patch("mes_dashboard.routes.dashboard_routes.query_utilization_heatmap")
@patch("mes_dashboard.routes.dashboard_routes.cache_get", return_value=None)
@patch("mes_dashboard.routes.dashboard_routes.cache_set")
def test_heatmap_success(mock_set, mock_get, mock_heatmap, client):
    mock_heatmap.return_value = {"cells": []}
    resp = client.post("/api/dashboard/utilization_heatmap", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
