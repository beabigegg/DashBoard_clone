# -*- coding: utf-8 -*-
"""Unit tests for resource_cache module.

Tests cache read/write functionality, fallback mechanism, and distinct values API.
"""

import pytest
import time
from unittest.mock import patch, MagicMock
import pandas as pd
import json


class TestPackageGroupLookup:
    """Tests for package-group lookup dict (IP-1..IP-5 acceptance criteria AC-5/AC-6)."""

    def _reset_pkg_state(self, rc):
        """Reset module-level package-group state before each test."""
        rc._package_group_lookup = {}
        rc._package_group_refreshed_at = 0.0

    def test_package_group_lookup_dict_build(self):
        """test_builds_lookup_dict_from_oracle_rows: _load_package_group_lookup builds
        {str(PACKAGEGROUPID).strip(): PACKAGEGROUPNAME} from read_sql_df rows."""
        import mes_dashboard.services.resource_cache as rc
        self._reset_pkg_state(rc)

        mock_df = pd.DataFrame([
            {'PACKAGEGROUPID': 'P01', 'PACKAGEGROUPNAME': 'SOT-23'},
            {'PACKAGEGROUPID': 'P02', 'PACKAGEGROUPNAME': 'SOT-89'},
        ])

        with patch.object(rc, 'read_sql_df', return_value=mock_df):
            rc._load_package_group_lookup()

        assert rc._package_group_lookup.get('P01') == 'SOT-23'
        assert rc._package_group_lookup.get('P02') == 'SOT-89'
        assert rc._package_group_refreshed_at > 0.0

    def test_package_group_lookup_dict_ttl_independent(self):
        """test_lookup_ttl_is_7_days_independent_of_resource_cache: _package_group_refreshed_at
        is a separate timestamp from the 24h resource_cache refresh timer.
        After _load_package_group_lookup() completes, the module-level
        _package_group_refreshed_at must be set and _PACKAGE_GROUP_SYNC_INTERVAL must be 604800.
        """
        import mes_dashboard.services.resource_cache as rc
        self._reset_pkg_state(rc)

        assert rc._PACKAGE_GROUP_SYNC_INTERVAL == 604_800  # 7 days in seconds

        mock_df = pd.DataFrame([
            {'PACKAGEGROUPID': 'P01', 'PACKAGEGROUPNAME': 'SOT-23'},
        ])

        before = time.time()
        with patch.object(rc, 'read_sql_df', return_value=mock_df):
            rc._load_package_group_lookup()

        # Timer was updated independently
        assert rc._package_group_refreshed_at >= before
        # It is NOT the same object as any other cache timer (just verify it's a float attr)
        assert isinstance(rc._package_group_refreshed_at, float)

    def test_package_group_lookup_char_key_normalization(self):
        """test_char_key_trailing_space_stripped_on_build: Oracle CHAR columns pad to fixed
        width with trailing spaces. Build must strip so lookup key is clean."""
        import mes_dashboard.services.resource_cache as rc
        self._reset_pkg_state(rc)

        mock_df = pd.DataFrame([
            {'PACKAGEGROUPID': 'P01   ', 'PACKAGEGROUPNAME': 'SOT-23'},
        ])

        with patch.object(rc, 'read_sql_df', return_value=mock_df):
            rc._load_package_group_lookup()

        # Key must be stripped — 'P01' resolves but 'P01   ' does not
        assert 'P01' in rc._package_group_lookup
        assert 'P01   ' not in rc._package_group_lookup

    def test_get_package_groups_returns_sorted_list(self):
        """get_package_groups() returns sorted distinct PACKAGEGROUPNAME values."""
        import mes_dashboard.services.resource_cache as rc
        self._reset_pkg_state(rc)

        rc._package_group_lookup = {'P01': 'SOT-23', 'P02': 'DFN-3', 'P03': 'SOT-89'}
        # Pre-set refreshed_at to avoid TTL reload during test
        rc._package_group_refreshed_at = time.time()

        result = rc.get_package_groups()

        assert result == sorted(['SOT-23', 'DFN-3', 'SOT-89'])

    def test_package_group_lookup_null_pgid_returns_none(self):
        """test_null_packagegroupid_resolves_to_none (data-boundary): get_package_group_name(None)
        must return None without triggering a lookup error."""
        import mes_dashboard.services.resource_cache as rc
        self._reset_pkg_state(rc)
        rc._package_group_refreshed_at = time.time()  # avoid TTL reload

        result = rc.get_package_group_name(None)

        assert result is None

    def test_package_group_lookup_char_trailing_space(self):
        """test_char_key_trailing_space_stripped_on_resolve (data-boundary): A PACKAGEGROUPID
        value arriving with trailing spaces (Oracle CHAR) must still resolve correctly."""
        import mes_dashboard.services.resource_cache as rc
        self._reset_pkg_state(rc)

        # Dict built with clean key
        rc._package_group_lookup = {'P01': 'SOT-23'}
        rc._package_group_refreshed_at = time.time()

        # PGID arriving with trailing space should resolve via .strip()
        result = rc.get_package_group_name('P01   ')

        assert result == 'SOT-23'


