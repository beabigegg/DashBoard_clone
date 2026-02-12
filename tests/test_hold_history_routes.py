# -*- coding: utf-8 -*-
"""Unit tests for Hold History API routes."""

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
        with self.client.session_transaction() as sess:
            sess['admin'] = {'displayName': 'Test Admin', 'employeeNo': 'A001'}

        response = self.client.get('/hold-history')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/static/dist/hold-history.js', response.data)

    @patch('mes_dashboard.routes.hold_history_routes.os.path.exists', return_value=False)
    def test_hold_history_page_returns_403_without_admin(self, _mock_exists):
        response = self.client.get('/hold-history')
        self.assertEqual(response.status_code, 403)


class TestHoldHistoryTrendRoute(TestHoldHistoryRoutesBase):
    """Test GET /api/hold-history/trend endpoint."""

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_trend')
    def test_trend_passes_date_range(self, mock_trend):
        mock_trend.return_value = {
            'days': [
                {
                    'date': '2026-02-01',
                    'quality': {'holdQty': 10, 'newHoldQty': 2, 'releaseQty': 3, 'futureHoldQty': 1},
                    'non_quality': {'holdQty': 5, 'newHoldQty': 1, 'releaseQty': 2, 'futureHoldQty': 0},
                    'all': {'holdQty': 15, 'newHoldQty': 3, 'releaseQty': 5, 'futureHoldQty': 1},
                }
            ]
        }

        response = self.client.get('/api/hold-history/trend?start_date=2026-02-01&end_date=2026-02-07')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('days', payload['data'])
        mock_trend.assert_called_once_with('2026-02-01', '2026-02-07')

    def test_trend_invalid_date_returns_400(self):
        response = self.client.get('/api/hold-history/trend?start_date=2026/02/01&end_date=2026-02-07')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_trend')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 8))
    def test_trend_rate_limited_returns_429(self, _mock_limit, mock_service):
        response = self.client.get('/api/hold-history/trend?start_date=2026-02-01&end_date=2026-02-07')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '8')
        mock_service.assert_not_called()


class TestHoldHistoryReasonParetoRoute(TestHoldHistoryRoutesBase):
    """Test GET /api/hold-history/reason-pareto endpoint."""

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_reason_pareto')
    def test_reason_pareto_passes_hold_type_and_record_type(self, mock_service):
        mock_service.return_value = {'items': []}

        response = self.client.get(
            '/api/hold-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07'
            '&hold_type=non-quality&record_type=on_hold'
        )

        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with('2026-02-01', '2026-02-07', 'non-quality', 'on_hold')

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_reason_pareto')
    def test_reason_pareto_defaults_record_type_to_new(self, mock_service):
        mock_service.return_value = {'items': []}

        response = self.client.get(
            '/api/hold-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07&hold_type=quality'
        )

        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with('2026-02-01', '2026-02-07', 'quality', 'new')

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_reason_pareto')
    def test_reason_pareto_multi_record_type(self, mock_service):
        mock_service.return_value = {'items': []}

        response = self.client.get(
            '/api/hold-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07'
            '&hold_type=quality&record_type=on_hold,released'
        )

        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with('2026-02-01', '2026-02-07', 'quality', 'on_hold,released')

    def test_reason_pareto_invalid_record_type_returns_400(self):
        response = self.client.get(
            '/api/hold-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07&record_type=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_reason_pareto_partial_invalid_record_type_returns_400(self):
        response = self.client.get(
            '/api/hold-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07&record_type=on_hold,bogus'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])


class TestHoldHistoryDurationRoute(TestHoldHistoryRoutesBase):
    """Test GET /api/hold-history/duration endpoint."""

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_duration')
    def test_duration_failure_returns_500(self, mock_service):
        mock_service.return_value = None

        response = self.client.get('/api/hold-history/duration?start_date=2026-02-01&end_date=2026-02-07')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload['success'])

    def test_duration_invalid_hold_type(self):
        response = self.client.get(
            '/api/hold-history/duration?start_date=2026-02-01&end_date=2026-02-07&hold_type=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_duration')
    def test_duration_passes_record_type(self, mock_service):
        mock_service.return_value = {'items': []}

        response = self.client.get(
            '/api/hold-history/duration?start_date=2026-02-01&end_date=2026-02-07&record_type=released'
        )

        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with('2026-02-01', '2026-02-07', 'quality', 'released')

    def test_duration_invalid_record_type_returns_400(self):
        response = self.client.get(
            '/api/hold-history/duration?start_date=2026-02-01&end_date=2026-02-07&record_type=bogus'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])


class TestHoldHistoryListRoute(TestHoldHistoryRoutesBase):
    """Test GET /api/hold-history/list endpoint."""

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_list')
    def test_list_caps_per_page_and_sets_page_floor(self, mock_service):
        mock_service.return_value = {
            'items': [],
            'pagination': {'page': 1, 'perPage': 200, 'total': 0, 'totalPages': 1},
        }

        response = self.client.get(
            '/api/hold-history/list?start_date=2026-02-01&end_date=2026-02-07'
            '&hold_type=all&page=0&per_page=500&reason=品質確認'
        )

        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with(
            start_date='2026-02-01',
            end_date='2026-02-07',
            hold_type='all',
            reason='品質確認',
            record_type='new',
            duration_range=None,
            page=1,
            per_page=200,
        )

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_list')
    def test_list_passes_duration_range(self, mock_service):
        mock_service.return_value = {
            'items': [],
            'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
        }

        response = self.client.get(
            '/api/hold-history/list?start_date=2026-02-01&end_date=2026-02-07&duration_range=<4h'
        )

        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with(
            start_date='2026-02-01',
            end_date='2026-02-07',
            hold_type='quality',
            reason=None,
            record_type='new',
            duration_range='<4h',
            page=1,
            per_page=50,
        )

    def test_list_invalid_duration_range_returns_400(self):
        response = self.client.get(
            '/api/hold-history/list?start_date=2026-02-01&end_date=2026-02-07&duration_range=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.get_hold_history_list')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
    def test_list_rate_limited_returns_429(self, _mock_limit, mock_service):
        response = self.client.get('/api/hold-history/list?start_date=2026-02-01&end_date=2026-02-07')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '5')
        mock_service.assert_not_called()
