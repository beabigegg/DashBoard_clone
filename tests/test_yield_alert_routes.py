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
        "filter_options": {
            "lines": [], "packages": [], "types": [], "functions": [],
            "workcenter_groups": ["焊接_WB_1線", "焊接_WB_2線"],
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
    # AC-5/YA-10: workcenter_groups in the /view response is spool-sourced (raw
    # DEPARTMENT_NAME values), not the global filter_cache grouped output.
    assert payload["data"]["filter_options"]["workcenter_groups"] == [
        "焊接_WB_1線", "焊接_WB_2線",
    ]


@patch("mes_dashboard.routes.yield_alert_routes.get_yield_workcenter_group_options")
@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_view_workcenter_groups_sourced_from_spool_not_filter_cache(mock_view, mock_groups, client):
    """AC-5/YA-10 regression: GET /api/yield-alert/view must NOT call
    get_yield_workcenter_group_options() (the filter_cache-backed helper) — its
    workcenter_groups value comes solely from apply_cached_view's filter_options."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 100, "scrap_qty": 1, "yield_pct": 99},
        "trend": {"items": [], "granularity": "day"},
        "alerts": {
            "items": [],
            "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 1},
            "quality": {},
            "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        },
        "filter_options": {
            "lines": [], "packages": [], "types": [], "functions": [],
            "workcenter_groups": ["切割_A線"],
        },
        "meta": {"cache": {"query_id": "qid-002"}},
    }

    response = client.get("/api/yield-alert/view?query_id=qid-002")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["filter_options"]["workcenter_groups"] == ["切割_A線"]
    assert not mock_groups.called, (
        "GET /api/yield-alert/view must not call get_yield_workcenter_group_options "
        "(filter_cache path) — workcenter_groups is spool-sourced per YA-10"
    )


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_view_new_process_type_zero_rows_returns_empty_not_error(mock_view, client):
    """AC-7/YA-12: a new process_type with zero matching spool rows must return a
    valid empty result — empty alerts array and empty workcenter_groups — not a 500."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 0, "scrap_qty": 0, "yield_pct": 0},
        "trend": {"items": [], "granularity": "day"},
        "alerts": {
            "items": [],
            "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 1},
            "quality": {},
            "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        },
        "filter_options": {
            "lines": [], "packages": [], "types": [], "functions": [], "workcenter_groups": [],
        },
        "meta": {"cache": {"query_id": "qid-zero-row"}},
    }

    response = client.get("/api/yield-alert/view?query_id=qid-zero-row")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["alerts"]["items"] == []
    assert payload["data"]["filter_options"]["workcenter_groups"] == []


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_summary_spool_path_returns_summary(mock_view, client):
    """B5: GET /api/yield-alert/summary with query_id reads from spool via apply_cached_view."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 100, "scrap_qty": 2, "yield_pct": 98},
        "trend": {"items": []},
        "alerts": {"items": [], "pagination": {}, "quality": {}, "sort": {}},
        "heatmap": {},
        "station_summary": {},
        "package_summary": {},
        "filter_options": {},
        "meta": {"view_source": "duckdb"},
    }

    response = client.get("/api/yield-alert/summary?query_id=qid-sum-001")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["transaction_qty"] == 100


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


@patch("mes_dashboard.routes.yield_alert_routes.execute_primary_query")
def test_query_spool_write_error_returns_503(mock_primary, client):
    from mes_dashboard.services.yield_alert_dataset_cache import SpoolWriteError

    mock_primary.side_effect = SpoolWriteError("spool_register_failed: Spool 註冊失敗，請稍後重試")

    response = client.post(
        "/api/yield-alert/query",
        json={"start_date": "2026-03-01", "end_date": "2026-03-06"},
    )
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers.get("Retry-After") == "30"


@patch("mes_dashboard.routes.yield_alert_routes.get_yield_workcenter_group_options")
def test_filter_options_returns_workcenter_groups(mock_groups, client):
    mock_groups.return_value = ["焊接_DB", "焊接_WB", "成型"]

    response = client.get("/api/yield-alert/filter-options")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["workcenter_groups"] == ["焊接_DB", "焊接_WB", "成型"]


def test_filter_options_still_uses_filter_cache(client):
    """AC-8/YA-11 regression guard: GET /api/yield-alert/filter-options must keep
    calling get_yield_workcenter_group_options() (-> filter_cache.get_workcenter_groups())
    unchanged. Unlike /view and /cross-filter-options, this endpoint is NOT re-pointed
    to the spool by this change."""
    with patch(
        "mes_dashboard.routes.yield_alert_routes.get_yield_workcenter_group_options"
    ) as mock_groups:
        mock_groups.return_value = ["焊接_DB", "焊接_WB"]
        response = client.get("/api/yield-alert/filter-options")

    assert response.status_code == 200
    assert mock_groups.called, (
        "GET /api/yield-alert/filter-options must still call "
        "get_yield_workcenter_group_options (filter_cache path)"
    )
    payload = response.get_json()
    assert payload["data"]["workcenter_groups"] == ["焊接_DB", "焊接_WB"]


@patch("mes_dashboard.routes.yield_alert_routes.compute_cross_filter_options")
def test_cross_filter_options_forwards_query_id_and_filters(mock_compute, client):
    mock_compute.return_value = {
        "lines": ["L1"],
        "packages": ["PKG-A"],
        "types": ["TYPE-A"],
        "functions": ["FUNC-A"],
        "workcenter_groups": ["焊接_WB_1線"],
    }

    response = client.get(
        "/api/yield-alert/cross-filter-options"
        "?query_id=qid-001"
        "&workcenter_groups=%E7%84%8A%E6%8E%A5_WB"
        "&lines=L1"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["packages"] == ["PKG-A"]
    assert payload["data"]["workcenter_groups"] == ["焊接_WB_1線"]
    mock_compute.assert_called_once()
    _, kwargs = mock_compute.call_args
    assert kwargs["query_id"] == "qid-001"
    assert kwargs["filters"]["workcenter_groups"] == ["焊接_WB"]
    assert "焊接_WB" in kwargs["filters"]["departments"]
    assert "焊接_DW" in kwargs["filters"]["departments"]
    assert kwargs["filters"]["lines"] == ["L1"]


@patch("mes_dashboard.routes.yield_alert_routes.get_yield_workcenter_group_options")
@patch("mes_dashboard.routes.yield_alert_routes.compute_cross_filter_options")
def test_cross_filter_options_workcenter_groups_from_spool(mock_compute, mock_groups, client):
    """AC-5/YA-10 regression: GET /api/yield-alert/cross-filter-options must NOT call
    get_yield_workcenter_group_options() (filter_cache path) — workcenter_groups comes
    solely from compute_cross_filter_options (spool path)."""
    mock_compute.return_value = {
        "lines": [], "packages": [], "types": [], "functions": [],
        "workcenter_groups": ["切割_A線"],
    }

    response = client.get("/api/yield-alert/cross-filter-options?query_id=qid-003")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["workcenter_groups"] == ["切割_A線"]
    assert not mock_groups.called, (
        "GET /api/yield-alert/cross-filter-options must not call "
        "get_yield_workcenter_group_options (filter_cache path)"
    )


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


class TestJobExpiry410PollingRace:
    """Polling /api/yield-alert/view after cache expiry must return 410 CACHE_EXPIRED.

    Simulates the race where a client starts polling with a query_id after
    the cached results have already expired (TTL elapsed between query and view).
    """

    def test_view_returns_410_when_cache_expired(self, client):
        """apply_cached_view returning None must produce 410 CACHE_EXPIRED envelope."""
        with patch(
            'mes_dashboard.routes.yield_alert_routes.apply_cached_view',
            return_value=None,
        ):
            rv = client.get(
                '/api/yield-alert/view',
                query_string={'query_id': 'stale-query-id-001'},
            )

        assert rv.status_code == 410
        body = rv.get_json()
        assert body['success'] is False
        assert body['error']['code'] == 'CACHE_EXPIRED'

    def test_view_410_has_envelope_meta(self, client):
        """410 CACHE_EXPIRED response must include standard meta.timestamp."""
        with patch(
            'mes_dashboard.routes.yield_alert_routes.apply_cached_view',
            return_value=None,
        ):
            rv = client.get(
                '/api/yield-alert/view',
                query_string={'query_id': 'expired-abc'},
            )

        body = rv.get_json()
        assert 'meta' in body
        assert 'timestamp' in body['meta']

    def test_view_410_polling_race_after_job_complete(self, client):
        """Simulate a polling race: job completes but cache TTL elapses before view call."""
        # Round 1: job completes, returns 200 via query
        # Round 2: view called → cache already expired → 410
        with patch(
            'mes_dashboard.routes.yield_alert_routes.apply_cached_view',
            return_value=None,
        ):
            rv1 = client.get(
                '/api/yield-alert/view',
                query_string={'query_id': 'race-condition-qid'},
            )
            rv2 = client.get(
                '/api/yield-alert/view',
                query_string={'query_id': 'race-condition-qid'},
            )

        # Both calls after expiry must consistently return 410
        assert rv1.status_code == 410
        assert rv2.status_code == 410

    def test_view_missing_query_id_returns_400_not_410(self, client):
        """Missing query_id must return 400 VALIDATION_ERROR, not 410 CACHE_EXPIRED."""
        rv = client.get('/api/yield-alert/view')
        body = rv.get_json()
        assert rv.status_code == 400
        assert body['error']['code'] == 'VALIDATION_ERROR'


# ──────────────────────────────────────────────────────────────────────────────
# yield-alert-spool-refactor: new route tests (B4, B5, B6)
# ──────────────────────────────────────────────────────────────────────────────

def test_query_requires_valid_process_type(client):
    """B4/AC-2: POST /api/yield-alert/query with invalid process_type must return
    400 VALIDATION_ERROR. Covers a clearly-invalid value and a near-miss (`G%`) that
    must still 400 under the expanded 6-value enum (GA%/GC%/GD%/F%/W%/D%)."""
    for bad_value in ("INVALID", "G%"):
        response = client.post(
            "/api/yield-alert/query",
            json={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "process_type": bad_value,
            },
        )
        assert response.status_code == 400, f"process_type={bad_value!r} must 400"
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("process_type", ["GA%", "GC%", "GD%", "F%", "W%", "D%"])
@patch("mes_dashboard.routes.yield_alert_routes.execute_primary_query")
def test_query_accepts_each_new_process_type(mock_primary, client, process_type):
    """AC-2: each of the 6 accepted process_type values is forwarded to
    execute_primary_query and returns 200 (not 400)."""
    mock_primary.return_value = {"query_id": f"ya-{process_type}", "meta": {"cache_hit": False}}

    response = client.post(
        "/api/yield-alert/query",
        json={
            "start_date": "2026-02-01",
            "end_date": "2026-02-28",
            "process_type": process_type,
        },
    )
    assert response.status_code == 200, f"process_type={process_type!r} must be accepted"
    payload = response.get_json()
    assert payload["success"] is True
    call_kwargs = mock_primary.call_args.kwargs
    assert call_kwargs.get("process_type") == process_type


@patch("mes_dashboard.routes.yield_alert_routes.execute_primary_query")
def test_query_defaults_process_type_to_ga(mock_primary, client):
    """B4: POST /api/yield-alert/query without process_type must default to 'GA%'."""
    mock_primary.return_value = {"query_id": "ya-ga-default", "meta": {"cache_hit": False}}

    response = client.post(
        "/api/yield-alert/query",
        json={"start_date": "2026-02-01", "end_date": "2026-02-28"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    # process_type must have been forwarded as 'GA%'
    assert mock_primary.called
    call_kwargs = mock_primary.call_args.kwargs
    assert call_kwargs.get("process_type") == "GA%"


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_trend_endpoint_uses_spool_not_oracle(mock_view, client):
    """B5: GET /api/yield-alert/trend must NOT call Oracle; uses apply_cached_view (spool path).

    query_yield_trend is no longer imported in the routes module after B5 — this test
    confirms the trend endpoint routes through apply_cached_view, not a live Oracle call.
    """
    import mes_dashboard.services.yield_alert_service as svc
    oracle_called = {"called": False}
    real_trend = svc.query_yield_trend

    def _spy_trend(*args, **kwargs):
        oracle_called["called"] = True
        return real_trend(*args, **kwargs)

    mock_view.return_value = {
        "summary": {},
        "trend": {"items": []},
        "alerts": {"items": [], "pagination": {}, "quality": {}, "sort": {}},
        "heatmap": {},
        "station_summary": {},
        "package_summary": {},
        "filter_options": {},
        "meta": {"view_source": "duckdb"},
    }
    response = client.get("/api/yield-alert/trend?query_id=spool-qid-001")
    # apply_cached_view is the spool path — it must have been called
    assert mock_view.called, "Trend endpoint must call apply_cached_view (spool path)"
    # Oracle function is NOT called by the route (it's not even imported)
    assert not oracle_called["called"], (
        "Trend endpoint must NOT call Oracle query_yield_trend after spool refactor"
    )


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_alerts_response_includes_source_code_field(mock_view, client):
    """B6: GET /api/yield-alert/view alerts items must include a 'source_code' key."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 1000, "scrap_qty": 5, "yield_pct": 99.5},
        "trend": {"items": []},
        "alerts": {
            "items": [
                {
                    "date_bucket": "2026-02-21",
                    "workorder": "GA-WO-001",
                    "reason_code": "031",
                    "source_code": "LOT-ABC",
                    "scrap_qty": 5.0,
                    "transaction_qty": 100.0,
                    "yield_pct": 95.0,
                    "risk_level": "low",
                    "risk_score": 3.0,
                }
            ],
            "pagination": {"page": 1, "per_page": 50, "total": 1, "total_pages": 1},
            "quality": {},
            "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        },
        "heatmap": {},
        "station_summary": {},
        "package_summary": {},
        "filter_options": {},
        "meta": {"view_source": "duckdb"},
    }

    response = client.get("/api/yield-alert/view?query_id=qid-src-001")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    items = payload["data"]["alerts"]["items"]
    assert len(items) >= 1
    assert "source_code" in items[0], (
        "Alert items must include 'source_code' field after spool-refactor B6"
    )


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_summary_route_forwards_risk_threshold_and_min_scrap_qty(mock_view, client):
    """AC-3/YA-13: GET /api/yield-alert/summary must forward risk_threshold and
    min_scrap_qty into apply_cached_view (previously dropped -> defaults only),
    so /view and /summary return identical KPI numbers for the same query."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 1000, "scrap_qty": 15, "yield_pct": 98.5},
        "trend": {"items": []},
        "alerts": {"items": [], "pagination": {}, "quality": {}, "sort": {}},
        "heatmap": {},
        "station_summary": {},
        "package_summary": {},
        "filter_options": {},
        "meta": {"view_source": "duckdb"},
    }

    response = client.get(
        "/api/yield-alert/summary"
        "?query_id=qid-threshold-001&risk_threshold=95.5&min_scrap_qty=3.5"
    )

    assert response.status_code == 200
    _, kwargs = mock_view.call_args
    assert kwargs["risk_threshold"] == 95.5, (
        "risk_threshold must be parsed from request.args and forwarded, not dropped"
    )
    assert kwargs["min_scrap_qty"] == 3.5, (
        "min_scrap_qty must be parsed from request.args and forwarded, not dropped"
    )


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_summary_route_uses_default_thresholds_when_absent(mock_view, client):
    """When risk_threshold/min_scrap_qty are absent from the query string, the
    /summary route must forward the same defaults as /view (98 / 1)."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 1000, "scrap_qty": 15, "yield_pct": 98.5},
        "trend": {"items": []},
        "alerts": {"items": [], "pagination": {}, "quality": {}, "sort": {}},
        "heatmap": {},
        "station_summary": {},
        "package_summary": {},
        "filter_options": {},
        "meta": {"view_source": "duckdb"},
    }

    response = client.get("/api/yield-alert/summary?query_id=qid-threshold-002")

    assert response.status_code == 200
    _, kwargs = mock_view.call_args
    assert kwargs["risk_threshold"] == 98.0
    assert kwargs["min_scrap_qty"] == 1.0