class TestGetDistinctValues:
    """Test get_distinct_values function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_returns_sorted_unique_values(self):
        """Test returns sorted unique values from resources."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'WORKCENTERNAME': 'Station_B', 'RESOURCEFAMILYNAME': 'Family1'},
            {'WORKCENTERNAME': 'Station_A', 'RESOURCEFAMILYNAME': 'Family2'},
            {'WORKCENTERNAME': 'Station_B', 'RESOURCEFAMILYNAME': 'Family1'},  # duplicate
            {'WORKCENTERNAME': 'Station_C', 'RESOURCEFAMILYNAME': None},  # None value
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_distinct_values('WORKCENTERNAME')

            assert result == ['Station_A', 'Station_B', 'Station_C']

    def test_excludes_none_and_empty_strings(self):
        """Test excludes None and empty string values."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEFAMILYNAME': 'Family1'},
            {'RESOURCEFAMILYNAME': None},
            {'RESOURCEFAMILYNAME': ''},
            {'RESOURCEFAMILYNAME': 'Family2'},
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_distinct_values('RESOURCEFAMILYNAME')

            assert result == ['Family1', 'Family2']

    def test_handles_nan_values(self):
        """Test handles NaN values (pandas float NaN)."""
        import mes_dashboard.services.resource_cache as rc
        import numpy as np

        mock_resources = [
            {'WORKCENTERNAME': 'Station_A'},
            {'WORKCENTERNAME': float('nan')},  # NaN
            {'WORKCENTERNAME': np.nan},  # NumPy NaN
            {'WORKCENTERNAME': 'Station_B'},
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_distinct_values('WORKCENTERNAME')

            assert result == ['Station_A', 'Station_B']

    def test_handles_mixed_types(self):
        """Test handles mixed types (converts to string)."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'PJ_DEPARTMENT': 'Dept_A'},
            {'PJ_DEPARTMENT': 123},  # int
            {'PJ_DEPARTMENT': 'Dept_B'},
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_distinct_values('PJ_DEPARTMENT')

            assert '123' in result
            assert 'Dept_A' in result
            assert 'Dept_B' in result

    def test_returns_empty_list_when_no_resources(self):
        """Test returns empty list when no resources."""
        import mes_dashboard.services.resource_cache as rc

        with patch.object(rc, 'get_all_resources', return_value=[]):
            result = rc.get_distinct_values('WORKCENTERNAME')

            assert result == []


