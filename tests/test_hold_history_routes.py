# -*- coding: utf-8 -*-
"""Unit tests for Hold History API routes (two-phase query/view pattern)."""

import json
import unittest
from unittest.mock import patch

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class TestHoldHistoryRoutesBase(unittest.TestCase):
    """Base class for Hold History route tests."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()


class TestHoldHistoryPageRoute(TestHoldHistoryRoutesBase):
    """Test GET /hold-history page route."""

    @patch('mes_dashboard.routes.hold_history_routes.os.path.exists', return_value=False)
    def test_hold_history_page_includes_vite_entry(self, _mock_exists):
        response = self.client.get('/hold-history', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/hold-history'))

    @patch('mes_dashboard.routes.hold_history_routes.os.path.exists', return_value=False)
    def test_hold_history_page_redirects_without_admin(self, _mock_exists):
        response = self.client.get('/hold-history', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/hold-history'))


class TestHoldHistoryQueryRoute(TestHoldHistoryRoutesBase):
    """Test POST /api/hold-history/query endpoint."""

    def test_query_missing_dates_returns_400(self):
        response = self.client.post(
            '/api/hold-history/query',
            json={'start_date': '2026-02-01'},
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_query_invalid_date_format_returns_400(self):
        response = self.client.post(
            '/api/hold-history/query',
            json={'start_date': '2026/02/01', 'end_date': '2026-02-07'},
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_query_end_before_start_returns_400(self):
        response = self.client.post(
            '/api/hold-history/query',
            json={'start_date': '2026-02-07', 'end_date': '2026-02-01'},
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_query_invalid_record_type_returns_400(self):
        response = self.client.post(
            '/api/hold-history/query',
            json={
                'start_date': '2026-02-01',
                'end_date': '2026-02-07',
                'record_type': 'invalid',
            },
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    def test_query_success(self, mock_exec):
        mock_exec.return_value = {
            'query_id': 'abc123',
            'trend': {'days': []},
            'reason_pareto': {'items': []},
            'duration': {'items': []},
            'list': {'items': [], 'pagination': {}},
        }

        response = self.client.post(
            '/api/hold-history/query',
            json={
                'start_date': '2026-02-01',
                'end_date': '2026-02-07',
                'hold_type': 'quality',
            },
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('query_id', payload['data'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    def test_query_passes_params(self, mock_exec):
        mock_exec.return_value = {'query_id': 'x', 'trend': {}, 'reason_pareto': {}, 'duration': {}, 'list': {}}

        self.client.post(
            '/api/hold-history/query',
            json={
                'start_date': '2026-02-01',
                'end_date': '2026-02-07',
                'hold_type': 'non-quality',
                'record_type': 'on_hold',
            },
        )

        mock_exec.assert_called_once_with(
            start_date='2026-02-01',
            end_date='2026-02-07',
            hold_type='non-quality',
            record_type='on_hold',
        )

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 8))
    def test_query_rate_limited_returns_429(self, _mock_limit, mock_exec):
        response = self.client.post(
            '/api/hold-history/query',
            json={'start_date': '2026-02-01', 'end_date': '2026-02-07'},
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '8')
        mock_exec.assert_not_called()

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    def test_query_bootstrap_render_failure_returns_500(self, mock_exec):
        """Bootstrap render failure from service should surface as route failure."""
        mock_exec.side_effect = RuntimeError('bootstrap render failure: apply_view returned None')

        response = self.client.post(
            '/api/hold-history/query',
            json={'start_date': '2026-02-01', 'end_date': '2026-02-07'},
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload['success'])


class TestHoldHistoryViewRoute(TestHoldHistoryRoutesBase):
    """Test GET /api/hold-history/view endpoint."""

    def test_view_missing_query_id_returns_400(self):
        response = self.client.get('/api/hold-history/view')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        self.assertIn('query_id', payload['error']['message'])

    def test_view_invalid_record_type_returns_400(self):
        response = self.client.get(
            '/api/hold-history/view?query_id=abc123&record_type=bogus'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_view_invalid_duration_range_returns_400(self):
        response = self.client.get(
            '/api/hold-history/view?query_id=abc123&duration_range=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    def test_view_cache_expired_returns_410(self, mock_view):
        mock_view.return_value = None

        response = self.client.get('/api/hold-history/view?query_id=abc123')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 410)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'CACHE_EXPIRED')

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    def test_view_success(self, mock_view):
        mock_view.return_value = {
            'trend': {'days': []},
            'reason_pareto': {'items': []},
            'duration': {'items': []},
            'list': {'items': [], 'pagination': {}},
        }

        response = self.client.get(
            '/api/hold-history/view?query_id=abc123&hold_type=non-quality&reason=品質確認&page=2&per_page=20'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])

        mock_view.assert_called_once_with(
            query_id='abc123',
            hold_type='non-quality',
            reason='品質確認',
            record_type='new',
            duration_range=None,
            page=2,
            per_page=20,
        )

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    def test_view_caps_per_page(self, mock_view):
        mock_view.return_value = {
            'trend': {'days': []},
            'reason_pareto': {'items': []},
            'duration': {'items': []},
            'list': {'items': [], 'pagination': {}},
        }

        self.client.get(
            '/api/hold-history/view?query_id=abc123&page=0&per_page=500'
        )

        call_kwargs = mock_view.call_args[1]
        self.assertEqual(call_kwargs['page'], 1)
        self.assertEqual(call_kwargs['per_page'], 200)

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    def test_view_passes_duration_range(self, mock_view):
        mock_view.return_value = {
            'trend': {'days': []},
            'reason_pareto': {'items': []},
            'duration': {'items': []},
            'list': {'items': [], 'pagination': {}},
        }

        self.client.get(
            '/api/hold-history/view?query_id=abc123&duration_range=<4h'
        )

        call_kwargs = mock_view.call_args[1]
        self.assertEqual(call_kwargs['duration_range'], '<4h')

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
    def test_view_rate_limited_returns_429(self, _mock_limit, mock_view):
        response = self.client.get('/api/hold-history/view?query_id=abc123')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '5')
        mock_view.assert_not_called()
