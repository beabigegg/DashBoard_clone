# -*- coding: utf-8 -*-
"""Integration tests for resource history API endpoints.

Tests API endpoints for proper response format, error handling,
and parameter validation.
"""

import unittest
from unittest.mock import patch, MagicMock
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


class TestResourceHistoryOptionsAPI(unittest.TestCase):
    """Integration tests for /api/resource/history/options endpoint."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.resource_history_routes.get_filter_options')
    def test_options_success(self, mock_get_options):
        """Successful options request should return workcenter_groups and families."""
        mock_get_options.return_value = {
            'workcenter_groups': [
                {'name': '焊接_DB', 'sequence': 1},
                {'name': '成型', 'sequence': 4}
            ],
            'families': ['FAM01', 'FAM02']
        }

        response = self.client.get('/api/resource/history/options')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertEqual(len(data['data']['workcenter_groups']), 2)
        self.assertEqual(data['data']['workcenter_groups'][0]['name'], '焊接_DB')
        self.assertEqual(data['data']['families'], ['FAM01', 'FAM02'])

    @patch('mes_dashboard.routes.resource_history_routes.get_filter_options')
    def test_options_failure(self, mock_get_options):
        """Failed options request should return error."""
        mock_get_options.return_value = None

        response = self.client.get('/api/resource/history/options')

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)


class TestResourceHistorySummaryAPI(unittest.TestCase):
    """Integration tests for /api/resource/history/summary endpoint."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_missing_start_date(self):
        """Missing start_date should return 400."""
        response = self.client.get('/api/resource/history/summary?end_date=2024-01-31')

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('start_date', data['error'])

    def test_missing_end_date(self):
        """Missing end_date should return 400."""
        response = self.client.get('/api/resource/history/summary?start_date=2024-01-01')

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('end_date', data['error'])

    @patch('mes_dashboard.routes.resource_history_routes.query_summary')
    def test_date_range_exceeds_limit(self, mock_query):
        """Date range exceeding 730 days should return error."""
        mock_query.return_value = {'error': '查詢範圍不可超過 730 天（兩年）'}

        response = self.client.get(
            '/api/resource/history/summary?start_date=2024-01-01&end_date=2026-01-02'
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('730', data['error'])

    @patch('mes_dashboard.routes.resource_history_routes.query_summary')
    def test_successful_summary(self, mock_query):
        """Successful summary request should return all data sections."""
        mock_query.return_value = {
            'kpi': {
                'ou_pct': 80.0,
                'prd_hours': 800,
                'sby_hours': 100,
                'udt_hours': 50,
                'sdt_hours': 30,
                'egt_hours': 20,
                'nst_hours': 100,
                'machine_count': 10
            },
            'trend': [{'date': '2024-01-01', 'ou_pct': 80.0}],
            'heatmap': [{'workcenter': 'WC01', 'date': '2024-01-01', 'ou_pct': 80.0}],
            'workcenter_comparison': [{'workcenter': 'WC01', 'ou_pct': 80.0}]
        }

        response = self.client.get(
            '/api/resource/history/summary?start_date=2024-01-01&end_date=2024-01-07'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('kpi', data['data'])
        self.assertIn('trend', data['data'])
        self.assertIn('heatmap', data['data'])
        self.assertIn('workcenter_comparison', data['data'])

    @patch('mes_dashboard.routes.resource_history_routes.query_summary')
    def test_summary_with_filters(self, mock_query):
        """Summary with filters should pass them to service."""
        mock_query.return_value = {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []}

        response = self.client.get(
            '/api/resource/history/summary'
            '?start_date=2024-01-01'
            '&end_date=2024-01-07'
            '&granularity=week'
            '&workcenter_groups=焊接_DB'
            '&workcenter_groups=成型'
            '&families=FAM01'
            '&families=FAM02'
            '&is_production=1'
            '&is_key=1'
        )

        self.assertEqual(response.status_code, 200)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args[1]
        self.assertEqual(call_kwargs['granularity'], 'week')
        self.assertEqual(call_kwargs['workcenter_groups'], ['焊接_DB', '成型'])
        self.assertEqual(call_kwargs['families'], ['FAM01', 'FAM02'])
        self.assertTrue(call_kwargs['is_production'])
        self.assertTrue(call_kwargs['is_key'])


class TestResourceHistoryDetailAPI(unittest.TestCase):
    """Integration tests for /api/resource/history/detail endpoint."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_missing_dates(self):
        """Missing dates should return 400."""
        response = self.client.get('/api/resource/history/detail')

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.resource_history_routes.query_detail')
    def test_successful_detail(self, mock_query):
        """Successful detail request should return data with total and truncated flag."""
        mock_query.return_value = {
            'data': [
                {'workcenter': 'WC01', 'family': 'FAM01', 'resource': 'RES01', 'ou_pct': 80.0}
            ],
            'total': 100,
            'truncated': False,
            'max_records': None
        }

        response = self.client.get(
            '/api/resource/history/detail?start_date=2024-01-01&end_date=2024-01-07'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('total', data)
        self.assertIn('truncated', data)
        self.assertFalse(data['truncated'])

    @patch('mes_dashboard.routes.resource_history_routes.query_detail')
    def test_detail_truncated_warning(self, mock_query):
        """Detail with truncated data should return truncated flag and max_records."""
        mock_query.return_value = {
            'data': [{'workcenter': 'WC01', 'family': 'FAM01', 'resource': 'RES01', 'ou_pct': 80.0}],
            'total': 6000,
            'truncated': True,
            'max_records': 5000
        }

        response = self.client.get(
            '/api/resource/history/detail'
            '?start_date=2024-01-01'
            '&end_date=2024-01-07'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertTrue(data['truncated'])
        self.assertEqual(data['max_records'], 5000)
        self.assertEqual(data['total'], 6000)


class TestResourceHistoryExportAPI(unittest.TestCase):
    """Integration tests for /api/resource/history/export endpoint."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_missing_dates(self):
        """Missing dates should return 400."""
        response = self.client.get('/api/resource/history/export')

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.resource_history_routes.export_csv')
    def test_successful_export(self, mock_export):
        """Successful export should return CSV with correct headers."""
        mock_export.return_value = iter(['站點,型號,機台,OU%\n', 'WC01,FAM01,RES01,80%\n'])

        response = self.client.get(
            '/api/resource/history/export?start_date=2024-01-01&end_date=2024-01-07'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.content_type)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertIn('resource_history', response.headers['Content-Disposition'])

    @patch('mes_dashboard.routes.resource_history_routes.export_csv')
    def test_export_filename_includes_dates(self, mock_export):
        """Export filename should include date range."""
        mock_export.return_value = iter(['header\n'])

        response = self.client.get(
            '/api/resource/history/export?start_date=2024-01-01&end_date=2024-01-07'
        )

        self.assertIn('2024-01-01', response.headers['Content-Disposition'])
        self.assertIn('2024-01-07', response.headers['Content-Disposition'])


class TestAPIContentType(unittest.TestCase):
    """Test that APIs return proper content types."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.resource_history_routes.get_filter_options')
    def test_json_content_type(self, mock_get_options):
        """API endpoints should return application/json content type."""
        mock_get_options.return_value = {'workcenter_groups': [], 'families': []}

        response = self.client.get('/api/resource/history/options')

        self.assertIn('application/json', response.content_type)


if __name__ == '__main__':
    unittest.main()