class TestConvenienceMethods:
    """Test convenience methods for common columns."""

    def test_get_resource_families_calls_get_distinct_values(self):
        """Test get_resource_families calls get_distinct_values with correct column."""
        import mes_dashboard.services.resource_cache as rc

        with patch.object(rc, 'get_distinct_values', return_value=['Family1', 'Family2']) as mock:
            result = rc.get_resource_families()

            mock.assert_called_once_with('RESOURCEFAMILYNAME')
            assert result == ['Family1', 'Family2']

    def test_get_workcenters_calls_get_distinct_values(self):
        """Test get_workcenters calls get_distinct_values with correct column."""
        import mes_dashboard.services.resource_cache as rc

        with patch.object(rc, 'get_distinct_values', return_value=['WC1', 'WC2']) as mock:
            result = rc.get_workcenters()

            mock.assert_called_once_with('WORKCENTERNAME')
            assert result == ['WC1', 'WC2']

    def test_get_departments_calls_get_distinct_values(self):
        """Test get_departments calls get_distinct_values with correct column."""
        import mes_dashboard.services.resource_cache as rc

        with patch.object(rc, 'get_distinct_values', return_value=['Dept1', 'Dept2']) as mock:
            result = rc.get_departments()

            mock.assert_called_once_with('PJ_DEPARTMENT')
            assert result == ['Dept1', 'Dept2']


