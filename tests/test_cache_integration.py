# -*- coding: utf-8 -*-
"""Integration tests for cache functionality.

Tests API endpoints with cache enabled/disabled scenarios.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import json


@pytest.fixture
def app_with_mock_cache():
    """Create app with mocked cache."""
    import mes_dashboard.core.database as db
    db._ENGINE = None

    from mes_dashboard.app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


class TestHealthEndpoint:
    """Test /health endpoint."""

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    def test_health_all_ok(self, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache):
        """Test health endpoint returns 200 when all services are healthy."""
        mock_check_db.return_value = ('ok', None)
        mock_check_redis.return_value = ('ok', None)
        mock_cache_status.return_value = {
            'enabled': True,
            'sys_date': '2024-01-15 10:30:00',
            'updated_at': '2024-01-15T10:30:00'
        }

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'healthy'
            assert data['services']['database'] == 'ok'
            assert data['services']['redis'] == 'ok'

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    def test_health_redis_down_degraded(self, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache):
        """Test health endpoint returns 200 degraded when Redis is down."""
        mock_check_db.return_value = ('ok', None)
        mock_check_redis.return_value = ('error', 'Connection refused')
        mock_cache_status.return_value = {'enabled': True, 'sys_date': None, 'updated_at': None}

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'degraded'
            assert 'warnings' in data

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    def test_health_db_down_unhealthy(self, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache):
        """Test health endpoint returns 503 when database is down."""
        mock_check_db.return_value = ('error', 'Connection refused')
        mock_check_redis.return_value = ('ok', None)
        mock_cache_status.return_value = {'enabled': True, 'sys_date': None, 'updated_at': None}

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 503
            data = response.get_json()
            assert data['status'] == 'unhealthy'
            assert 'errors' in data

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    def test_health_redis_disabled(self, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache):
        """Test health endpoint shows Redis disabled status."""
        mock_check_db.return_value = ('ok', None)
        mock_check_redis.return_value = ('disabled', None)
        mock_cache_status.return_value = {'enabled': False, 'sys_date': None, 'updated_at': None}

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'healthy'
            assert data['services']['redis'] == 'disabled'


class TestWipApiWithCache:
    """Test WIP API endpoints with cache."""

    @pytest.fixture
    def mock_wip_cache_data(self):
        """Create mock WIP data for cache."""
        return pd.DataFrame({
            'LOTID': ['LOT001', 'LOT002', 'LOT003'],
            'QTY': [100, 200, 150],
            'WORKORDER': ['WO001', 'WO002', 'WO003'],
            'WORKCENTER_GROUP': ['WC1', 'WC1', 'WC2'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1, 2],
            'PACKAGE_LEF': ['PKG1', 'PKG2', 'PKG1'],
            'PRODUCTLINENAME': ['PKG1', 'PKG2', 'PKG1'],
            'EQUIPMENTCOUNT': [1, 0, 0],
            'CURRENTHOLDCOUNT': [0, 1, 0],
            'HOLDREASONNAME': [None, 'Quality Issue', None],
            'STATUS': ['ACTIVE', 'HOLD', 'ACTIVE'],
            'SPECNAME': ['SPEC1', 'SPEC1', 'SPEC2'],
            'SPECSEQUENCE': [1, 1, 2],
            'AGEBYDAYS': [1.5, 3.2, 0.5],
            'EQUIPMENTS': ['EQ001', None, None],
            'SYS_DATE': ['2024-01-15 10:30:00'] * 3
        })

    @patch('mes_dashboard.services.wip_service._get_wip_dataframe')
    @patch('mes_dashboard.services.wip_service.get_cached_sys_date')
    def test_wip_summary_uses_cache(self, mock_sys_date, mock_get_df, app_with_mock_cache, mock_wip_cache_data):
        """Test /api/wip/overview/summary uses cache when available."""
        mock_get_df.return_value = mock_wip_cache_data
        mock_sys_date.return_value = '2024-01-15 10:30:00'

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/wip/overview/summary')

            assert response.status_code == 200
            resp = response.get_json()
            # API returns wrapped response: {success: true, data: {...}}
            data = resp.get('data', resp)  # Handle both wrapped and unwrapped
            assert data['totalLots'] == 3
            assert data['dataUpdateDate'] == '2024-01-15 10:30:00'

    @patch('mes_dashboard.services.wip_service._get_wip_dataframe')
    @patch('mes_dashboard.services.wip_service.get_cached_sys_date')
    def test_wip_matrix_uses_cache(self, mock_sys_date, mock_get_df, app_with_mock_cache, mock_wip_cache_data):
        """Test /api/wip/overview/matrix uses cache when available."""
        mock_get_df.return_value = mock_wip_cache_data
        mock_sys_date.return_value = '2024-01-15 10:30:00'

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/wip/overview/matrix')

            assert response.status_code == 200
            resp = response.get_json()
            # API returns wrapped response: {success: true, data: {...}}
            data = resp.get('data', resp)
            assert 'workcenters' in data
            assert 'packages' in data
            assert 'matrix' in data

    @patch('mes_dashboard.services.wip_service._get_wip_dataframe')
    def test_workcenters_uses_cache(self, mock_get_df, app_with_mock_cache, mock_wip_cache_data):
        """Test /api/wip/meta/workcenters uses cache when available."""
        mock_get_df.return_value = mock_wip_cache_data

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/wip/meta/workcenters')

            assert response.status_code == 200
            resp = response.get_json()
            # API returns wrapped response: {success: true, data: [...]}
            data = resp.get('data', resp) if isinstance(resp, dict) and 'data' in resp else resp
            assert isinstance(data, list)
            assert len(data) == 2  # WC1 and WC2

    @patch('mes_dashboard.services.wip_service._get_wip_dataframe')
    def test_packages_uses_cache(self, mock_get_df, app_with_mock_cache, mock_wip_cache_data):
        """Test /api/wip/meta/packages uses cache when available."""
        mock_get_df.return_value = mock_wip_cache_data

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/wip/meta/packages')

            assert response.status_code == 200
            resp = response.get_json()
            # API returns wrapped response: {success: true, data: [...]}
            data = resp.get('data', resp) if isinstance(resp, dict) and 'data' in resp else resp
            assert isinstance(data, list)
            assert len(data) == 2  # PKG1 and PKG2


class TestHealthEndpointResourceCache:
    """Test /health endpoint resource cache status."""

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    @patch('mes_dashboard.routes.health_routes.get_resource_cache_status')
    def test_health_includes_resource_cache(
        self, mock_res_cache_status, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache
    ):
        """Test health endpoint includes resource_cache field."""
        mock_check_db.return_value = ('ok', None)
        mock_check_redis.return_value = ('ok', None)
        mock_cache_status.return_value = {
            'enabled': True,
            'sys_date': '2024-01-15 10:30:00',
            'updated_at': '2024-01-15T10:30:00'
        }
        mock_res_cache_status.return_value = {
            'enabled': True,
            'loaded': True,
            'count': 1500,
            'version': '2024-01-15T10:00:00',
            'updated_at': '2024-01-15T10:30:00'
        }

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 200
            data = response.get_json()
            assert 'resource_cache' in data
            assert data['resource_cache']['enabled'] is True
            assert data['resource_cache']['loaded'] is True
            assert data['resource_cache']['count'] == 1500

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    @patch('mes_dashboard.routes.health_routes.get_resource_cache_status')
    def test_health_warning_when_resource_cache_not_loaded(
        self, mock_res_cache_status, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache
    ):
        """Test health endpoint shows warning when resource cache enabled but not loaded."""
        mock_check_db.return_value = ('ok', None)
        mock_check_redis.return_value = ('ok', None)
        mock_cache_status.return_value = {
            'enabled': True,
            'sys_date': '2024-01-15 10:30:00',
            'updated_at': '2024-01-15T10:30:00'
        }
        mock_res_cache_status.return_value = {
            'enabled': True,
            'loaded': False,
            'count': 0,
            'version': None,
            'updated_at': None
        }

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 200
            data = response.get_json()
            assert 'warnings' in data
            assert any('Resource cache not loaded' in w for w in data['warnings'])

    @patch('mes_dashboard.routes.health_routes.check_database')
    @patch('mes_dashboard.routes.health_routes.check_redis')
    @patch('mes_dashboard.routes.health_routes.get_cache_status')
    @patch('mes_dashboard.routes.health_routes.get_resource_cache_status')
    def test_health_no_warning_when_resource_cache_disabled(
        self, mock_res_cache_status, mock_cache_status, mock_check_redis, mock_check_db, app_with_mock_cache
    ):
        """Test health endpoint no warning when resource cache is disabled."""
        mock_check_db.return_value = ('ok', None)
        mock_check_redis.return_value = ('ok', None)
        mock_cache_status.return_value = {
            'enabled': True,
            'sys_date': '2024-01-15 10:30:00',
            'updated_at': '2024-01-15T10:30:00'
        }
        mock_res_cache_status.return_value = {'enabled': False}

        with app_with_mock_cache.test_client() as client:
            response = client.get('/health')

            assert response.status_code == 200
            data = response.get_json()
            # No warnings about resource cache
            warnings = data.get('warnings', [])
            assert not any('Resource cache' in w for w in warnings)


class TestResourceFilterOptionsWithCache:
    """Test resource filter options with cache."""

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    @patch('mes_dashboard.services.resource_service.read_sql_df')
    def test_filter_options_uses_resource_cache(
        self, mock_read_sql, mock_get_all, app_with_mock_cache
    ):
        """Test resource filter options uses resource_cache for static data."""
        # Mock resource cache data
        mock_get_all.return_value = [
            {'WORKCENTERNAME': 'WC1', 'RESOURCEFAMILYNAME': 'F1', 'PJ_DEPARTMENT': 'Dept1',
             'LOCATIONNAME': 'Loc1', 'PJ_ASSETSSTATUS': 'Active'},
            {'WORKCENTERNAME': 'WC2', 'RESOURCEFAMILYNAME': 'F2', 'PJ_DEPARTMENT': 'Dept1',
             'LOCATIONNAME': 'Loc1', 'PJ_ASSETSSTATUS': 'Active'},
        ]
        mock_read_sql.return_value = pd.DataFrame({'NEWSTATUSNAME': ['PRD', 'SBY']})

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/resource/filter_options')

            assert response.status_code == 200
            data = response.get_json()

            if data.get('success'):
                options = data.get('data', {})
                assert 'WC1' in options['workcenters']
                assert 'WC2' in options['workcenters']
                assert 'F1' in options['families']
                assert 'F2' in options['families']


class TestResourceHistoryOptionsWithCache:
    """Test resource history filter options with cache."""

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_history_options_uses_resource_cache(
        self, mock_get_all, mock_groups, app_with_mock_cache
    ):
        """Test resource history options uses resource_cache for families."""
        mock_groups.return_value = [
            {'name': 'Group1', 'sequence': 1},
            {'name': 'Group2', 'sequence': 2}
        ]
        # Mock resource cache data for families
        mock_get_all.return_value = [
            {'RESOURCEFAMILYNAME': 'Family1'},
            {'RESOURCEFAMILYNAME': 'Family2'},
            {'RESOURCEFAMILYNAME': 'Family1'},  # duplicate
        ]

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/resource/history/options')

            assert response.status_code == 200
            data = response.get_json()

            if data.get('success'):
                options = data.get('data', {})
                assert 'families' in options
                assert 'Family1' in options['families']
                assert 'Family2' in options['families']


class TestFallbackToOracle:
    """Test fallback to Oracle when cache is unavailable."""

    @patch('mes_dashboard.services.wip_service._get_wip_dataframe')
    @patch('mes_dashboard.services.wip_service._get_wip_summary_from_oracle')
    def test_summary_falls_back_to_oracle(self, mock_oracle, mock_get_df, app_with_mock_cache):
        """Test summary falls back to Oracle when cache unavailable."""
        mock_get_df.return_value = None  # Cache miss
        mock_oracle.return_value = {
            'totalLots': 100,
            'totalQtyPcs': 10000,
            'byWipStatus': {
                'run': {'lots': 30, 'qtyPcs': 3000},
                'queue': {'lots': 50, 'qtyPcs': 5000},
                'hold': {'lots': 20, 'qtyPcs': 2000},
                'qualityHold': {'lots': 15, 'qtyPcs': 1500},
                'nonQualityHold': {'lots': 5, 'qtyPcs': 500}
            },
            'dataUpdateDate': '2024-01-15 10:30:00'
        }

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/wip/overview/summary')

            assert response.status_code == 200
            resp = response.get_json()
            # API returns wrapped response: {success: true, data: {...}}
            data = resp.get('data', resp)
            assert data['totalLots'] == 100
            mock_oracle.assert_called_once()

    @patch('mes_dashboard.services.wip_service._get_wip_dataframe')
    @patch('mes_dashboard.services.wip_service._get_workcenters_from_oracle')
    def test_workcenters_falls_back_to_oracle(self, mock_oracle, mock_get_df, app_with_mock_cache):
        """Test workcenters falls back to Oracle when cache unavailable."""
        mock_get_df.return_value = None  # Cache miss
        mock_oracle.return_value = [
            {'name': 'WC1', 'lot_count': 50},
            {'name': 'WC2', 'lot_count': 30}
        ]

        with app_with_mock_cache.test_client() as client:
            response = client.get('/api/wip/meta/workcenters')

            assert response.status_code == 200
            resp = response.get_json()
            # API returns wrapped response: {success: true, data: [...]}
            data = resp.get('data', resp) if isinstance(resp, dict) and 'data' in resp else resp
            assert len(data) == 2
            mock_oracle.assert_called_once()
