# -*- coding: utf-8 -*-
"""Route tests for Yield Alert Center APIs."""

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


def test_summary_requires_date_range(client):
    response = client.get("/api/yield-alert/summary")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "start_date" in payload["error"]["message"]


def test_query_requires_dates(client):
    response = client.post("/api/yield-alert/query", json={"mode": "date_range"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "start_date" in payload["error"]["message"]


@patch("mes_dashboard.routes.yield_alert_routes.execute_primary_query")
def test_query_returns_query_id(mock_primary, client):
    mock_primary.return_value = {"query_id": "ya-001", "meta": {"cache_hit": False}}

    response = client.post(
        "/api/yield-alert/query",
        json={"start_date": "2026-03-01", "end_date": "2026-03-06"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["query_id"] == "ya-001"


def test_view_requires_query_id(client):
    response = client.get("/api/yield-alert/view")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "query_id" in payload["error"]["message"]


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_view_returns_cache_expired_when_query_missing(mock_view, client):
    mock_view.return_value = None
    response = client.get("/api/yield-alert/view?query_id=expired")
    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "CACHE_EXPIRED"


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_view_supports_workcenter_group_filters(mock_view, client):
    mock_view.return_value = {
        "summary": {"transaction_qty": 100, "scrap_qty": 1, "yield_pct": 99},
        "trend": {"items": [], "granularity": "day"},
        "alerts": {
            "items": [],
            "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 1},
            "quality": {},
            "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        },
        "meta": {"cache": {"query_id": "qid-001"}},
    }
    response = client.get(
        "/api/yield-alert/view"
        "?query_id=qid-001"
        "&workcenter_groups=%E7%84%8A%E6%8E%A5_WB"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    _, kwargs = mock_view.call_args
    assert kwargs["filters"]["workcenter_groups"] == ["焊接_WB"]
    assert "焊接_WB" in kwargs["filters"]["departments"]
    assert "焊接_DW" in kwargs["filters"]["departments"]


@patch("mes_dashboard.routes.yield_alert_routes.cache_get")
def test_summary_cache_hit_returns_meta(cache_get, client):
    cache_get.return_value = {
        "success": True,
        "data": {"transaction_qty": 100, "scrap_qty": 2, "yield_pct": 98},
        "meta": {},
    }

    response = client.get("/api/yield-alert/summary?start_date=2026-03-01&end_date=2026-03-06")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["meta"]["cache"]["hit"] is True


def test_alerts_rejects_invalid_sort_key(client):
    response = client.get(
        "/api/yield-alert/alerts"
        "?start_date=2026-03-01&end_date=2026-03-06"
        "&sort_by=bad_field"
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False


@patch("mes_dashboard.routes.yield_alert_routes.query_alert_candidates")
def test_alerts_caps_per_page_and_returns_payload(mock_query, client):
    mock_query.return_value = {
        "items": [],
        "pagination": {"page": 1, "per_page": 200, "total": 0, "total_pages": 1},
        "quality": {
            "matched": 0,
            "partially_matched": 0,
            "unmatched": 0,
            "matched_scrap_qty": 0,
            "partially_matched_scrap_qty": 0,
            "unmatched_scrap_qty": 0,
            "total_scrap_qty": 0,
            "unmatched_ratio": 0,
            "warning": False,
            "warning_code": None,
        },
        "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        "meta": {"query_latency_ms": 10},
    }

    response = client.get(
        "/api/yield-alert/alerts"
        "?start_date=2026-03-01&end_date=2026-03-06"
        "&per_page=9999"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    _, kwargs = mock_query.call_args
    assert kwargs["per_page"] == 200


@patch("mes_dashboard.routes.yield_alert_routes.query_alert_candidates")
def test_alerts_supports_workcenter_group_filters(mock_query, client):
    mock_query.return_value = {
        "items": [],
        "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 1},
        "quality": {
            "matched": 0,
            "partially_matched": 0,
            "unmatched": 0,
            "matched_scrap_qty": 0,
            "partially_matched_scrap_qty": 0,
            "unmatched_scrap_qty": 0,
            "total_scrap_qty": 0,
            "unmatched_ratio": 0,
            "warning": False,
            "warning_code": None,
        },
        "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        "meta": {"query_latency_ms": 10},
    }

    response = client.get(
        "/api/yield-alert/alerts"
        "?start_date=2026-03-01&end_date=2026-03-06"
        "&workcenter_groups=%E7%84%8A%E6%8E%A5_WB"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    _, kwargs = mock_query.call_args
    assert kwargs["filters"]["workcenter_groups"] == ["焊接_WB"]
    assert "焊接_WB" in kwargs["filters"]["departments"]
    assert "焊接_DW" in kwargs["filters"]["departments"]


@patch("mes_dashboard.routes.yield_alert_routes.get_yield_workcenter_group_options")
def test_filter_options_returns_workcenter_groups(mock_groups, client):
    mock_groups.return_value = ["焊接_DB", "焊接_WB", "成型"]

    response = client.get("/api/yield-alert/filter-options")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["workcenter_groups"] == ["焊接_DB", "焊接_WB", "成型"]


@patch("mes_dashboard.routes.yield_alert_routes.build_drilldown_payload")
def test_drilldown_context_returns_payload(mock_payload, client):
    mock_payload.return_value = {
        "match_status": "exact",
        "fallback_reason": None,
        "launch_href": "/reject-history?start_date=2026-03-06&end_date=2026-03-06",
        "filters": {"start_date": "2026-03-06", "end_date": "2026-03-06"},
        "linkage": {"canonical_key": "2026-03-06|WO|001"},
    }

    response = client.get(
        "/api/yield-alert/drilldown-context"
        "?date_bucket=2026-03-06&workorder=WO-1&reason_code=001"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["match_status"] == "exact"
