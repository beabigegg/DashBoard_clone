# -*- coding: utf-8 -*-
"""Unit tests for resource_service module.

Tests merged resource status queries and summary functions.
"""

from unittest.mock import patch


class TestGetMergedResourceStatus:
    """Test get_merged_resource_status function."""

    def test_returns_empty_when_no_resources(self):
        """Test returns empty list when no resources available."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=[]):
            result = get_merged_resource_status()
            assert result == []

    def test_merges_resource_and_status_data(self):
        """Test merges resource-cache and realtime-equipment-cache data."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources = [
            {
                'RESOURCEID': 'R001',
                'RESOURCENAME': 'Machine1',
                'WORKCENTERNAME': 'WC-01',
                'RESOURCEFAMILYNAME': 'Family1',
                'PJ_DEPARTMENT': 'Dept1',
                'PJ_ASSETSSTATUS': 'Active',
                'PJ_ISPRODUCTION': 1,
                'PJ_ISKEY': 0,
                'PJ_ISMONITOR': 0,
                'VENDORNAME': 'Vendor1',
                'VENDORMODEL': 'Model1',
                'LOCATIONNAME': 'Loc1',
            }
        ]

        mock_equipment_status = [
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'STATUS_CATEGORY': 'PRODUCTIVE',
                'JOBORDER': 'JO001',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOT_COUNT': 2,
                'TOTAL_TRACKIN_QTY': 150,
                'LATEST_TRACKIN_TIME': '2024-01-15T10:00:00',
            }
        ]

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value='焊接'):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value='DB'):
                        result = get_merged_resource_status()

                        assert len(result) == 1
                        r = result[0]
                        # Resource-cache data
                        assert r['RESOURCEID'] == 'R001'
                        assert r['RESOURCENAME'] == 'Machine1'
                        assert r['WORKCENTERNAME'] == 'WC-01'
                        # Workcenter mapping
                        assert r['WORKCENTER_GROUP'] == '焊接'
                        assert r['WORKCENTER_SHORT'] == 'DB'
                        # Realtime status
                        assert r['EQUIPMENTASSETSSTATUS'] == 'PRD'
                        assert r['STATUS_CATEGORY'] == 'PRODUCTIVE'
                        assert r['LOT_COUNT'] == 2

    def test_handles_resources_without_status(self):
        """Test handles resources that have no realtime status."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources = [
            {
                'RESOURCEID': 'R001',
                'RESOURCENAME': 'Machine1',
                'WORKCENTERNAME': 'WC-01',
                'RESOURCEFAMILYNAME': 'Family1',
                'PJ_DEPARTMENT': 'Dept1',
                'PJ_ASSETSSTATUS': 'Active',
                'PJ_ISPRODUCTION': 1,
                'PJ_ISKEY': 0,
                'PJ_ISMONITOR': 0,
                'VENDORNAME': 'Vendor1',
                'VENDORMODEL': 'Model1',
                'LOCATIONNAME': 'Loc1',
            }
        ]

        # No matching equipment status
        mock_equipment_status = []

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value=None):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        result = get_merged_resource_status()

                        assert len(result) == 1
                        r = result[0]
                        assert r['RESOURCEID'] == 'R001'
                        # Status fields should be None
                        assert r['EQUIPMENTASSETSSTATUS'] is None
                        assert r['STATUS_CATEGORY'] is None
                        assert r['LOT_COUNT'] is None


class TestGetMergedResourceStatusWithFilters:
    """Test get_merged_resource_status with filter parameters."""

    def _get_mock_data(self):
        """Get mock test data."""
        mock_resources = [
            {
                'RESOURCEID': 'R001',
                'RESOURCENAME': 'Machine1',
                'WORKCENTERNAME': 'WC-01',
                'RESOURCEFAMILYNAME': 'Family1',
                'PJ_DEPARTMENT': 'Dept1',
                'PJ_ASSETSSTATUS': 'Active',
                'PJ_ISPRODUCTION': 1,
                'PJ_ISKEY': 1,
                'PJ_ISMONITOR': 0,
                'VENDORNAME': 'Vendor1',
                'VENDORMODEL': 'Model1',
                'LOCATIONNAME': 'Loc1',
            },
            {
                'RESOURCEID': 'R002',
                'RESOURCENAME': 'Machine2',
                'WORKCENTERNAME': 'WC-02',
                'RESOURCEFAMILYNAME': 'Family2',
                'PJ_DEPARTMENT': 'Dept2',
                'PJ_ASSETSSTATUS': 'Active',
                'PJ_ISPRODUCTION': 0,
                'PJ_ISKEY': 0,
                'PJ_ISMONITOR': 1,
                'VENDORNAME': 'Vendor2',
                'VENDORMODEL': 'Model2',
                'LOCATIONNAME': 'Loc2',
            },
        ]

        mock_equipment_status = [
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'STATUS_CATEGORY': 'PRODUCTIVE',
                'JOBORDER': 'JO001',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOT_COUNT': 1,
                'TOTAL_TRACKIN_QTY': 100,
                'LATEST_TRACKIN_TIME': '2024-01-15T10:00:00',
            },
            {
                'RESOURCEID': 'R002',
                'EQUIPMENTASSETSSTATUS': 'SBY',
                'EQUIPMENTASSETSSTATUSREASON': 'Waiting',
                'STATUS_CATEGORY': 'STANDBY',
                'JOBORDER': None,
                'JOBSTATUS': None,
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOT_COUNT': 0,
                'TOTAL_TRACKIN_QTY': 0,
                'LATEST_TRACKIN_TIME': None,
            },
        ]

        return mock_resources, mock_equipment_status

    def test_filters_by_workcenter_groups(self):
        """Test filters by workcenter_groups parameter."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources, mock_equipment_status = self._get_mock_data()

        def mock_get_group(wc_name):
            return '焊接' if wc_name == 'WC-01' else '成型'

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', side_effect=mock_get_group):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        result = get_merged_resource_status(workcenter_groups=['焊接'])

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R001'

    def test_filters_by_is_production(self):
        """Test filters by is_production parameter."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources, mock_equipment_status = self._get_mock_data()

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value=None):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        result = get_merged_resource_status(is_production=True)

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R001'

    def test_filters_by_is_key(self):
        """Test filters by is_key parameter."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources, mock_equipment_status = self._get_mock_data()

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value=None):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        result = get_merged_resource_status(is_key=True)

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R001'

    def test_filters_by_is_monitor(self):
        """Test filters by is_monitor parameter."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources, mock_equipment_status = self._get_mock_data()

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value=None):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        result = get_merged_resource_status(is_monitor=True)

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R002'

    def test_filters_by_status_categories(self):
        """Test filters by status_categories parameter."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources, mock_equipment_status = self._get_mock_data()

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value=None):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        result = get_merged_resource_status(status_categories=['PRODUCTIVE'])

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R001'
                        assert result[0]['STATUS_CATEGORY'] == 'PRODUCTIVE'

    def test_combines_multiple_filters(self):
        """Test combines multiple filter criteria."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        mock_resources, mock_equipment_status = self._get_mock_data()

        with patch('mes_dashboard.services.resource_service.get_all_resources', return_value=mock_resources):
            with patch('mes_dashboard.services.resource_service.get_all_equipment_status', return_value=mock_equipment_status):
                with patch('mes_dashboard.services.resource_service.get_workcenter_group', return_value=None):
                    with patch('mes_dashboard.services.resource_service.get_workcenter_short', return_value=None):
                        # Filter: production AND key
                        result = get_merged_resource_status(is_production=True, is_key=True)

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R001'


class TestGetResourceStatusSummary:
    """Test get_resource_status_summary function."""

    def test_returns_empty_summary_when_no_data(self):
        """Test returns empty summary when no data."""
        from mes_dashboard.services.resource_service import get_resource_status_summary

        with patch('mes_dashboard.services.resource_service.get_merged_resource_status', return_value=[]):
            result = get_resource_status_summary()

            assert result['total_count'] == 0
            assert result['by_status_category'] == {}
            assert result['by_workcenter_group'] == {}

    def test_calculates_summary_statistics(self):
        """Test calculates correct summary statistics."""
        from mes_dashboard.services.resource_service import get_resource_status_summary

        mock_data = [
            {
                'RESOURCEID': 'R001',
                'STATUS_CATEGORY': 'PRODUCTIVE',
                'WORKCENTER_GROUP': '焊接',
                'JOBORDER': 'JO001',
                'LOT_COUNT': 2,
            },
            {
                'RESOURCEID': 'R002',
                'STATUS_CATEGORY': 'PRODUCTIVE',
                'WORKCENTER_GROUP': '焊接',
                'JOBORDER': 'JO002',
                'LOT_COUNT': 1,
            },
            {
                'RESOURCEID': 'R003',
                'STATUS_CATEGORY': 'STANDBY',
                'WORKCENTER_GROUP': '成型',
                'JOBORDER': None,
                'LOT_COUNT': 0,
            },
        ]

        with patch('mes_dashboard.services.resource_service.get_merged_resource_status', return_value=mock_data):
            result = get_resource_status_summary()

            assert result['total_count'] == 3
            assert result['by_status_category']['PRODUCTIVE'] == 2
            assert result['by_status_category']['STANDBY'] == 1
            assert result['by_workcenter_group']['焊接'] == 2
            assert result['by_workcenter_group']['成型'] == 1
            assert result['with_active_job'] == 2
            assert result['with_wip'] == 2


class TestGetWorkcenterStatusMatrix:
    """Test get_workcenter_status_matrix function."""

    def test_returns_empty_when_no_data(self):
        """Test returns empty list when no data."""
        from mes_dashboard.services.resource_service import get_workcenter_status_matrix

        with patch('mes_dashboard.services.resource_service.get_merged_resource_status', return_value=[]):
            result = get_workcenter_status_matrix()
            assert result == []

    def test_builds_matrix_by_workcenter_and_status(self):
        """Test builds matrix by workcenter group and status."""
        from mes_dashboard.services.resource_service import get_workcenter_status_matrix

        mock_data = [
            {'WORKCENTER_GROUP': '焊接', 'EQUIPMENTASSETSSTATUS': 'PRD'},
            {'WORKCENTER_GROUP': '焊接', 'EQUIPMENTASSETSSTATUS': 'PRD'},
            {'WORKCENTER_GROUP': '焊接', 'EQUIPMENTASSETSSTATUS': 'SBY'},
            {'WORKCENTER_GROUP': '成型', 'EQUIPMENTASSETSSTATUS': 'UDT'},
        ]

        mock_groups = [
            {'name': '焊接', 'sequence': 1},
            {'name': '成型', 'sequence': 2},
        ]

        with patch('mes_dashboard.services.resource_service.get_merged_resource_status', return_value=mock_data):
            with patch('mes_dashboard.services.resource_service.get_workcenter_groups', return_value=mock_groups):
                result = get_workcenter_status_matrix()

                assert len(result) == 2

                # Should be sorted by sequence
                assert result[0]['workcenter_group'] == '焊接'
                assert result[0]['total'] == 3
                assert result[0]['PRD'] == 2
                assert result[0]['SBY'] == 1

                assert result[1]['workcenter_group'] == '成型'
                assert result[1]['total'] == 1
                assert result[1]['UDT'] == 1

    def test_handles_unknown_status(self):
        """Test handles unknown status codes."""
        from mes_dashboard.services.resource_service import get_workcenter_status_matrix

        mock_data = [
            {'WORKCENTER_GROUP': '焊接', 'EQUIPMENTASSETSSTATUS': 'CUSTOM_STATUS'},
        ]

        mock_groups = [{'name': '焊接', 'sequence': 1}]

        with patch('mes_dashboard.services.resource_service.get_merged_resource_status', return_value=mock_data):
            with patch('mes_dashboard.services.resource_service.get_workcenter_groups', return_value=mock_groups):
                result = get_workcenter_status_matrix()

                assert len(result) == 1
                assert result[0]['OTHER'] == 1


class TestQueryResourceFilterOptions:
    """Tests for query_resource_filter_options using STATUS_CATEGORIES constant."""

    # resource_cache functions are imported locally inside query_resource_filter_options
    _RC = 'mes_dashboard.services.resource_cache'

    def test_statuses_come_from_constant(self):
        """statuses in filter options are from STATUS_CATEGORIES constant, no Oracle query."""
        from mes_dashboard.services.resource_service import query_resource_filter_options
        from mes_dashboard.config.constants import STATUS_CATEGORIES

        with patch(f'{self._RC}.get_workcenters', return_value=['WC-01']):
            with patch(f'{self._RC}.get_resource_families', return_value=['F1']):
                with patch(f'{self._RC}.get_departments', return_value=['D1']):
                    with patch(f'{self._RC}.get_locations', return_value=['L1']):
                        with patch(f'{self._RC}.get_distinct_values', return_value=['Active']):
                            result = query_resource_filter_options()

        assert result is not None
        assert result['statuses'] == list(STATUS_CATEGORIES)
        assert 'workcenters' in result

    def test_no_read_sql_df_call_for_statuses(self):
        """query_resource_filter_options does not call read_sql_df for statuses."""
        from mes_dashboard.services.resource_service import query_resource_filter_options

        with patch(f'{self._RC}.get_workcenters', return_value=[]):
            with patch(f'{self._RC}.get_resource_families', return_value=[]):
                with patch(f'{self._RC}.get_departments', return_value=[]):
                    with patch(f'{self._RC}.get_locations', return_value=[]):
                        with patch(f'{self._RC}.get_distinct_values', return_value=[]):
                            with patch('mes_dashboard.services.resource_service.read_sql_df') as mock_sql:
                                result = query_resource_filter_options()

        mock_sql.assert_not_called()
        assert result is not None