class TestGetAllResources:
    """Test get_all_resources function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_returns_cached_data_when_available(self):
        """Test returns cached data from Redis when available."""
        import mes_dashboard.services.resource_cache as rc

        test_data = [
            {'RESOURCEID': 'R001', 'RESOURCENAME': 'Machine1'},
            {'RESOURCEID': 'R002', 'RESOURCENAME': 'Machine2'}
        ]
        cached_json = json.dumps(test_data)

        mock_client = MagicMock()
        mock_client.get.return_value = cached_json

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'get_redis_client', return_value=mock_client):
                    result = rc.get_all_resources()

                    assert len(result) == 2
                    assert result[0]['RESOURCEID'] == 'R001'

    def test_falls_back_to_oracle_when_cache_miss(self):
        """Test falls back to Oracle when cache is empty."""
        import mes_dashboard.services.resource_cache as rc

        mock_client = MagicMock()
        mock_client.get.return_value = None

        oracle_df = pd.DataFrame({
            'RESOURCEID': ['R001'],
            'RESOURCENAME': ['Machine1']
        })

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'get_redis_client', return_value=mock_client):
                    with patch.object(rc, '_load_from_oracle', return_value=oracle_df):
                        result = rc.get_all_resources()

                        assert len(result) == 1
                        assert result[0]['RESOURCEID'] == 'R001'

    def test_returns_empty_when_both_unavailable(self):
        """Test returns empty list when both cache and Oracle fail."""
        import mes_dashboard.services.resource_cache as rc

        mock_client = MagicMock()
        mock_client.get.return_value = None

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'get_redis_client', return_value=mock_client):
                    with patch.object(rc, '_load_from_oracle', return_value=None):
                        result = rc.get_all_resources()

                        assert result == []


class TestGetResourceById:
    """Test get_resource_by_id function."""

    def test_returns_matching_resource(self):
        """Test returns resource with matching ID."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'RESOURCENAME': 'Machine1'},
            {'RESOURCEID': 'R002', 'RESOURCENAME': 'Machine2'}
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_resource_by_id('R002')

            assert result is not None
            assert result['RESOURCEID'] == 'R002'
            assert result['RESOURCENAME'] == 'Machine2'

    def test_returns_none_when_not_found(self):
        """Test returns None when ID not found."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'RESOURCENAME': 'Machine1'}
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_resource_by_id('R999')

            assert result is None


class TestGetResourcesByIds:
    """Test get_resources_by_ids function."""

    def test_returns_matching_resources(self):
        """Test returns all resources with matching IDs."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'RESOURCENAME': 'Machine1'},
            {'RESOURCEID': 'R002', 'RESOURCENAME': 'Machine2'},
            {'RESOURCEID': 'R003', 'RESOURCENAME': 'Machine3'}
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_resources_by_ids(['R001', 'R003'])

            assert len(result) == 2
            ids = [r['RESOURCEID'] for r in result]
            assert 'R001' in ids
            assert 'R003' in ids

    def test_ignores_missing_ids(self):
        """Test ignores IDs that don't exist."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'RESOURCENAME': 'Machine1'}
        ]

        with patch.object(rc, 'get_all_resources', return_value=mock_resources):
            result = rc.get_resources_by_ids(['R001', 'R999'])

            assert len(result) == 1
            assert result[0]['RESOURCEID'] == 'R001'


class TestGetResourcesByFilter:
    """Test get_resources_by_filter function."""

    @staticmethod
    def _legacy_snapshot():
        # Force legacy/filter-from-records path so these unit tests remain
        # independent from shared in-process resource index state.
        return {"ready": False}

    def test_filters_by_workcenter(self):
        """Test filters resources by workcenter."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'WORKCENTERNAME': 'WC1'},
            {'RESOURCEID': 'R002', 'WORKCENTERNAME': 'WC2'},
            {'RESOURCEID': 'R003', 'WORKCENTERNAME': 'WC1'}
        ]

        with patch.object(rc, 'get_resource_index_snapshot', return_value=self._legacy_snapshot()):
            with patch.object(rc, 'get_all_resources', return_value=mock_resources):
                result = rc.get_resources_by_filter(workcenters=['WC1'])

                assert len(result) == 2

    def test_filters_by_family(self):
        """Test filters resources by family."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'RESOURCEFAMILYNAME': 'F1'},
            {'RESOURCEID': 'R002', 'RESOURCEFAMILYNAME': 'F2'}
        ]

        with patch.object(rc, 'get_resource_index_snapshot', return_value=self._legacy_snapshot()):
            with patch.object(rc, 'get_all_resources', return_value=mock_resources):
                result = rc.get_resources_by_filter(families=['F1'])

                assert len(result) == 1
                assert result[0]['RESOURCEFAMILYNAME'] == 'F1'

    def test_filters_by_production_flag(self):
        """Test filters resources by production flag."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'PJ_ISPRODUCTION': 1},
            {'RESOURCEID': 'R002', 'PJ_ISPRODUCTION': 0},
            {'RESOURCEID': 'R003', 'PJ_ISPRODUCTION': 1}
        ]

        with patch.object(rc, 'get_resource_index_snapshot', return_value=self._legacy_snapshot()):
            with patch.object(rc, 'get_all_resources', return_value=mock_resources):
                result = rc.get_resources_by_filter(is_production=True)

                assert len(result) == 2

    def test_combines_multiple_filters(self):
        """Test combines multiple filter criteria."""
        import mes_dashboard.services.resource_cache as rc

        mock_resources = [
            {'RESOURCEID': 'R001', 'WORKCENTERNAME': 'WC1', 'RESOURCEFAMILYNAME': 'F1'},
            {'RESOURCEID': 'R002', 'WORKCENTERNAME': 'WC1', 'RESOURCEFAMILYNAME': 'F2'},
            {'RESOURCEID': 'R003', 'WORKCENTERNAME': 'WC2', 'RESOURCEFAMILYNAME': 'F1'}
        ]

        with patch.object(rc, 'get_resource_index_snapshot', return_value=self._legacy_snapshot()):
            with patch.object(rc, 'get_all_resources', return_value=mock_resources):
                result = rc.get_resources_by_filter(workcenters=['WC1'], families=['F1'])

                assert len(result) == 1
                assert result[0]['RESOURCEID'] == 'R001'


