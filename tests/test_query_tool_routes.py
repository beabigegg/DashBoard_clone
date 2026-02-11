# -*- coding: utf-8 -*-
"""Integration tests for Query Tool API routes.

Tests the API endpoints with mocked service dependencies:
- Input validation (empty, over limit, invalid format)
- Success responses
- Error handling
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from mes_dashboard import create_app


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestQueryToolPage:
    """Tests for /query-tool page route."""

    def test_page_returns_html(self, client):
        """Should return the query tool page."""
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin", "displayName": "Admin"}

        response = client.get('/query-tool')
        assert response.status_code == 200
        assert b'html' in response.data.lower()


class TestResolveEndpoint:
    """Tests for /api/query-tool/resolve endpoint."""

    def test_missing_input_type(self, client):
        """Should return error without input_type."""
        response = client.post(
            '/api/query-tool/resolve',
            json={
                'values': ['GA23100020-A00-001']
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_values(self, client):
        """Should return error without values."""
        response = client.post(
            '/api/query-tool/resolve',
            json={
                'input_type': 'lot_id'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_empty_values(self, client):
        """Should return error for empty values list."""
        response = client.post(
            '/api/query-tool/resolve',
            json={
                'input_type': 'lot_id',
                'values': []
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_values_over_limit(self, client):
        """Should reject values exceeding limit."""
        # More than MAX_LOT_IDS (50)
        values = [f'GA{i:09d}' for i in range(51)]
        response = client.post(
            '/api/query-tool/resolve',
            json={
                'input_type': 'lot_id',
                'values': values
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '超過上限' in data['error'] or '50' in data['error']

    @patch('mes_dashboard.routes.query_tool_routes.resolve_lots')
    def test_resolve_success(self, mock_resolve, client):
        """Should return resolved LOT IDs on success."""
        mock_resolve.return_value = {
            'data': [
                {
                    'container_id': '488103800029578b',
                    'lot_id': 'GA23100020-A00-001',
                    'input_value': 'GA23100020-A00-001',
                    'spec_name': 'SPEC-001'
                }
            ],
            'total': 1,
            'input_count': 1,
            'not_found': []
        }

        response = client.post(
            '/api/query-tool/resolve',
            json={
                'input_type': 'lot_id',
                'values': ['GA23100020-A00-001']
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        assert data['total'] == 1
        assert data['data'][0]['lot_id'] == 'GA23100020-A00-001'

    @patch('mes_dashboard.routes.query_tool_routes.resolve_lots')
    def test_resolve_not_found(self, mock_resolve, client):
        """Should return not_found list for missing LOT IDs."""
        mock_resolve.return_value = {
            'data': [],
            'total': 0,
            'input_count': 1,
            'not_found': ['INVALID-LOT-ID']
        }

        response = client.post(
            '/api/query-tool/resolve',
            json={
                'input_type': 'lot_id',
                'values': ['INVALID-LOT-ID']
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] == 0
        assert 'INVALID-LOT-ID' in data['not_found']


class TestLotHistoryEndpoint:
    """Tests for /api/query-tool/lot-history endpoint."""

    def test_missing_container_id(self, client):
        """Should return error without container_id."""
        response = client.get('/api/query-tool/lot-history')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_lot_history_success(self, mock_query, client):
        """Should return lot history on success."""
        mock_query.return_value = {
            'data': [
                {
                    'CONTAINERID': '488103800029578b',
                    'EQUIPMENTNAME': 'ASSY-01',
                    'SPECNAME': 'SPEC-001',
                    'TRACKINTIMESTAMP': '2024-01-15 10:30:00',
                    'TRACKOUTTIMESTAMP': '2024-01-15 11:00:00'
                }
            ],
            'total': 1
        }

        response = client.get('/api/query-tool/lot-history?container_id=488103800029578b')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        assert data['total'] == 1

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_lot_history_service_error(self, mock_query, client):
        """Should return error from service."""
        mock_query.return_value = {'error': '查詢失敗'}

        response = client.get('/api/query-tool/lot-history?container_id=invalid')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


class TestAdjacentLotsEndpoint:
    """Tests for /api/query-tool/adjacent-lots endpoint."""

    def test_missing_equipment_id(self, client):
        """Should return error without equipment_id."""
        response = client.get(
            '/api/query-tool/adjacent-lots?'
            'target_time=2024-01-15T10:30:00'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_target_time(self, client):
        """Should return error without target_time."""
        response = client.get(
            '/api/query-tool/adjacent-lots?'
            'equipment_id=EQ001'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_with_only_equipment_id(self, client):
        """Should return error with only equipment_id (no target_time)."""
        response = client.get(
            '/api/query-tool/adjacent-lots?'
            'equipment_id=EQ001'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('mes_dashboard.routes.query_tool_routes.get_adjacent_lots')
    def test_adjacent_lots_success(self, mock_query, client):
        """Should return adjacent lots on success."""
        mock_query.return_value = {
            'data': [
                {
                    'CONTAINERID': '488103800029578a',
                    'CONTAINERNAME': 'GA23100020-A00-000',
                    'relative_position': -1
                },
                {
                    'CONTAINERID': '488103800029578b',
                    'CONTAINERNAME': 'GA23100020-A00-001',
                    'relative_position': 0
                },
                {
                    'CONTAINERID': '488103800029578c',
                    'CONTAINERNAME': 'GA23100020-A00-002',
                    'relative_position': 1
                }
            ],
            'total': 3
        }

        response = client.get(
            '/api/query-tool/adjacent-lots?'
            'equipment_id=EQ001&target_time=2024-01-15T10:30:00'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        assert data['total'] == 3
        # Verify service was called without spec_name
        mock_query.assert_called_once()
        call_args = mock_query.call_args
        assert call_args[0][0] == 'EQ001'  # equipment_id
        assert '2024-01-15' in call_args[0][1]  # target_time


class TestLotAssociationsEndpoint:
    """Tests for /api/query-tool/lot-associations endpoint."""

    def test_missing_container_id(self, client):
        """Should return error without container_id."""
        response = client.get('/api/query-tool/lot-associations?type=materials')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_type(self, client):
        """Should return error without type."""
        response = client.get('/api/query-tool/lot-associations?container_id=488103800029578b')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_invalid_type(self, client):
        """Should return error for invalid association type."""
        response = client.get(
            '/api/query-tool/lot-associations?container_id=488103800029578b&type=invalid'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '不支援' in data['error'] or 'type' in data['error'].lower()

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_materials')
    def test_lot_materials_success(self, mock_query, client):
        """Should return lot materials on success."""
        mock_query.return_value = {
            'data': [
                {
                    'MATERIALTYPE': 'TypeA',
                    'MATERIALNAME': 'Material-001',
                    'QTY': 100
                }
            ],
            'total': 1
        }

        response = client.get(
            '/api/query-tool/lot-associations?container_id=488103800029578b&type=materials'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        assert data['total'] == 1


class TestEquipmentPeriodEndpoint:
    """Tests for /api/query-tool/equipment-period endpoint."""

    def test_missing_query_type(self, client):
        """Should return error without query_type."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '查詢類型' in data['error'] or 'type' in data['error'].lower()

    def test_empty_equipment_ids(self, client):
        """Should return error for empty equipment_ids."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': [],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
                'query_type': 'status_hours'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_start_date(self, client):
        """Should return error without start_date."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'end_date': '2024-01-31',
                'query_type': 'status_hours'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_end_date(self, client):
        """Should return error without end_date."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'start_date': '2024-01-01',
                'query_type': 'status_hours'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_invalid_date_range(self, client):
        """Should return error for end date before start date."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'start_date': '2024-12-31',
                'end_date': '2024-01-01',
                'query_type': 'status_hours'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '結束日期' in data['error'] or '早於' in data['error']

    def test_date_range_exceeds_limit(self, client):
        """Should reject date range > 90 days."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'start_date': '2024-01-01',
                'end_date': '2024-06-01',
                'query_type': 'status_hours'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '90' in data['error']

    def test_invalid_query_type(self, client):
        """Should reject invalid query_type."""
        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
                'query_type': 'invalid_type'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '查詢類型' in data['error'] or 'type' in data['error'].lower()

    @patch('mes_dashboard.routes.query_tool_routes.get_equipment_status_hours')
    def test_equipment_status_hours_success(self, mock_status, client):
        """Should return equipment status hours on success."""
        mock_status.return_value = {'data': [], 'total': 0}

        response = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ001'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
                'query_type': 'status_hours'
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data


class TestExportCsvEndpoint:
    """Tests for /api/query-tool/export-csv endpoint."""

    def test_missing_export_type(self, client):
        """Should return error without export_type."""
        response = client.post(
            '/api/query-tool/export-csv',
            json={
                'params': {'container_id': '488103800029578b'}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_invalid_export_type(self, client):
        """Should return error for invalid export_type."""
        response = client.post(
            '/api/query-tool/export-csv',
            json={
                'export_type': 'invalid_type',
                'params': {}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '不支援' in data['error'] or 'type' in data['error'].lower()

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_export_lot_history_success(self, mock_get_history, client):
        """Should return CSV for lot history."""
        mock_get_history.return_value = {
            'data': [
                {
                    'EQUIPMENTNAME': 'ASSY-01',
                    'SPECNAME': 'SPEC-001',
                    'TRACKINTIMESTAMP': '2024-01-15 10:00:00'
                }
            ],
            'total': 1
        }

        response = client.post(
            '/api/query-tool/export-csv',
            json={
                'export_type': 'lot_history',
                'params': {'container_id': '488103800029578b'}
            }
        )
        assert response.status_code == 200
        assert 'text/csv' in response.content_type


class TestEquipmentListEndpoint:
    """Tests for /api/query-tool/equipment-list endpoint."""

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_get_equipment_list_success(self, mock_get_resources, client):
        """Should return equipment list."""
        mock_get_resources.return_value = [
            {
                'RESOURCEID': 'EQ001',
                'RESOURCENAME': 'ASSY-01',
                'WORKCENTERNAME': 'WC-A',
                'RESOURCEFAMILYNAME': 'FAM-01'
            },
            {
                'RESOURCEID': 'EQ002',
                'RESOURCENAME': 'ASSY-02',
                'WORKCENTERNAME': 'WC-B',
                'RESOURCEFAMILYNAME': 'FAM-02'
            }
        ]

        response = client.get('/api/query-tool/equipment-list')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        assert 'total' in data
        assert data['total'] == 2

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_get_equipment_list_empty(self, mock_get_resources, client):
        """Should return error when no equipment available."""
        mock_get_resources.return_value = []

        response = client.get('/api/query-tool/equipment-list')
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_get_equipment_list_exception(self, mock_get_resources, client):
        """Should handle exception gracefully."""
        mock_get_resources.side_effect = Exception('Database error')

        response = client.get('/api/query-tool/equipment-list')
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data


class TestWorkcenterGroupsEndpoint:
    """Tests for /api/query-tool/workcenter-groups endpoint."""

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    def test_returns_groups_list(self, mock_get_groups, client):
        """Should return workcenter groups list."""
        mock_get_groups.return_value = [
            {'name': 'DB', 'sequence': 1},
            {'name': 'WB', 'sequence': 2},
        ]

        response = client.get('/api/query-tool/workcenter-groups')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        assert len(data['data']) == 2
        assert data['total'] == 2

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    def test_handles_cache_failure(self, mock_get_groups, client):
        """Should return 500 when cache fails."""
        mock_get_groups.return_value = None

        response = client.get('/api/query-tool/workcenter-groups')

        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    def test_handles_exception(self, mock_get_groups, client):
        """Should handle exception gracefully."""
        mock_get_groups.side_effect = Exception('Cache error')

        response = client.get('/api/query-tool/workcenter-groups')

        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data


class TestLotHistoryWithWorkcenterFilter:
    """Tests for /api/query-tool/lot-history with workcenter filter."""

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_accepts_workcenter_groups_param(self, mock_query, client):
        """Should pass workcenter_groups parameter to service."""
        mock_query.return_value = {
            'data': [],
            'total': 0,
            'filtered_by_groups': ['DB', 'WB']
        }

        response = client.get(
            '/api/query-tool/lot-history?'
            'container_id=abc123&workcenter_groups=DB,WB'
        )

        assert response.status_code == 200
        # Verify the service was called with workcenter_groups
        call_args = mock_query.call_args
        assert call_args[1].get('workcenter_groups') == ['DB', 'WB']

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_empty_workcenter_groups_ignored(self, mock_query, client):
        """Should ignore empty workcenter_groups parameter."""
        mock_query.return_value = {
            'data': [],
            'total': 0,
            'filtered_by_groups': []
        }

        response = client.get(
            '/api/query-tool/lot-history?'
            'container_id=abc123&workcenter_groups='
        )

        assert response.status_code == 200
        # Verify workcenter_groups is None (not empty list)
        call_args = mock_query.call_args
        assert call_args[1].get('workcenter_groups') is None

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_returns_filtered_by_groups_in_response(self, mock_query, client):
        """Should include filtered_by_groups in response."""
        mock_query.return_value = {
            'data': [{'CONTAINERID': 'abc123'}],
            'total': 1,
            'filtered_by_groups': ['DB']
        }

        response = client.get(
            '/api/query-tool/lot-history?'
            'container_id=abc123&workcenter_groups=DB'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('filtered_by_groups') == ['DB']
