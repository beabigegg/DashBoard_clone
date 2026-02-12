# -*- coding: utf-8 -*-
"""End-to-end tests for resource history analysis page.

These tests simulate real user workflows through the resource history analysis feature.
Run with: pytest tests/e2e/test_resource_history_e2e.py -v --run-integration
"""

import json
import pytest
from unittest.mock import patch
import pandas as pd
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


@pytest.fixture
def app():
    """Create application for testing."""
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestResourceHistoryPageAccess:
    """E2E tests for page access and navigation."""

    @staticmethod
    def _load_resource_history_entry(client):
        spa_enabled = bool(client.application.config.get("PORTAL_SPA_ENABLED", False))
        response = client.get('/resource-history', follow_redirects=False)
        if spa_enabled:
            assert response.status_code == 302
            assert response.location.endswith('/portal-shell/resource-history')
            shell_response = client.get('/portal-shell/resource-history')
            assert shell_response.status_code == 200
            return shell_response, True
        return response, False

    def test_page_loads_successfully(self, client):
        """Resource history page should load without errors."""
        response, spa_enabled = self._load_resource_history_entry(client)
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        if spa_enabled:
            assert '/static/dist/portal-shell.js' in content
        else:
            assert '設備歷史績效' in content

    def test_page_bootstrap_container_exists(self, client):
        """Resource history page should expose the Vue mount container."""
        response, _spa_enabled = self._load_resource_history_entry(client)
        content = response.data.decode('utf-8')

        assert "id='app'" in content or 'id="app"' in content

    def test_page_references_vite_module(self, client):
        """Resource history page should load the Vite module bundle."""
        response, spa_enabled = self._load_resource_history_entry(client)
        content = response.data.decode('utf-8')

        if spa_enabled:
            assert '/static/dist/portal-shell.js' in content
        else:
            assert '/static/dist/resource-history.js' in content
        assert 'type="module"' in content