class TestGetCacheStatus:
    """Test get_cache_status function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_returns_disabled_when_cache_disabled(self):
        """Test returns disabled status when cache is disabled."""
        import mes_dashboard.services.resource_cache as rc

        with patch.object(rc, 'REDIS_ENABLED', False):
            result = rc.get_cache_status()

            assert result['enabled'] is False
            assert result['loaded'] is False

    def test_returns_loaded_status_when_data_exists(self):
        """Test returns loaded status when cache has data."""
        import mes_dashboard.services.resource_cache as rc

        mock_client = MagicMock()
        mock_client.exists.return_value = 1
        mock_client.get.side_effect = lambda key: {
            'mes_wip:resource:meta:count': '1000',
            'mes_wip:resource:meta:version': '2024-01-15T10:00:00',
            'mes_wip:resource:meta:updated': '2024-01-15T10:30:00',
        }.get(key)

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'get_redis_client', return_value=mock_client):
                    result = rc.get_cache_status()

                    assert result['enabled'] is True
                    assert result['loaded'] is True


class TestRefreshCache:
    """Test refresh_cache function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_returns_false_when_disabled(self):
        """Test returns False when cache is disabled."""
        import mes_dashboard.services.resource_cache as rc

        with patch.object(rc, 'REDIS_ENABLED', False):
            result = rc.refresh_cache()

            assert result is False

    def test_skips_sync_when_version_unchanged(self):
        """Test skips sync when Oracle version matches Redis version."""
        import mes_dashboard.services.resource_cache as rc

        mock_client = MagicMock()
        mock_client.get.return_value = '2024-01-15T10:00:00'
        mock_client.ping.return_value = True

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'redis_available', return_value=True):
                    with patch.object(rc, '_get_version_from_oracle', return_value='2024-01-15T10:00:00'):
                        with patch.object(rc, '_get_version_from_redis', return_value='2024-01-15T10:00:00'):
                            result = rc.refresh_cache(force=False)

                            assert result is False

    def test_syncs_when_version_changed(self):
        """Test syncs when Oracle version differs from Redis version."""
        import mes_dashboard.services.resource_cache as rc

        mock_df = pd.DataFrame({
            'RESOURCEID': ['R001'],
            'RESOURCENAME': ['Machine1']
        })

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'redis_available', return_value=True):
                    with patch.object(rc, '_get_version_from_oracle', return_value='2024-01-15T11:00:00'):
                        with patch.object(rc, '_get_version_from_redis', return_value='2024-01-15T10:00:00'):
                            with patch.object(rc, '_load_from_oracle', return_value=mock_df):
                                with patch.object(rc, '_sync_to_redis', return_value=True) as mock_sync:
                                    result = rc.refresh_cache(force=False)

                                    assert result is True
                                    mock_sync.assert_called_once()

    def test_force_sync_ignores_version(self):
        """Test force sync ignores version comparison."""
        import mes_dashboard.services.resource_cache as rc

        mock_df = pd.DataFrame({
            'RESOURCEID': ['R001'],
            'RESOURCENAME': ['Machine1']
        })

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'RESOURCE_CACHE_ENABLED', True):
                with patch.object(rc, 'redis_available', return_value=True):
                    with patch.object(rc, '_get_version_from_oracle', return_value='2024-01-15T10:00:00'):
                        with patch.object(rc, '_get_version_from_redis', return_value='2024-01-15T10:00:00'):
                            with patch.object(rc, '_load_from_oracle', return_value=mock_df):
                                with patch.object(rc, '_sync_to_redis', return_value=True) as mock_sync:
                                    result = rc.refresh_cache(force=True)

                                    assert result is True
                                    mock_sync.assert_called_once()


