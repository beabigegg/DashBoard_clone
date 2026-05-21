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

    # resource_cache functions that are imported locally inside query_resource_filter_options
    _RC = 'mes_dashboard.services.resource_cache'
    # get_package_groups is imported at module level into resource_service — patch there
    _RS = 'mes_dashboard.services.resource_service'

    def test_statuses_come_from_constant(self):
        """statuses in filter options are from STATUS_CATEGORIES constant, no Oracle query."""
        from mes_dashboard.services.resource_service import query_resource_filter_options
        from mes_dashboard.config.constants import STATUS_CATEGORIES

        with patch(f'{self._RC}.get_workcenters', return_value=['WC-01']):
            with patch(f'{self._RC}.get_resource_families', return_value=['F1']):
                with patch(f'{self._RC}.get_departments', return_value=['D1']):
                    with patch(f'{self._RC}.get_locations', return_value=['L1']):
                        with patch(f'{self._RC}.get_distinct_values', return_value=['Active']):
                            with patch(f'{self._RS}.get_package_groups', return_value=['SOT-23']):
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
                            with patch(f'{self._RS}.get_package_groups', return_value=[]):
                                with patch('mes_dashboard.services.resource_service.read_sql_df') as mock_sql:
                                    result = query_resource_filter_options()

        mock_sql.assert_not_called()
        assert result is not None

    def test_returns_package_groups_list(self):
        """test_returns_package_groups_list: query_resource_filter_options() includes
        'package_groups' key with a list of package group name strings.

        Note: get_package_groups is imported at module level into resource_service, so
        we patch it at the resource_service namespace (not resource_cache).
        """
        from mes_dashboard.services.resource_service import query_resource_filter_options

        with patch(f'{self._RC}.get_workcenters', return_value=[]):
            with patch(f'{self._RC}.get_resource_families', return_value=[]):
                with patch(f'{self._RC}.get_departments', return_value=[]):
                    with patch(f'{self._RC}.get_locations', return_value=[]):
                        with patch(f'{self._RC}.get_distinct_values', return_value=[]):
                            with patch(f'{self._RS}.get_package_groups', return_value=['DFN-3', 'SOT-23']) as mock_pg:
                                result = query_resource_filter_options()

        assert result is not None
        assert 'package_groups' in result
        assert result['package_groups'] == ['DFN-3', 'SOT-23']
        mock_pg.assert_called_once()

    def test_package_groups_excludes_null_entries(self):
        """test_package_groups_excludes_null_entries: get_package_groups() (which powers
        query_resource_filter_options) returns only non-null strings (None values are never
        added to the lookup dict during _load_package_group_lookup)."""
        from mes_dashboard.services.resource_service import query_resource_filter_options

        # Simulate get_package_groups already filtered (no nulls from lookup dict)
        with patch(f'{self._RC}.get_workcenters', return_value=[]):
            with patch(f'{self._RC}.get_resource_families', return_value=[]):
                with patch(f'{self._RC}.get_departments', return_value=[]):
                    with patch(f'{self._RC}.get_locations', return_value=[]):
                        with patch(f'{self._RC}.get_distinct_values', return_value=[]):
                            with patch(f'{self._RS}.get_package_groups', return_value=['SOT-23']):
                                result = query_resource_filter_options()

        assert result is not None
        for pg in result['package_groups']:
            assert pg is not None


