# -*- coding: utf-8 -*-
"""Unit tests for Hold Detail API routes.

Tests the Hold Detail API endpoints in hold_routes.py.
"""

import unittest
from unittest.mock import patch
import json

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class TestHoldRoutesBase(unittest.TestCase):
    """Base class for Hold routes tests."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()


class TestHoldDetailPageRoute(TestHoldRoutesBase):
    """Test GET /hold-detail page route."""

    def setUp(self):
        super().setUp()
        self.app.config['PORTAL_SPA_ENABLED'] = True

    def test_hold_detail_page_requires_reason(self):
        """SPA mode should single-hop redirect missing reason to canonical shell overview."""
        response = self.client.get('/hold-detail', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/hold-overview'))

    def test_hold_detail_page_requires_reason_non_spa_mode(self):
        """Non-SPA mode should keep legacy overview redirect behavior."""
        self.app.config['PORTAL_SPA_ENABLED'] = False
        response = self.client.get('/hold-detail', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/hold-overview'))

    def test_hold_detail_page_requires_reason_has_single_redirect_hop_in_spa_mode(self):
        """Follow-redirect flow should complete with exactly one redirect hop."""
        response = self.client.get('/hold-detail', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.history), 1)
        self.assertTrue(response.history[0].location.endswith('/portal-shell/hold-overview'))

    def test_hold_detail_page_with_reason(self):
        """GET /hold-detail?reason=xxx should redirect to canonical shell route."""
        response = self.client.get('/hold-detail?reason=YieldLimit', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/hold-detail?reason=YieldLimit'))

    def test_hold_detail_page_includes_vite_entry(self):
        """Direct entry should be redirected to canonical shell host page."""
        response = self.client.get('/hold-detail?reason=YieldLimit', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/portal-shell/hold-detail?reason=YieldLimit', response.location)


class TestHoldDetailSummaryRoute(TestHoldRoutesBase):
    """Test GET /api/wip/hold-detail/summary endpoint."""

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_summary')
    def test_returns_success_with_data(self, mock_get_summary):
        """Should return success=True with summary data."""
        mock_get_summary.return_value = {
            'totalLots': 128,
            'totalQty': 25600,
            'avgAge': 2.3,
            'maxAge': 15.0,
            'workcenterCount': 8
        }

        response = self.client.get('/api/wip/hold-detail/summary?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['totalLots'], 128)
        self.assertEqual(data['data']['totalQty'], 25600)
        self.assertEqual(data['data']['avgAge'], 2.3)
        self.assertEqual(data['data']['maxAge'], 15.0)
        self.assertEqual(data['data']['workcenterCount'], 8)

    def test_returns_error_without_reason(self):
        """Should return 400 when reason is missing."""
        response = self.client.get('/api/wip/hold-detail/summary')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('reason', data['error']['message'])

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_summary')
    def test_returns_error_on_failure(self, mock_get_summary):
        """Should return success=False and 500 on failure."""
        mock_get_summary.return_value = None

        response = self.client.get('/api/wip/hold-detail/summary?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_summary')
    def test_passes_include_dummy(self, mock_get_summary):
        """Should pass include_dummy flag to summary service."""
        mock_get_summary.return_value = {
            'totalLots': 0,
            'totalQty': 0,
            'avgAge': 0,
            'maxAge': 0,
            'workcenterCount': 0,
        }

        self.client.get('/api/wip/hold-detail/summary?reason=YieldLimit&include_dummy=true')

        mock_get_summary.assert_called_once()
        kw = mock_get_summary.call_args.kwargs
        self.assertEqual(kw['reason'], 'YieldLimit')
        self.assertTrue(kw['include_dummy'])


class TestHoldDetailDistributionRoute(TestHoldRoutesBase):
    """Test GET /api/wip/hold-detail/distribution endpoint."""

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_distribution')
    def test_returns_success_with_distribution(self, mock_get_dist):
        """Should return success=True with distribution data."""
        mock_get_dist.return_value = {
            'byWorkcenter': [
                {'name': 'DA', 'lots': 45, 'qty': 9000, 'percentage': 35.2},
                {'name': 'WB', 'lots': 38, 'qty': 7600, 'percentage': 29.7}
            ],
            'byPackage': [
                {'name': 'DIP-B', 'lots': 50, 'qty': 10000, 'percentage': 39.1},
                {'name': 'QFN', 'lots': 35, 'qty': 7000, 'percentage': 27.3}
            ],
            'byAge': [
                {'range': '0-1', 'label': '0-1天', 'lots': 45, 'qty': 9000, 'percentage': 35.2},
                {'range': '1-3', 'label': '1-3天', 'lots': 38, 'qty': 7600, 'percentage': 29.7},
                {'range': '3-7', 'label': '3-7天', 'lots': 30, 'qty': 6000, 'percentage': 23.4},
                {'range': '7+', 'label': '7+天', 'lots': 15, 'qty': 3000, 'percentage': 11.7}
            ]
        }

        response = self.client.get('/api/wip/hold-detail/distribution?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('byWorkcenter', data['data'])
        self.assertIn('byPackage', data['data'])
        self.assertIn('byAge', data['data'])
        self.assertEqual(len(data['data']['byWorkcenter']), 2)
        self.assertEqual(len(data['data']['byAge']), 4)

    def test_returns_error_without_reason(self):
        """Should return 400 when reason is missing."""
        response = self.client.get('/api/wip/hold-detail/distribution')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_distribution')
    def test_returns_error_on_failure(self, mock_get_dist):
        """Should return success=False and 500 on failure."""
        mock_get_dist.return_value = None

        response = self.client.get('/api/wip/hold-detail/distribution?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_distribution')
    def test_passes_include_dummy(self, mock_get_dist):
        """Should pass include_dummy flag to distribution service."""
        mock_get_dist.return_value = {
            'byWorkcenter': [],
            'byPackage': [],
            'byAge': [],
        }

        self.client.get('/api/wip/hold-detail/distribution?reason=YieldLimit&include_dummy=1')

        mock_get_dist.assert_called_once()
        kw = mock_get_dist.call_args.kwargs
        self.assertEqual(kw['reason'], 'YieldLimit')
        self.assertTrue(kw['include_dummy'])


class TestHoldDetailLotsRoute(TestHoldRoutesBase):
    """Test GET /api/wip/hold-detail/lots endpoint."""

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_returns_success_with_lots(self, mock_get_lots):
        """Should return success=True with lots data."""
        mock_get_lots.return_value = {
            'lots': [
                {
                    'lotId': 'L001',
                    'workorder': 'WO123',
                    'qty': 200,
                    'package': 'DIP-B',
                    'workcenter': 'DA',
                    'spec': 'S01',
                    'age': 2.3,
                    'holdBy': 'EMP01',
                    'dept': 'QC',
                    'holdComment': 'Yield below threshold'
                }
            ],
            'pagination': {
                'page': 1,
                'perPage': 50,
                'total': 128,
                'totalPages': 3
            },
            'filters': {
                'workcenter': None,
                'package': None,
                'ageRange': None
            }
        }

        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('lots', data['data'])
        self.assertIn('pagination', data['data'])
        self.assertIn('filters', data['data'])
        self.assertEqual(len(data['data']['lots']), 1)
        self.assertEqual(data['data']['pagination']['total'], 128)

    def test_returns_error_without_reason(self):
        """Should return 400 when reason is missing."""
        response = self.client.get('/api/wip/hold-detail/lots')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_passes_filter_parameters(self, mock_get_lots):
        """Should pass filter parameters to service function."""
        mock_get_lots.return_value = {
            'lots': [],
            'pagination': {'page': 2, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': 'DA', 'package': 'DIP-B', 'ageRange': '1-3'}
        }

        response = self.client.get(
            '/api/wip/hold-detail/lots?reason=YieldLimit&workcenter=DA&package=DIP-B&age_range=1-3&page=2'
        )

        mock_get_lots.assert_called_once()
        kw = mock_get_lots.call_args.kwargs
        self.assertEqual(kw['reason'], 'YieldLimit')
        self.assertEqual(kw['workcenter'], 'DA')
        self.assertEqual(kw['package'], 'DIP-B')
        self.assertEqual(kw['age_range'], '1-3')
        self.assertFalse(kw['include_dummy'])
        self.assertEqual(kw['page'], 2)
        self.assertEqual(kw['page_size'], 50)

    def test_validates_age_range_parameter(self):
        """Should return 400 for invalid age_range."""
        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit&age_range=invalid')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('age_range', data['error']['message'])

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_limits_per_page_to_200(self, mock_get_lots):
        """Per page should be capped at 200."""
        mock_get_lots.return_value = {
            'lots': [],
            'pagination': {'page': 1, 'perPage': 200, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': None}
        }

        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit&per_page=500')

        call_args = mock_get_lots.call_args
        self.assertEqual(call_args.kwargs['page_size'], 200)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_handles_page_less_than_one(self, mock_get_lots):
        """Page number less than 1 should be set to 1."""
        mock_get_lots.return_value = {
            'lots': [],
            'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': None}
        }

        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit&page=0')

        call_args = mock_get_lots.call_args
        self.assertEqual(call_args.kwargs['page'], 1)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_handles_invalid_page_type(self, mock_get_lots):
        mock_get_lots.return_value = {
            'lots': [],
            'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': None}
        }

        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit&page=abc')
        self.assertEqual(response.status_code, 200)

        call_args = mock_get_lots.call_args
        self.assertEqual(call_args.kwargs['page'], 1)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_handles_invalid_per_page_type(self, mock_get_lots):
        mock_get_lots.return_value = {
            'lots': [],
            'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': None}
        }

        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit&per_page=abc')
        self.assertEqual(response.status_code, 200)

        call_args = mock_get_lots.call_args
        self.assertEqual(call_args.kwargs['page_size'], 50)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_returns_error_on_failure(self, mock_get_lots):
        """Should return success=False and 500 on failure."""
        mock_get_lots.return_value = None

        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 4))
    def test_lots_rate_limited_returns_429(self, _mock_limit, mock_get_lots):
        """Rate-limited lots requests should return 429."""
        response = self.client.get('/api/wip/hold-detail/lots?reason=YieldLimit')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], 'TOO_MANY_REQUESTS')
        mock_get_lots.assert_not_called()


class TestHoldDetailAgeRangeFilters(TestHoldRoutesBase):
    """Test age range filter validation."""

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_valid_age_range_0_1(self, mock_get_lots):
        """Should accept 0-1 as valid age_range."""
        mock_get_lots.return_value = {
            'lots': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': '0-1'}
        }
        response = self.client.get('/api/wip/hold-detail/lots?reason=Test&age_range=0-1')
        self.assertEqual(response.status_code, 200)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_valid_age_range_1_3(self, mock_get_lots):
        """Should accept 1-3 as valid age_range."""
        mock_get_lots.return_value = {
            'lots': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': '1-3'}
        }
        response = self.client.get('/api/wip/hold-detail/lots?reason=Test&age_range=1-3')
        self.assertEqual(response.status_code, 200)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_valid_age_range_3_7(self, mock_get_lots):
        """Should accept 3-7 as valid age_range."""
        mock_get_lots.return_value = {
            'lots': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': '3-7'}
        }
        response = self.client.get('/api/wip/hold-detail/lots?reason=Test&age_range=3-7')
        self.assertEqual(response.status_code, 200)

    @patch('mes_dashboard.routes.hold_routes.get_hold_detail_lots')
    def test_valid_age_range_7_plus(self, mock_get_lots):
        """Should accept 7+ as valid age_range."""
        mock_get_lots.return_value = {
            'lots': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {'workcenter': None, 'package': None, 'ageRange': '7+'}
        }
        response = self.client.get('/api/wip/hold-detail/lots?reason=Test&age_range=7%2B')
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