class TestBuildFilterBuilder:
    """Test _build_filter_builder function."""

    def test_includes_equipment_type_filter(self):
        """Test includes equipment type filter."""
        import mes_dashboard.services.resource_cache as rc

        builder = rc._build_filter_builder()
        builder.base_sql = "SELECT * FROM DWH.DW_MES_RESOURCE {{ WHERE_CLAUSE }}"
        sql, params = builder.build()

        assert 'OBJECTCATEGORY' in sql
        assert 'ASSEMBLY' in sql or 'WAFERSORT' in sql

    def test_includes_location_filter(self):
        """Test includes location exclusion filter with parameterization."""
        import mes_dashboard.services.resource_cache as rc

        builder = rc._build_filter_builder()
        builder.base_sql = "SELECT * FROM DWH.DW_MES_RESOURCE {{ WHERE_CLAUSE }}"
        sql, params = builder.build()

        # Check SQL contains LOCATIONNAME condition
        assert 'LOCATIONNAME' in sql
        # Parameterized query should have bind variables
        assert len(params) > 0

    def test_includes_asset_status_filter(self):
        """Test includes asset status exclusion filter with parameterization."""
        import mes_dashboard.services.resource_cache as rc

        builder = rc._build_filter_builder()
        builder.base_sql = "SELECT * FROM DWH.DW_MES_RESOURCE {{ WHERE_CLAUSE }}"
        sql, params = builder.build()

        # Check SQL contains PJ_ASSETSSTATUS condition
        assert 'PJ_ASSETSSTATUS' in sql
        # Parameterized query should have bind variables
        assert len(params) > 0

    def test_resource_load_uses_shared_sql_fragment_template(self):
        """Test resource load path uses shared SQL fragment template."""
        import mes_dashboard.services.resource_cache as rc
        from mes_dashboard.services.sql_fragments import RESOURCE_TABLE

        with patch.object(rc, "read_sql_df", return_value=pd.DataFrame()) as mock_read:
            rc._load_from_oracle()

        sql = mock_read.call_args[0][0]
        assert RESOURCE_TABLE in sql

    def test_resource_version_sql_replaces_where_clause_placeholder(self):
        """Version SQL should not leak placeholder token into Oracle."""
        import mes_dashboard.services.resource_cache as rc
        from mes_dashboard.services.sql_fragments import RESOURCE_TABLE

        with patch.object(
            rc,
            "read_sql_df",
            return_value=pd.DataFrame([{"VERSION": "2026-02-09T12:00:00"}]),
        ) as mock_read:
            rc._get_version_from_oracle()

        sql = mock_read.call_args[0][0]
        assert RESOURCE_TABLE in sql
        assert "{{ WHERE_CLAUSE }}" not in sql
        assert "{ WHERE_CLAUSE }" not in sql
        assert "WHERE " in sql