class TestResourceHistoryAPIWorkflow:
    """E2E tests for API workflows."""

    @patch('mes_dashboard.services.resource_history_service.get_filter_options')
    def test_filter_options_workflow(self, mock_get_filter_options, client):
        """Filter options should be loadable."""
        mock_get_filter_options.return_value = {
            'workcenter_groups': [
                {'name': '焊接_DB', 'sequence': 1},
                {'name': '焊接_WB', 'sequence': 2},
                {'name': '成型', 'sequence': 4},
            ],
            'families': ['FAM001', 'FAM002'],
        }

        response = client.get('/api/resource/history/options')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'workcenter_groups' in data['data']
        assert 'families' in data['data']

    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_complete_query_workflow(self, mock_read_sql, mock_resources, client):
        """Complete query workflow should return all data sections."""
        mock_resources.return_value = [
            {
                'RESOURCEID': 'RES001',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES001',
            },
            {
                'RESOURCEID': 'RES002',
                'WORKCENTERNAME': '成型',
                'RESOURCEFAMILYNAME': 'FAM002',
                'RESOURCENAME': 'RES002',
            },
        ]

        # Mock responses for the 3 queries in query_summary
        kpi_df = pd.DataFrame([{
            'PRD_HOURS': 8000, 'SBY_HOURS': 1000, 'UDT_HOURS': 500,
            'SDT_HOURS': 300, 'EGT_HOURS': 200, 'NST_HOURS': 1000,
            'MACHINE_COUNT': 100
        }])

        trend_df = pd.DataFrame([
            {'DATA_DATE': datetime(2024, 1, 1), 'PRD_HOURS': 1000, 'SBY_HOURS': 100,
             'UDT_HOURS': 50, 'SDT_HOURS': 30, 'EGT_HOURS': 20, 'NST_HOURS': 100, 'MACHINE_COUNT': 100},
            {'DATA_DATE': datetime(2024, 1, 2), 'PRD_HOURS': 1100, 'SBY_HOURS': 90,
             'UDT_HOURS': 40, 'SDT_HOURS': 25, 'EGT_HOURS': 15, 'NST_HOURS': 100, 'MACHINE_COUNT': 100},
        ])

        heatmap_raw_df = pd.DataFrame([
            {'HISTORYID': 'RES001', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 400, 'SBY_HOURS': 50, 'UDT_HOURS': 25, 'SDT_HOURS': 15, 'EGT_HOURS': 10, 'NST_HOURS': 20},
            {'HISTORYID': 'RES002', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 600, 'SBY_HOURS': 50, 'UDT_HOURS': 25, 'SDT_HOURS': 15, 'EGT_HOURS': 10, 'NST_HOURS': 30},
        ])

        # Use function-based side_effect for ThreadPoolExecutor parallel queries
        def mock_sql(sql, _params=None):
            sql_upper = sql.upper()
            if 'HISTORYID' in sql_upper and 'DATA_DATE' in sql_upper:
                return heatmap_raw_df
            elif 'DATA_DATE' in sql_upper:
                return trend_df
            else:
                return kpi_df

        mock_read_sql.side_effect = mock_sql

        response = client.get(
            '/api/resource/history/summary'
            '?start_date=2024-01-01'
            '&end_date=2024-01-07'
            '&granularity=day'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify KPI
        assert data['data']['kpi']['ou_pct'] == 80.0
        # Availability% = (8000+1000+200) / (8000+1000+200+300+500+1000) * 100 = 9200/11000 = 83.6%
        assert data['data']['kpi']['availability_pct'] == 83.6
        assert data['data']['kpi']['machine_count'] == 100

        # Verify trend
        assert len(data['data']['trend']) == 2
        # Trend should also have availability_pct
        assert 'availability_pct' in data['data']['trend'][0]

        # Verify heatmap
        assert len(data['data']['heatmap']) == 2

        # Verify comparison
        assert len(data['data']['workcenter_comparison']) == 2

    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_detail_query_workflow(self, mock_read_sql, mock_resources, client):
        """Detail query workflow should return hierarchical data."""
        mock_resources.return_value = [
            {
                'RESOURCEID': 'RES001',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES001',
            },
            {
                'RESOURCEID': 'RES002',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES002',
            },
        ]

        detail_df = pd.DataFrame([
            {'HISTORYID': 'RES001',
             'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
            {'HISTORYID': 'RES002',
             'PRD_HOURS': 75, 'SBY_HOURS': 15, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
        ])

        mock_read_sql.return_value = detail_df

        response = client.get(
            '/api/resource/history/detail'
            '?start_date=2024-01-01'
            '&end_date=2024-01-07'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total'] == 2
        assert len(data['data']) == 2
        assert data['truncated'] is False

        # Verify data structure
        first_row = data['data'][0]
        assert 'workcenter' in first_row
        assert 'family' in first_row
        assert 'resource' in first_row
        assert 'ou_pct' in first_row
        assert 'availability_pct' in first_row
        assert 'prd_hours' in first_row
        assert 'prd_pct' in first_row

    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_export_workflow(self, mock_read_sql, mock_resources, client):
        """Export workflow should return valid CSV."""
        mock_resources.return_value = [
            {
                'RESOURCEID': 'RES001',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES001',
            }
        ]
        mock_read_sql.return_value = pd.DataFrame([
            {'HISTORYID': 'RES001',
             'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
        ])

        response = client.get(
            '/api/resource/history/export'
            '?start_date=2024-01-01'
            '&end_date=2024-01-07'
        )

        assert response.status_code == 200
        assert 'text/csv' in response.content_type

        content = response.data.decode('utf-8-sig')
        lines = content.strip().split('\n')

        # Should have header + data rows
        assert len(lines) >= 2

        # Verify header
        header = lines[0]
        assert '站點' in header
        assert 'OU%' in header
        assert 'Availability%' in header


class TestResourceHistoryValidation:
    """E2E tests for input validation."""

    def test_date_range_validation(self, client):
        """Date range exceeding 730 days should be rejected."""
        response = client.get(
            '/api/resource/history/summary'
            '?start_date=2024-01-01'
            '&end_date=2026-01-02'
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert '730' in data['error']

    def test_missing_required_params(self, client):
        """Missing required parameters should return error."""
        response = client.get('/api/resource/history/summary')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_granularity_options(self, mock_read_sql, mock_resources, client):
        """Different granularity options should work."""
        mock_resources.return_value = [{
            'RESOURCEID': 'RES001',
            'WORKCENTERNAME': '焊接_DB',
            'RESOURCEFAMILYNAME': 'FAM001',
            'RESOURCENAME': 'RES001',
        }]
        kpi_df = pd.DataFrame([{
            'PRD_HOURS': 100, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10, 'MACHINE_COUNT': 5
        }])
        trend_df = pd.DataFrame([{
            'DATA_DATE': datetime(2024, 1, 1),
            'PRD_HOURS': 100, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10,
            'MACHINE_COUNT': 5
        }])
        heatmap_raw_df = pd.DataFrame([{
            'HISTORYID': 'RES001',
            'DATA_DATE': datetime(2024, 1, 1),
            'PRD_HOURS': 100, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10
        }])

        for granularity in ['day', 'week', 'month', 'year']:
            def mock_sql(sql, _params=None):
                sql_upper = sql.upper()
                if 'HISTORYID' in sql_upper and 'DATA_DATE' in sql_upper:
                    return heatmap_raw_df
                if 'DATA_DATE' in sql_upper:
                    return trend_df
                return kpi_df

            mock_read_sql.side_effect = mock_sql

            response = client.get(
                f'/api/resource/history/summary'
                f'?start_date=2024-01-01'
                f'&end_date=2024-01-31'
                f'&granularity={granularity}'
            )

            assert response.status_code == 200, f"Failed for granularity={granularity}"


class TestResourceHistoryNavigation:
    """E2E tests for navigation integration."""

    def test_portal_includes_history_tab(self, client):
        """Portal should include resource history tab."""
        if bool(client.application.config.get("PORTAL_SPA_ENABLED", False)):
            response = client.get('/api/portal/navigation')
            assert response.status_code == 200
            payload = response.get_json()
            pages = [
                page
                for drawer in payload.get("drawers", [])
                for page in drawer.get("pages", [])
            ]
            history_pages = [page for page in pages if page.get("route") == "/resource-history"]
            assert history_pages, "resource-history route missing from portal navigation contract"
            assert history_pages[0].get("name") == "設備歷史績效"
        else:
            response = client.get('/')
            content = response.data.decode('utf-8')
            assert '設備歷史績效' in content
            assert 'resourceHistoryFrame' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