class TestGetMergedResourceStatusPackageGroup:
    """Tests for PACKAGEGROUPNAME resolution and package_groups filter in
    get_merged_resource_status (AC-1, AC-5)."""

    def _base_resource(self, pgid=None, resource_id='R001', family='FamilyA'):
        return {
            'RESOURCEID': resource_id,
            'RESOURCENAME': 'Machine1',
            'WORKCENTERNAME': 'WC-01',
            'RESOURCEFAMILYNAME': family,
            'PJ_DEPARTMENT': 'Dept1',
            'PJ_ASSETSSTATUS': 'Active',
            'PJ_ISPRODUCTION': 1,
            'PJ_ISKEY': 0,
            'PJ_ISMONITOR': 0,
            'VENDORNAME': 'Vendor1',
            'VENDORMODEL': 'Model1',
            'LOCATIONNAME': 'Loc1',
            'PACKAGEGROUPID': pgid,
        }

    def _patches(self, resources, get_pkg_name_side_effect=None):
        """Return a context manager stack for common patches."""
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch(
            'mes_dashboard.services.resource_service.get_all_resources',
            return_value=resources,
        ))
        stack.enter_context(patch(
            'mes_dashboard.services.resource_service.get_equipment_status_lookup',
            return_value={},
        ))
        stack.enter_context(patch(
            'mes_dashboard.services.resource_service.get_all_equipment_status',
            return_value=[],
        ))
        stack.enter_context(patch(
            'mes_dashboard.services.resource_service.get_workcenter_group',
            return_value=None,
        ))
        stack.enter_context(patch(
            'mes_dashboard.services.resource_service.get_workcenter_group_sequence',
            return_value=None,
        ))
        stack.enter_context(patch(
            'mes_dashboard.services.resource_service.get_workcenter_short',
            return_value=None,
        ))
        if get_pkg_name_side_effect is not None:
            stack.enter_context(patch(
                'mes_dashboard.services.resource_service.get_package_group_name',
                side_effect=get_pkg_name_side_effect,
            ))
        else:
            stack.enter_context(patch(
                'mes_dashboard.services.resource_service.get_package_group_name',
                return_value=None,
            ))
        return stack

    def test_get_merged_resource_status_packagegroupname_resolved(self):
        """test_packagegroupname_added_when_packagegroupid_present: When PACKAGEGROUPID is set
        and lookup resolves it, PACKAGEGROUPNAME is present in the record with the resolved value."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [self._base_resource(pgid='P01')]

        with self._patches(resources, get_pkg_name_side_effect=lambda pgid: 'SOT-23' if pgid == 'P01' else None):
            result = get_merged_resource_status()

        assert len(result) == 1
        assert result[0]['PACKAGEGROUPNAME'] == 'SOT-23'

    def test_get_merged_resource_status_packagegroupname_null_when_id_null(self):
        """test_packagegroupname_is_none_when_packagegroupid_null: When PACKAGEGROUPID is None
        (91% case), PACKAGEGROUPNAME must be None in the merged record."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [self._base_resource(pgid=None)]

        with self._patches(resources, get_pkg_name_side_effect=lambda pgid: None):
            result = get_merged_resource_status()

        assert len(result) == 1
        assert result[0]['PACKAGEGROUPNAME'] is None

    def test_get_merged_resource_status_packagegroupname_null_when_dict_miss(self):
        """When PACKAGEGROUPID has a value but lookup dict has no entry, PACKAGEGROUPNAME is None."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [self._base_resource(pgid='P99')]

        with self._patches(resources, get_pkg_name_side_effect=lambda pgid: None):
            result = get_merged_resource_status()

        assert len(result) == 1
        assert result[0]['PACKAGEGROUPNAME'] is None

    def test_get_merged_resource_status_package_groups_filter_excludes(self):
        """test_package_groups_filter_warm_cache_path: Passing package_groups=['SOT-23'] keeps
        only records whose PACKAGEGROUPNAME matches; others are excluded."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [
            self._base_resource(pgid='P01', resource_id='R001'),
            self._base_resource(pgid='P02', resource_id='R002'),
        ]

        def _resolve(pgid):
            return {'P01': 'SOT-23', 'P02': 'DFN-3'}.get(pgid)

        with self._patches(resources, get_pkg_name_side_effect=_resolve):
            result = get_merged_resource_status(package_groups=['SOT-23'])

        assert len(result) == 1
        assert result[0]['RESOURCEID'] == 'R001'
        assert result[0]['PACKAGEGROUPNAME'] == 'SOT-23'

    def test_get_merged_resource_status_package_groups_filter_excludes_null(self):
        """Records with PACKAGEGROUPNAME=None are excluded when package_groups filter is active."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [
            self._base_resource(pgid='P01', resource_id='R001'),
            self._base_resource(pgid=None, resource_id='R002'),
        ]

        def _resolve(pgid):
            return 'SOT-23' if pgid == 'P01' else None

        with self._patches(resources, get_pkg_name_side_effect=_resolve):
            result = get_merged_resource_status(package_groups=['SOT-23'])

        assert len(result) == 1
        assert result[0]['RESOURCEID'] == 'R001'

    def test_package_groups_filter_warm_cache_path(self):
        """Integration: package_groups filter applies on the warm-cache path (get_all_resources
        returns cached records). Two resources, only one matches the filter."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [
            self._base_resource(pgid='P01', resource_id='R001', family='FamilyA'),
            self._base_resource(pgid='P02', resource_id='R002', family='FamilyB'),
        ]

        def _resolve(pgid):
            return {'P01': 'SOT-23', 'P02': 'SOT-89'}.get(pgid)

        with self._patches(resources, get_pkg_name_side_effect=_resolve):
            result = get_merged_resource_status(package_groups=['SOT-23'])

        resource_ids = [r['RESOURCEID'] for r in result]
        assert 'R001' in resource_ids
        assert 'R002' not in resource_ids

    def test_package_groups_filter_oracle_fallback_path(self):
        """Integration: package_groups filter applies on Oracle-fallback path.
        Simulate get_all_resources returning records from Oracle (same code path)."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        # Oracle fallback still goes through get_all_resources — same code path applies
        resources = [
            self._base_resource(pgid='P01', resource_id='R001'),
            self._base_resource(pgid='P02', resource_id='R002'),
        ]

        def _resolve(pgid):
            return {'P01': 'SOT-23', 'P02': 'DFN-3'}.get(pgid)

        with self._patches(resources, get_pkg_name_side_effect=_resolve):
            result = get_merged_resource_status(package_groups=['DFN-3'])

        assert len(result) == 1
        assert result[0]['RESOURCEID'] == 'R002'
        assert result[0]['PACKAGEGROUPNAME'] == 'DFN-3'

    def test_package_groups_empty_list_returns_all_resources(self):
        """An empty package_groups list (not None) must not filter anything."""
        from mes_dashboard.services.resource_service import get_merged_resource_status

        resources = [
            self._base_resource(pgid='P01', resource_id='R001'),
            self._base_resource(pgid=None, resource_id='R002'),
        ]

        def _resolve(pgid):
            return 'SOT-23' if pgid == 'P01' else None

        with self._patches(resources, get_pkg_name_side_effect=_resolve):
            # Empty list is falsy → same as None → no filtering
            result = get_merged_resource_status(package_groups=[])

        assert len(result) == 2