class TestResourceDerivedIndex:
    """Test derived resource index and telemetry behavior."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        import mes_dashboard.services.resource_cache as rc
        rc._resource_index = rc._new_empty_index()
        rc._resource_df_cache.invalidate("resource_data")
        yield
        rc._resource_index = rc._new_empty_index()
        rc._resource_df_cache.invalidate("resource_data")

    def test_get_resource_by_id_uses_index_snapshot(self):
        import mes_dashboard.services.resource_cache as rc

        cache_df = pd.DataFrame([{"RESOURCEID": "R001", "RESOURCENAME": "Machine1"}])
        rc._resource_df_cache.set(rc.RESOURCE_DF_CACHE_KEY, cache_df)
        snapshot = {
            "ready": True,
            "all_positions": [0],
            "by_resource_id": {"R001": 0},
        }
        with patch.object(rc, "get_resource_index_snapshot", return_value=snapshot):
            row = rc.get_resource_by_id("R001")
            assert row is not None
            assert row["RESOURCENAME"] == "Machine1"

    def test_get_cache_status_includes_derived_index_freshness(self):
        import mes_dashboard.services.resource_cache as rc

        rc._resource_index = {
            **rc._new_empty_index(),
            "ready": True,
            "source": "redis",
            "version": "v1",
            "updated_at": "2026-02-07T10:00:00",
            "built_at": "2026-02-07T10:00:05",
            "count": 2,
        }

        mock_client = MagicMock()
        mock_client.exists.return_value = 1
        mock_client.get.side_effect = lambda key: {
            'mes_wip:resource:meta:count': '2',
            'mes_wip:resource:meta:version': 'v1',
            'mes_wip:resource:meta:updated': '2026-02-07T10:00:00',
        }.get(key)

        with patch.object(rc, "REDIS_ENABLED", True):
            with patch.object(rc, "RESOURCE_CACHE_ENABLED", True):
                with patch.object(rc, "get_redis_client", return_value=mock_client):
                    status = rc.get_cache_status()
                    assert status["derived_index"]["ready"] is True
                    assert status["derived_index"]["is_fresh"] is True

    def test_index_rebuilds_when_redis_version_changes(self):
        import mes_dashboard.services.resource_cache as rc

        rc._resource_index = {
            **rc._new_empty_index(),
            "ready": True,
            "source": "redis",
            "version": "v1",
            "updated_at": "2026-02-07T10:00:00",
            "built_at": "2026-02-07T10:00:05",
            "version_checked_at": 0.0,
            "count": 1,
            "all_positions": [0],
            "by_resource_id": {"OLD": 0},
        }

        rebuilt_df = pd.DataFrame([
            {"RESOURCEID": "R002", "RESOURCENAME": "Machine2"}
        ])

        with patch.object(rc, "RESOURCE_INDEX_VERSION_CHECK_INTERVAL", 0):
            with patch.object(rc, "_get_version_from_redis", return_value="v2"):
                with patch.object(rc, "_get_cached_data", return_value=rebuilt_df):
                    with patch.object(rc, "_get_cache_meta", return_value=("v2", "2026-02-07T10:10:00")):
                        snapshot = rc.get_resource_index_snapshot()
                        assert snapshot["version"] == "v2"
                        assert snapshot["count"] == 1
                        assert snapshot["by_resource_id"]["R002"] == 0
                        records = rc.get_all_resources()
                        assert records[0]["RESOURCENAME"] == "Machine2"

    def test_normalized_index_does_not_store_full_records_copy(self):
        import mes_dashboard.services.resource_cache as rc

        df = pd.DataFrame([
            {"RESOURCEID": "R001", "WORKCENTERNAME": "WC1", "PJ_ISPRODUCTION": 1},
            {"RESOURCEID": "R002", "WORKCENTERNAME": "WC2", "PJ_ISPRODUCTION": 0},
        ])

        index = rc._build_resource_index(df, source="redis", version="v1", updated_at="2026-02-08T00:00:00")
        assert "records" not in index
        assert index["by_resource_id"]["R001"] == 0
        assert index["by_resource_id"]["R002"] == 1
        assert index["memory"]["index_bytes"] > 0
        assert index["memory"]["records_json_bytes"] == 0


class TestResourceProcessLevelCache:
    """Test bounded process-level cache for resource data."""

    def test_lru_eviction_prefers_recent_keys(self):
        import mes_dashboard.services.resource_cache as rc

        cache = rc._ProcessLevelCache(ttl_seconds=60, max_size=2)
        df1 = pd.DataFrame([{"RESOURCEID": "R001"}])
        df2 = pd.DataFrame([{"RESOURCEID": "R002"}])
        df3 = pd.DataFrame([{"RESOURCEID": "R003"}])

        cache.set("a", df1)
        cache.set("b", df2)
        assert cache.get("a") is not None  # refresh recency for "a"
        cache.set("c", df3)  # should evict "b"

        assert cache.get("b") is None
        assert cache.get("a") is not None
        assert cache.get("c") is not None

    def test_resource_process_cache_uses_bounded_config(self):
        import mes_dashboard.services.resource_cache as rc

        assert rc.RESOURCE_PROCESS_CACHE_MAX_SIZE >= 1
        assert rc._resource_df_cache.max_size == rc.RESOURCE_PROCESS_CACHE_MAX_SIZE
