# -*- coding: utf-8 -*-
"""Tests for resource route helpers and safeguards."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


def _client():
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True
    return app.test_client()


def test_clean_nan_values_handles_deep_nesting_without_recursion_error():
    from mes_dashboard.routes.resource_routes import _clean_nan_values

    payload = current = {}
    for _ in range(2500):
        nxt = {}
        current["next"] = nxt
        current = nxt
    current["value"] = float("nan")

    cleaned = _clean_nan_values(payload)
    cursor = cleaned
    for _ in range(2500):
        cursor = cursor["next"]
    assert cursor["value"] is None


def test_clean_nan_values_breaks_cycles_safely():
    from mes_dashboard.routes.resource_routes import _clean_nan_values

    payload = {"name": "root"}
    payload["self"] = payload

    cleaned = _clean_nan_values(payload)
    assert cleaned["name"] == "root"
    assert cleaned["self"] is None


@patch(
    "mes_dashboard.routes.resource_routes.get_resource_status_summary",
    side_effect=RuntimeError("ORA-00942: table or view does not exist"),
)
def test_resource_status_summary_masks_internal_error_details(_mock_summary):
    response = _client().get("/api/resource/status/summary")
    assert response.status_code == 500

    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "服務暫時無法使用"
    assert "ORA-00942" not in str(payload)


@patch(
    "mes_dashboard.routes.resource_routes.get_merged_resource_status",
    side_effect=RuntimeError("sensitive sql context"),
)
def test_resource_status_masks_internal_error_details(_mock_status):
    response = _client().get("/api/resource/status")
    assert response.status_code == 500

    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "服務暫時無法使用"
    assert "sensitive sql context" not in str(payload)


@patch("mes_dashboard.routes.resource_routes.query_resource_detail")
def test_resource_detail_non_json_payload_returns_415(mock_query):
    response = _client().post(
        "/api/resource/detail",
        data="plain-text",
        content_type="text/plain",
    )

    assert response.status_code == 415
    payload = response.get_json()
    assert payload["success"] is False
    assert "error" in payload
    mock_query.assert_not_called()


@patch("mes_dashboard.routes.resource_routes.query_resource_detail")
def test_resource_detail_malformed_json_returns_400(mock_query):
    response = _client().post(
        "/api/resource/detail",
        data='{"filters":',
        content_type="application/json",
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "error" in payload
    mock_query.assert_not_called()


@patch("mes_dashboard.routes.resource_routes.query_resource_detail")
def test_resource_detail_rejects_limit_over_configured_max(mock_query):
    client = _client()
    client.application.config["RESOURCE_DETAIL_MAX_LIMIT"] = 100
    response = client.post(
        "/api/resource/detail",
        json={"limit": 101, "offset": 0, "filters": {}},
    )

    assert response.status_code == 413
    payload = response.get_json()
    assert payload["success"] is False
    assert "limit" in payload["error"]["message"]
    mock_query.assert_not_called()


@patch("mes_dashboard.routes.resource_routes.query_resource_detail")
def test_resource_detail_rejects_invalid_limit_type(mock_query):
    response = _client().post(
        "/api/resource/detail",
        json={"limit": "abc", "offset": 0, "filters": {}},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "limit" in payload["error"]["message"]
    mock_query.assert_not_called()


@patch("mes_dashboard.routes.resource_routes.query_resource_detail")
def test_resource_detail_rejects_negative_offset(mock_query):
    response = _client().post(
        "/api/resource/detail",
        json={"limit": 10, "offset": -1, "filters": {}},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "offset" in payload["error"]["message"]
    mock_query.assert_not_called()


# ============================================================
# Package Group Route Tests (resource-status-package-group)
# ============================================================


@patch("mes_dashboard.routes.resource_routes.get_merged_resource_status", return_value=[])
def test_resource_status_route_forwards_package_groups_kwarg(mock_service):
    """test_resource_status_forwards_package_groups_kwarg: /api/resource/status must parse
    ?package_groups= and forward package_groups kwarg to get_merged_resource_status.
    Uses a non-default value per CLAUDE.md route-forwarding discipline."""
    response = _client().get("/api/resource/status?package_groups=SOT-23")

    assert response.status_code == 200
    mock_service.assert_called_once()
    assert mock_service.call_args.kwargs['package_groups'] == ['SOT-23']


@patch("mes_dashboard.routes.resource_routes.get_merged_resource_status", return_value=[])
def test_resource_status_package_groups_non_default_value_forwarded(mock_service):
    """test_resource_status_package_groups_non_default_value_forwarded: Multiple values
    in comma-separated ?package_groups= are correctly split and forwarded."""
    response = _client().get("/api/resource/status?package_groups=SOT-23,DFN-3")

    assert response.status_code == 200
    mock_service.assert_called_once()
    assert mock_service.call_args.kwargs['package_groups'] == ['SOT-23', 'DFN-3']


@patch("mes_dashboard.routes.resource_routes.get_resource_status_summary", return_value={
    'total_count': 0, 'by_status_category': {}, 'by_status': {}, 'by_workcenter_group': {},
    'with_active_job': 0, 'with_wip': 0, 'ou_pct': 0, 'availability_pct': 0,
})
def test_resource_status_summary_route_forwards_package_groups_kwarg(mock_service):
    """test_resource_status_summary_route_forwards_package_groups_kwarg: /api/resource/status/summary
    must parse ?package_groups= and forward package_groups kwarg to get_resource_status_summary."""
    response = _client().get("/api/resource/status/summary?package_groups=SOT-23")

    assert response.status_code == 200
    mock_service.assert_called_once()
    assert mock_service.call_args.kwargs['package_groups'] == ['SOT-23']


@patch("mes_dashboard.routes.resource_routes.get_workcenter_status_matrix", return_value=[])
def test_resource_status_matrix_route_forwards_package_groups_kwarg(mock_service):
    """test_resource_status_matrix_route_forwards_package_groups_kwarg: /api/resource/status/matrix
    must parse ?package_groups= and forward package_groups kwarg to get_workcenter_status_matrix."""
    response = _client().get("/api/resource/status/matrix?package_groups=SOT-23")

    assert response.status_code == 200
    mock_service.assert_called_once()
    assert mock_service.call_args.kwargs['package_groups'] == ['SOT-23']


@patch("mes_dashboard.routes.resource_routes.get_package_groups", return_value=['DFN-3', 'SOT-23'])
@patch("mes_dashboard.routes.resource_routes.get_workcenter_groups", return_value=[])
@patch("mes_dashboard.routes.resource_routes.get_resource_families", return_value=[])
@patch("mes_dashboard.routes.resource_routes.get_resource_cascade_metadata", return_value=[])
def test_resource_status_options_returns_package_groups_field(
    mock_cascade, mock_families, mock_wc_groups, mock_pkg_groups
):
    """test_resource_filter_options_returns_package_groups_field: /api/resource/status/options
    must include 'package_groups' key in the response data object."""
    response = _client().get("/api/resource/status/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "package_groups" in payload["data"]
    assert payload["data"]["package_groups"] == ['DFN-3', 'SOT-23']
