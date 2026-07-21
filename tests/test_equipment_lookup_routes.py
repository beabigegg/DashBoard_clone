# -*- coding: utf-8 -*-
"""Tests for mes_dashboard.routes.equipment_lookup_routes."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


def _client():
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True
    return app.test_client()


_ROUTES = "mes_dashboard.routes.equipment_lookup_routes"


# ============================================================
# /api/equipment-lookup/options
# ============================================================


@patch(f"{_ROUTES}.get_equipment_lookup_options")
def test_options_endpoint_shape(mock_options):
    mock_options.return_value = {
        "locations": ["LOC-A", "LOC-B"],
        "families": ["FAM-A"],
        "resource_names": ["EQP-001"],
    }

    response = _client().get("/api/equipment-lookup/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["locations"] == ["LOC-A", "LOC-B"]
    assert payload["data"]["families"] == ["FAM-A"]
    assert payload["data"]["resource_names"] == ["EQP-001"]


@patch(f"{_ROUTES}.get_equipment_lookup_options", side_effect=RuntimeError("boom"))
def test_options_endpoint_masks_internal_error_details(mock_options):
    response = _client().get("/api/equipment-lookup/options")

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" not in str(payload)


# ============================================================
# /api/equipment-lookup/list — defaults + pagination shape
# ============================================================


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_endpoint_default_pagination_forwarded(mock_list):
    mock_list.return_value = {
        "rows": [],
        "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1},
    }

    response = _client().get("/api/equipment-lookup/list")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["pagination"]["page"] == 1
    assert payload["data"]["pagination"]["page_size"] == 20

    mock_list.assert_called_once()
    assert mock_list.call_args.kwargs["page"] == 1
    assert mock_list.call_args.kwargs["page_size"] == 20
    assert mock_list.call_args.kwargs["sort_by"] == "RESOURCENAME"
    assert mock_list.call_args.kwargs["sort_dir"] == "asc"
    assert mock_list.call_args.kwargs["locations"] is None
    assert mock_list.call_args.kwargs["families"] is None
    assert mock_list.call_args.kwargs["resource_names"] is None


# ============================================================
# Filtering — each axis independently, incl. empty-while-sibling-populated
# ============================================================


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_forwards_locations_only(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?locations=LOC-A,LOC-B")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["locations"] == ["LOC-A", "LOC-B"]
    assert mock_list.call_args.kwargs["families"] is None
    assert mock_list.call_args.kwargs["resource_names"] is None


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_forwards_families_only(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?families=FAM-A")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["families"] == ["FAM-A"]
    assert mock_list.call_args.kwargs["locations"] is None
    assert mock_list.call_args.kwargs["resource_names"] is None


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_forwards_resource_names_only(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?resource_names=EQP-001,EQP-002")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["resource_names"] == ["EQP-001", "EQP-002"]
    assert mock_list.call_args.kwargs["locations"] is None
    assert mock_list.call_args.kwargs["families"] is None


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_supports_repeated_query_param_form(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?locations=LOC-A&locations=LOC-B")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["locations"] == ["LOC-A", "LOC-B"]


# ============================================================
# Empty-result case (service returns no rows)
# ============================================================


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_empty_result_response_shape(mock_list):
    mock_list.return_value = {
        "rows": [],
        "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1},
    }

    response = _client().get("/api/equipment-lookup/list?locations=NO-MATCH")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["rows"] == []
    assert payload["data"]["pagination"]["total"] == 0


# ============================================================
# Sort direction forwarding — both directions
# ============================================================


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_forwards_sort_dir_asc(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?sort_by=LOCATIONNAME&sort_dir=asc")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["sort_by"] == "LOCATIONNAME"
    assert mock_list.call_args.kwargs["sort_dir"] == "asc"


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_forwards_sort_dir_desc(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?sort_by=RESOURCEFAMILYNAME&sort_dir=desc")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["sort_by"] == "RESOURCEFAMILYNAME"
    assert mock_list.call_args.kwargs["sort_dir"] == "desc"


# ============================================================
# Validation at the boundary
# ============================================================


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_rejects_invalid_sort_by(mock_list):
    response = _client().get("/api/equipment-lookup/list?sort_by=NOT_A_COLUMN")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    mock_list.assert_not_called()


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_rejects_invalid_sort_dir(mock_list):
    response = _client().get("/api/equipment-lookup/list?sort_dir=sideways")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    mock_list.assert_not_called()


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_rejects_page_size_over_max(mock_list):
    response = _client().get("/api/equipment-lookup/list?page_size=10001")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    mock_list.assert_not_called()


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_allows_page_size_at_max_for_export(mock_list):
    mock_list.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 10000, "total": 0, "total_pages": 1}}

    response = _client().get("/api/equipment-lookup/list?page_size=10000")

    assert response.status_code == 200
    assert mock_list.call_args.kwargs["page_size"] == 10000


@patch(f"{_ROUTES}.get_equipment_lookup_list")
def test_list_rejects_invalid_page(mock_list):
    response = _client().get("/api/equipment-lookup/list?page=0")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    mock_list.assert_not_called()


@patch(f"{_ROUTES}.get_equipment_lookup_list", side_effect=RuntimeError("sensitive sql context"))
def test_list_endpoint_masks_internal_error_details(mock_list):
    response = _client().get("/api/equipment-lookup/list")

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "sensitive sql context" not in str(payload)