@patch("mes_dashboard.routes.yield_alert_routes.apply_cached_view")
def test_view_and_summary_response_shape_unchanged_after_scope_unification(mock_view, client):
    """AC-7: GET /view and GET /summary response envelopes keep their existing
    shape after the KPI rescoping fix — only summary numeric values/semantics
    change, not the response schema."""
    mock_view.return_value = {
        "summary": {"transaction_qty": 1000.0, "scrap_qty": 15.0, "yield_pct": 98.5},
        "trend": {"items": [], "granularity": "day"},
        "alerts": {
            "items": [],
            "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 1},
            "quality": {},
            "sort": {"sort_by": "date_bucket", "sort_dir": "desc"},
        },
        "heatmap": {"items": []},
        "station_summary": {"items": []},
        "package_summary": {"items": []},
        "filter_options": {
            "lines": [], "packages": [], "types": [], "functions": [], "workcenter_groups": [],
        },
        "meta": {"cache": {"query_id": "qid-shape-001"}},
    }

    view_response = client.get("/api/yield-alert/view?query_id=qid-shape-001")
    assert view_response.status_code == 200
    view_payload = view_response.get_json()
    assert set(view_payload["data"]["summary"].keys()) == {
        "transaction_qty", "scrap_qty", "yield_pct",
    }

    summary_response = client.get("/api/yield-alert/summary?query_id=qid-shape-001")
    assert summary_response.status_code == 200
    summary_payload = summary_response.get_json()
    assert set(summary_payload["data"].keys()) == {
        "transaction_qty", "scrap_qty", "yield_pct",
    }
    assert summary_payload["data"] == view_payload["data"]["summary"]
