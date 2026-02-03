# -*- coding: utf-8 -*-
"""Integration tests for API endpoints.

Tests API endpoints for proper response format, error handling,
and timeout behavior compatible with the MesApi client.
"""

import unittest
from unittest.mock import patch, MagicMock
import json

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class TestTableQueryAPIIntegration(unittest.TestCase):
    """Integration tests for table query APIs."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.app.get_table_columns')
    def test_get_table_columns_success(self, mock_get_columns):
        """GET table columns should return JSON with columns array."""
        mock_get_columns.return_value = ['ID', 'NAME', 'STATUS', 'CREATED_AT']

        response = self.client.post(
            '/api/get_table_columns',
            json={'table_name': 'TEST_TABLE'},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('columns', data)
        self.assertEqual(len(data['columns']), 4)

    def test_get_table_columns_missing_table_name(self):
        """GET table columns without table_name should return 400."""
        response = self.client.post(
            '/api/get_table_columns',
            json={},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)

    @patch('mes_dashboard.app.get_table_data')
    def test_query_table_success(self, mock_get_data):
        """Query table should return JSON with data array."""
        mock_get_data.return_value = {
            'data': [{'ID': 1, 'NAME': 'Test'}],
            'row_count': 1
        }

        response = self.client.post(
            '/api/query_table',
            json={'table_name': 'TEST_TABLE', 'limit': 100},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('data', data)
        self.assertEqual(data['row_count'], 1)

    def test_query_table_missing_table_name(self):
        """Query table without table_name should return 400."""
        response = self.client.post(
            '/api/query_table',
            json={'limit': 100},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)

    @patch('mes_dashboard.app.get_table_data')
    def test_query_table_with_filters(self, mock_get_data):
        """Query table should pass filters to the service."""
        mock_get_data.return_value = {
            'data': [],
            'row_count': 0
        }

        response = self.client.post(
            '/api/query_table',
            json={
                'table_name': 'TEST_TABLE',
                'limit': 100,
                'filters': {'STATUS': 'ACTIVE'}
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        mock_get_data.assert_called_once()
        call_args = mock_get_data.call_args
        self.assertEqual(call_args[0][3], {'STATUS': 'ACTIVE'})


class TestWIPAPIIntegration(unittest.TestCase):
    """Integration tests for WIP API endpoints."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_wip_summary_response_format(self, mock_summary):
        """WIP summary should return consistent JSON structure."""
        mock_summary.return_value = {
            'totalLots': 1000,
            'totalQtyPcs': 100000,
            'byWipStatus': {
                'run': {'lots': 800, 'qtyPcs': 80000},
                'queue': {'lots': 150, 'qtyPcs': 15000},
                'hold': {'lots': 50, 'qtyPcs': 5000}
            },
            'dataUpdateDate': '2026-01-28 10:00:00'
        }

        response = self.client.get('/api/wip/overview/summary')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Verify response structure for MesApi compatibility
        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_wip_summary_error_response(self, mock_summary):
        """WIP summary error should return proper error structure."""
        mock_summary.return_value = None

        response = self.client.get('/api/wip/overview/summary')

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)

        # Verify error response structure
        self.assertIn('success', data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    @patch('mes_dashboard.routes.wip_routes.get_wip_matrix')
    def test_wip_matrix_response_format(self, mock_matrix):
        """WIP matrix should return consistent JSON structure."""
        mock_matrix.return_value = {
            'workcenters': ['WC1', 'WC2'],
            'packages': ['PKG1'],
            'matrix': {'WC1': {'PKG1': 100}},
            'workcenter_totals': {'WC1': 100},
            'package_totals': {'PKG1': 100},
            'grand_total': 100
        }

        response = self.client.get('/api/wip/overview/matrix')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('workcenters', data['data'])
        self.assertIn('matrix', data['data'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_wip_detail_response_format(self, mock_detail):
        """WIP detail should return consistent JSON structure."""
        mock_detail.return_value = {
            'workcenter': 'TestWC',
            'summary': {
                'total_lots': 100,
                'on_equipment_lots': 50,
                'waiting_lots': 40,
                'hold_lots': 10
            },
            'specs': ['Spec1'],
            'lots': [{'lot_id': 'LOT001', 'status': 'ACTIVE'}],
            'pagination': {
                'page': 1,
                'page_size': 100,
                'total_count': 100,
                'total_pages': 1
            },
            'sys_date': '2026-01-28 10:00:00'
        }

        response = self.client.get('/api/wip/detail/TestWC')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('pagination', data['data'])


class TestResourceAPIIntegration(unittest.TestCase):
    """Integration tests for Resource API endpoints."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.resource_routes.get_resource_status_summary')
    def test_resource_status_summary_response_format(self, mock_summary):
        """Resource status summary should return consistent JSON structure."""
        mock_summary.return_value = {
            'total_count': 100,
            'by_status_category': {'PRODUCTIVE': 60, 'STANDBY': 30, 'DOWN': 10},
            'by_status': {'PRD': 60, 'SBY': 30, 'UDT': 5, 'SDT': 5, 'EGT': 0, 'NST': 0, 'OTHER': 0},
            'by_workcenter_group': {'焊接': 50, '成型': 50},
            'with_active_job': 40,
            'with_wip': 35,
            'ou_pct': 63.2,
            'availability_pct': 90.0,
        }

        response = self.client.get('/api/resource/status/summary')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Verify response structure
        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('total_count', data['data'])


class TestAPIContentType(unittest.TestCase):
    """Test that APIs return proper content types."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_api_returns_json_content_type(self, mock_summary):
        """API endpoints should return application/json content type."""
        mock_summary.return_value = {
            'totalLots': 0, 'totalQtyPcs': 0,
            'byWipStatus': {'run': {}, 'queue': {}, 'hold': {}},
            'dataUpdateDate': None
        }

        response = self.client.get('/api/wip/overview/summary')

        self.assertIn('application/json', response.content_type)

    @patch('mes_dashboard.app.get_table_columns')
    def test_table_api_returns_json_content_type(self, mock_columns):
        """Table API should return application/json content type."""
        mock_columns.return_value = ['COL1', 'COL2']

        response = self.client.post(
            '/api/get_table_columns',
            json={'table_name': 'TEST'},
            content_type='application/json'
        )

        self.assertIn('application/json', response.content_type)


if __name__ == "__main__":
    unittest.main()
