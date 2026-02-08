# -*- coding: utf-8 -*-
"""End-to-end tests for resource history analysis page.

These tests simulate real user workflows through the resource history analysis feature.
Run with: pytest tests/e2e/test_resource_history_e2e.py -v --run-integration
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta

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

    def test_page_loads_successfully(self, client):
        """Resource history page should load without errors."""
        response = client.get('/resource-history')

        assert response.status_code == 200
        content = response.data.decode('utf-8')
        assert '設備歷史績效' in content

    def test_page_contains_filter_elements(self, client):
        """Page should contain all filter elements."""
        response = client.get('/resource-history')
        content = response.data.decode('utf-8')

        # Check for filter elements
        assert 'startDate' in content
        assert 'endDate' in content
        # Multi-select dropdowns
        assert 'workcenterGroupsDropdown' in content
        assert 'familiesDropdown' in content
        assert 'isProduction' in content
        assert 'isKey' in content
        assert 'isMonitor' in content

    def test_page_contains_kpi_cards(self, client):
        """Page should contain KPI card elements."""
        response = client.get('/resource-history')
        content = response.data.decode('utf-8')

        assert 'kpiOuPct' in content
        assert 'kpiAvailabilityPct' in content
        assert 'kpiPrdHours' in content
        assert 'kpiUdtHours' in content
        assert 'kpiSdtHours' in content
        assert 'kpiEgtHours' in content
        assert 'kpiMachineCount' in content

    def test_page_contains_chart_containers(self, client):
        """Page should contain chart container elements."""
        response = client.get('/resource-history')
        content = response.data.decode('utf-8')

        assert 'trendChart' in content
        assert 'stackedChart' in content
        assert 'comparisonChart' in content
        assert 'heatmapChart' in content

    def test_page_contains_table_elements(self, client):
        """Page should contain table elements."""
        response = client.get('/resource-history')
        content = response.data.decode('utf-8')

        assert 'detailTableBody' in content
        assert 'expandAllBtn' in content
        assert 'collapseAllBtn' in content
        assert 'exportBtn' in content


class TestResourceHistoryAPIWorkflow:
    """E2E tests for API workflows."""

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    @patch('mes_dashboard.services.filter_cache.get_resource_families')
    def test_filter_options_workflow(self, mock_families, mock_groups, client):
        """Filter options should be loadable."""
        mock_groups.return_value = [
            {'name': '焊接_DB', 'sequence': 1},
            {'name': '焊接_WB', 'sequence': 2},
            {'name': '成型', 'sequence': 4},
        ]
        mock_families.return_value = ['FAM001', 'FAM002']

        response = client.get('/api/resource/history/options')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'workcenter_groups' in data['data']
        assert 'families' in data['data']

    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_complete_query_workflow(self, mock_read_sql, client):
        """Complete query workflow should return all data sections."""
        # Mock responses for the 4 queries in query_summary
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

        heatmap_df = pd.DataFrame([
            {'WORKCENTERNAME': '焊接_DB', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 400, 'SBY_HOURS': 50, 'UDT_HOURS': 25, 'SDT_HOURS': 15, 'EGT_HOURS': 10},
            {'WORKCENTERNAME': '成型', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 600, 'SBY_HOURS': 50, 'UDT_HOURS': 25, 'SDT_HOURS': 15, 'EGT_HOURS': 10},
        ])

        comparison_df = pd.DataFrame([
            {'WORKCENTERNAME': '焊接_DB', 'PRD_HOURS': 4000, 'SBY_HOURS': 500,
             'UDT_HOURS': 250, 'SDT_HOURS': 150, 'EGT_HOURS': 100, 'MACHINE_COUNT': 50},
            {'WORKCENTERNAME': '成型', 'PRD_HOURS': 4000, 'SBY_HOURS': 500,
             'UDT_HOURS': 250, 'SDT_HOURS': 150, 'EGT_HOURS': 100, 'MACHINE_COUNT': 50},
        ])

        # Use function-based side_effect for ThreadPoolExecutor parallel queries
        def mock_sql(sql):
            sql_upper = sql.upper()
            if 'DATA_DATE' in sql_upper and 'WORKCENTERNAME' in sql_upper:
                return heatmap_df
            elif 'DATA_DATE' in sql_upper:
                return trend_df
            elif 'WORKCENTERNAME' in sql_upper:
                return comparison_df
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

    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_detail_query_workflow(self, mock_read_sql, client):
        """Detail query workflow should return hierarchical data."""
        detail_df = pd.DataFrame([
            {'WORKCENTERNAME': '焊接_DB', 'RESOURCEFAMILYNAME': 'FAM001', 'RESOURCENAME': 'RES001',
             'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
            {'WORKCENTERNAME': '焊接_DB', 'RESOURCEFAMILYNAME': 'FAM001', 'RESOURCENAME': 'RES002',
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

    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_export_workflow(self, mock_read_sql, client):
        """Export workflow should return valid CSV."""
        mock_read_sql.return_value = pd.DataFrame([
            {'WORKCENTERNAME': '焊接_DB', 'RESOURCEFAMILYNAME': 'FAM001', 'RESOURCENAME': 'RES001',
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

    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_granularity_options(self, mock_read_sql, client):
        """Different granularity options should work."""
        mock_df = pd.DataFrame([{
            'PRD_HOURS': 100, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10, 'MACHINE_COUNT': 5
        }])
        mock_read_sql.return_value = mock_df

        for granularity in ['day', 'week', 'month', 'year']:
            mock_read_sql.side_effect = [mock_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()]

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
        response = client.get('/')
        content = response.data.decode('utf-8')

        assert '設備歷史績效' in content
        assert 'resourceHistoryFrame' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
