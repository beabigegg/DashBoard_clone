# -*- coding: utf-8 -*-
"""Tests for mes_dashboard.services.equipment_lookup_service."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.services.equipment_lookup_service as els


_MODULE = "mes_dashboard.services.equipment_lookup_service"


def _resource(
    name,
    location="LOC-A",
    family="FAM-A",
    vendor="V1",
    vendor_model="M1",
    workcenter="WC1",
):
    return {
        "RESOURCENAME": name,
        "LOCATIONNAME": location,
        "RESOURCEFAMILYNAME": family,
        "VENDORNAME": vendor,
        "VENDORMODEL": vendor_model,
        "WORKCENTERNAME": workcenter,
    }


# ============================================================
# get_equipment_lookup_options
# ============================================================


@patch(f"{_MODULE}.get_distinct_values")
def test_options_shape_and_source_columns(mock_distinct):
    mock_distinct.side_effect = lambda column: {
        "LOCATIONNAME": ["LOC-A", "LOC-B"],
        "RESOURCEFAMILYNAME": ["FAM-A"],
        "RESOURCENAME": ["EQP-001", "EQP-002"],
    }[column]

    result = els.get_equipment_lookup_options()

    assert result["locations"] == ["LOC-A", "LOC-B"]
    assert result["families"] == ["FAM-A"]
    assert result["resource_names"] == ["EQP-001", "EQP-002"]
    assert mock_distinct.call_args_list[0].args[0] == "LOCATIONNAME"
    assert mock_distinct.call_args_list[1].args[0] == "RESOURCEFAMILYNAME"
    assert mock_distinct.call_args_list[2].args[0] == "RESOURCENAME"


# ============================================================
# get_equipment_lookup_list — default pagination
# ============================================================


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_default_pagination(mock_filter):
    mock_filter.return_value = [_resource(f"EQP-{i:03d}") for i in range(5)]

    result = els.get_equipment_lookup_list()

    assert result["pagination"]["page"] == 1
    assert result["pagination"]["page_size"] == 20
    assert result["pagination"]["total"] == 5
    assert result["pagination"]["total_pages"] == 1
    assert len(result["rows"]) == 5
    # Default sort_by=RESOURCENAME, sort_dir=asc
    assert [r["RESOURCENAME"] for r in result["rows"]] == [
        "EQP-000", "EQP-001", "EQP-002", "EQP-003", "EQP-004",
    ]
    # Row shape includes all display fields.
    row = result["rows"][0]
    assert set(row.keys()) == {
        "RESOURCENAME", "LOCATIONNAME", "RESOURCEFAMILYNAME",
        "VENDORNAME", "VENDORMODEL", "WORKCENTERNAME",
    }


# ============================================================
# Filtering — each axis independently, including empty-while-sibling-populated
# ============================================================


@patch(f"{_MODULE}.get_resources_by_filter", return_value=[])
def test_list_forwards_locations_only_families_empty(mock_filter):
    """locations populated, families/resource_names empty — families must forward as None."""
    els.get_equipment_lookup_list(locations=["LOC-A"], families=None, resource_names=None)

    mock_filter.assert_called_once()
    assert mock_filter.call_args.kwargs["locations"] == ["LOC-A"]
    assert mock_filter.call_args.kwargs["families"] is None


@patch(f"{_MODULE}.get_resources_by_filter", return_value=[])
def test_list_forwards_families_only_locations_empty(mock_filter):
    """families populated, locations empty — locations must forward as None."""
    els.get_equipment_lookup_list(locations=None, families=["FAM-A"], resource_names=None)

    mock_filter.assert_called_once()
    assert mock_filter.call_args.kwargs["families"] == ["FAM-A"]
    assert mock_filter.call_args.kwargs["locations"] is None


@patch(f"{_MODULE}.get_resources_by_filter", return_value=[])
def test_list_empty_list_filters_forward_as_none(mock_filter):
    """Empty lists (not just None) for locations/families must also forward as None."""
    els.get_equipment_lookup_list(locations=[], families=[], resource_names=None)

    mock_filter.assert_called_once()
    assert mock_filter.call_args.kwargs["locations"] is None
    assert mock_filter.call_args.kwargs["families"] is None


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_filters_by_resource_names_only_python_membership(mock_filter):
    """resource_names populated, locations/families empty — get_resources_by_filter
    itself has no resource_names param; filtering must happen in Python on top."""
    mock_filter.return_value = [
        _resource("EQP-001"), _resource("EQP-002"), _resource("EQP-003"),
    ]

    result = els.get_equipment_lookup_list(
        locations=None, families=None, resource_names=["EQP-002"],
    )

    assert mock_filter.call_args.kwargs["locations"] is None
    assert mock_filter.call_args.kwargs["families"] is None
    assert "resource_names" not in mock_filter.call_args.kwargs
    assert [r["RESOURCENAME"] for r in result["rows"]] == ["EQP-002"]
    assert result["pagination"]["total"] == 1


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_combines_all_three_filter_axes(mock_filter):
    mock_filter.return_value = [
        _resource("EQP-001", location="LOC-A", family="FAM-A"),
        _resource("EQP-002", location="LOC-A", family="FAM-A"),
    ]

    result = els.get_equipment_lookup_list(
        locations=["LOC-A"], families=["FAM-A"], resource_names=["EQP-001"],
    )

    assert mock_filter.call_args.kwargs["locations"] == ["LOC-A"]
    assert mock_filter.call_args.kwargs["families"] == ["FAM-A"]
    assert [r["RESOURCENAME"] for r in result["rows"]] == ["EQP-001"]


# ============================================================
# Empty-result case
# ============================================================


@patch(f"{_MODULE}.get_resources_by_filter", return_value=[])
def test_list_empty_result(mock_filter):
    result = els.get_equipment_lookup_list(locations=["LOC-NONE"])

    assert result["rows"] == []
    assert result["pagination"]["total"] == 0
    assert result["pagination"]["total_pages"] == 1


# ============================================================
# Sorting — both directions
# ============================================================


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_sort_asc(mock_filter):
    mock_filter.return_value = [_resource("EQP-003"), _resource("EQP-001"), _resource("EQP-002")]

    result = els.get_equipment_lookup_list(sort_by="RESOURCENAME", sort_dir="asc")

    assert [r["RESOURCENAME"] for r in result["rows"]] == ["EQP-001", "EQP-002", "EQP-003"]


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_sort_desc(mock_filter):
    mock_filter.return_value = [_resource("EQP-003"), _resource("EQP-001"), _resource("EQP-002")]

    result = els.get_equipment_lookup_list(sort_by="RESOURCENAME", sort_dir="desc")

    assert [r["RESOURCENAME"] for r in result["rows"]] == ["EQP-003", "EQP-002", "EQP-001"]


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_sort_by_location_asc(mock_filter):
    mock_filter.return_value = [
        _resource("EQP-001", location="LOC-C"),
        _resource("EQP-002", location="LOC-A"),
        _resource("EQP-003", location="LOC-B"),
    ]

    result = els.get_equipment_lookup_list(sort_by="LOCATIONNAME", sort_dir="asc")

    assert [r["LOCATIONNAME"] for r in result["rows"]] == ["LOC-A", "LOC-B", "LOC-C"]


# ============================================================
# Pagination — page/page_size slicing
# ============================================================


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_pagination_second_page(mock_filter):
    mock_filter.return_value = [_resource(f"EQP-{i:03d}") for i in range(25)]

    result = els.get_equipment_lookup_list(page=2, page_size=10)

    assert result["pagination"]["page"] == 2
    assert result["pagination"]["page_size"] == 10
    assert result["pagination"]["total"] == 25
    assert result["pagination"]["total_pages"] == 3
    assert [r["RESOURCENAME"] for r in result["rows"]] == [
        f"EQP-{i:03d}" for i in range(10, 20)
    ]


@patch(f"{_MODULE}.get_resources_by_filter")
def test_list_pagination_large_page_size_for_export(mock_filter):
    mock_filter.return_value = [_resource(f"EQP-{i:03d}") for i in range(25)]

    result = els.get_equipment_lookup_list(page=1, page_size=10000)

    assert result["pagination"]["total_pages"] == 1
    assert len(result["rows"]) == 25
