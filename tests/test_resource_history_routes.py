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


class TestResourceHistoryQueryAPI(unittest.TestCase):
    """Integration tests for POST /api/resource/history/query endpoint."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_missing_start_date(self):
        """Missing start_date should return 400."""
        response = self.client.post(
            '/api/resource/history/query',
            json={'end_date': '2024-01-31'},
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('start_date', data['error']['message'])

    def test_missing_end_date(self):
        """Missing end_date should return 400."""
        response = self.client.post(
            '/api/resource/history/query',
            json={'start_date': '2024-01-01'},
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('end_date', data['error']['message'])

    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_successful_query(self, mock_query):
        """Successful query should return query_id, summary, and detail."""
        mock_query.return_value = {
            'query_id': 'abc123',
            'summary': {
                'kpi': {'ou_pct': 80.0, 'machine_count': 10},
                'trend': [{'date': '2024-01-01', 'ou_pct': 80.0}],
                'heatmap': [{'workcenter': 'WC01', 'date': '2024-01-01', 'ou_pct': 80.0}],
                'workcenter_comparison': [{'workcenter': 'WC01', 'ou_pct': 80.0}],
            },
            'detail': {
                'data': [{'workcenter': 'WC01', 'ou_pct': 80.0}],
                'total': 1,
                'truncated': False,
                'max_records': None,
            },
        }

        response = self.client.post(
            '/api/resource/history/query',
            json={'start_date': '2024-01-01', 'end_date': '2024-01-07'},
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('query_id', data['data'])
        self.assertIn('summary', data['data'])
        self.assertIn('detail', data['data'])
        self.assertIn('kpi', data['data']['summary'])
        self.assertIn('trend', data['data']['summary'])

    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_query_with_filters(self, mock_query):
        """Query with filters should pass them to service."""
        mock_query.return_value = {
            'query_id': 'abc123',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }

        response = self.client.post(
            '/api/resource/history/query',
            json={
                'start_date': '2024-01-01',
                'end_date': '2024-01-07',
                'granularity': 'week',
                'workcenter_groups': ['焊接_DB', '成型'],
                'families': ['FAM01', 'FAM02'],
                'is_production': True,
                'is_key': True,
            },
        )

        self.assertEqual(response.status_code, 200)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args[1]
        self.assertEqual(call_kwargs['granularity'], 'week')
        self.assertEqual(call_kwargs['workcenter_groups'], ['焊接_DB', '成型'])
        self.assertEqual(call_kwargs['families'], ['FAM01', 'FAM02'])
        self.assertTrue(call_kwargs['is_production'])
        self.assertTrue(call_kwargs['is_key'])

    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
        return_value=(None, None),
    )
    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_query_bootstrap_render_failure_returns_500(self, mock_query, _mock_canonical):
        """Bootstrap render failure from service should surface as route failure."""
        mock_query.side_effect = RuntimeError('bootstrap render failure: apply_view returned None')

        response = self.client.post(
            '/api/resource/history/query',
            json={'start_date': '2024-01-01', 'end_date': '2024-01-07'},
        )

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertFalse(data['success'])


class TestResourceHistoryViewAPI(unittest.TestCase):
    """Integration tests for GET /api/resource/history/view endpoint."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_missing_query_id(self):
        """Missing query_id should return 400."""
        response = self.client.get('/api/resource/history/view')

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('query_id', data['error']['message'])

    @patch('mes_dashboard.routes.resource_history_routes.apply_view')
    def test_cache_expired(self, mock_view):
        """Expired cache should return 410."""
        mock_view.return_value = None

        response = self.client.get('/api/resource/history/view?query_id=abc123')

        self.assertEqual(response.status_code, 410)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], 'CACHE_EXPIRED')

    @patch('mes_dashboard.routes.resource_history_routes.apply_view')
    def test_successful_view(self, mock_view):
        """Successful view should return summary and detail."""
        mock_view.return_value = {
            'summary': {
                'kpi': {'ou_pct': 80.0},
                'trend': [],
                'heatmap': [],
                'workcenter_comparison': [],
            },
            'detail': {
                'data': [{'workcenter': 'WC01', 'ou_pct': 80.0}],
                'total': 1,
                'truncated': False,
                'max_records': None,
            },
        }

        response = self.client.get(
            '/api/resource/history/view?query_id=abc123&granularity=week'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('summary', data['data'])
        self.assertIn('detail', data['data'])


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
