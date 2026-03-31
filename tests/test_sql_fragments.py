# -*- coding: utf-8 -*-
"""Unit tests for sql_fragments.py — shared SQL constants and templates."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services.sql_fragments import (
    RESOURCE_TABLE,
    RESOURCE_BASE_SELECT_TEMPLATE,
    RESOURCE_VERSION_SELECT_TEMPLATE,
    EQUIPMENT_STATUS_VIEW,
    EQUIPMENT_STATUS_COLUMNS,
    EQUIPMENT_STATUS_SELECT_SQL,
)


class TestResourceTableConstant:
    def test_resource_table_name(self):
        assert RESOURCE_TABLE == "DWH.DW_MES_RESOURCE"

    def test_base_select_template_contains_table(self):
        assert RESOURCE_TABLE in RESOURCE_BASE_SELECT_TEMPLATE

    def test_base_select_template_has_where_placeholder(self):
        assert "{{ WHERE_CLAUSE }}" in RESOURCE_BASE_SELECT_TEMPLATE

    def test_version_select_template_has_max_lastchangedate(self):
        assert "MAX(LASTCHANGEDATE)" in RESOURCE_VERSION_SELECT_TEMPLATE

    def test_version_select_template_has_where_placeholder(self):
        assert "{{ WHERE_CLAUSE }}" in RESOURCE_VERSION_SELECT_TEMPLATE

    def test_version_select_template_aliases_as_version(self):
        assert "VERSION" in RESOURCE_VERSION_SELECT_TEMPLATE


class TestEquipmentStatusFragment:
    def test_equipment_status_view_name(self):
        assert EQUIPMENT_STATUS_VIEW == "DWH.DW_MES_EQUIPMENTSTATUS_WIP_V"

    def test_equipment_status_columns_is_tuple(self):
        assert isinstance(EQUIPMENT_STATUS_COLUMNS, tuple)

    def test_equipment_status_columns_has_expected_keys(self):
        required = {"RESOURCEID", "EQUIPMENTID", "OBJECTCATEGORY"}
        assert required.issubset(set(EQUIPMENT_STATUS_COLUMNS))

    def test_equipment_status_select_sql_contains_view(self):
        assert EQUIPMENT_STATUS_VIEW in EQUIPMENT_STATUS_SELECT_SQL

    def test_equipment_status_select_sql_starts_with_select(self):
        assert EQUIPMENT_STATUS_SELECT_SQL.strip().upper().startswith("SELECT")

    def test_equipment_status_select_sql_contains_all_columns(self):
        for col in EQUIPMENT_STATUS_COLUMNS:
            assert col in EQUIPMENT_STATUS_SELECT_SQL
