# -*- coding: utf-8 -*-
"""Unit tests for Hold Overview API routes."""

import json
import unittest
from unittest.mock import patch

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class TestHoldOverviewRoutesBase(unittest.TestCase):
    """Base class for Hold Overview route tests."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()


class TestHoldOverviewPageRoute(TestHoldOverviewRoutesBase):
    """Test GET /hold-overview page route."""

    @patch('mes_dashboard.routes.hold_overview_routes.os.path.exists', return_value=False)
    def test_hold_overview_page_includes_vite_entry(self, _mock_exists):
        response = self.client.get('/hold-overview', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/hold-overview'))

    @patch('mes_dashboard.routes.hold_overview_routes.os.path.exists', return_value=False)
    def test_hold_overview_page_redirects_without_admin(self, _mock_exists):
        response = self.client.get('/hold-overview', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/hold-overview'))


class TestHoldOverviewSummaryRoute(TestHoldOverviewRoutesBase):
    """Test GET /api/hold-overview/summary endpoint."""

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_summary')
    def test_summary_defaults_to_quality(self, mock_service):
        mock_service.return_value = {
            'totalLots': 12,
            'totalQty': 3400,
            'avgAge': 2.5,
            'maxAge': 9.0,
            'workcenterCount': 3,
            'dataUpdateDate': '2026-01-01 08:00:00',
        }

        response = self.client.get('/api/hold-overview/summary')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        mock_service.assert_called_once_with(
            reason=None,
            hold_type='quality',
            include_dummy=False,
        )

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_summary')
    def test_summary_hold_type_all_maps_to_none(self, mock_service):
        mock_service.return_value = {
            'totalLots': 0,
            'totalQty': 0,
            'avgAge': 0,
            'maxAge': 0,
            'workcenterCount': 0,
            'dataUpdateDate': None,
        }

        response = self.client.get('/api/hold-overview/summary?hold_type=all&reason=品質確認')
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with(
            reason='品質確認',
            hold_type=None,
            include_dummy=False,
        )

    def test_summary_invalid_hold_type(self):
        response = self.client.get('/api/hold-overview/summary?hold_type=invalid')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_summary')
    def test_summary_failure_returns_500(self, mock_service):
        mock_service.return_value = None
        response = self.client.get('/api/hold-overview/summary')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload['success'])


class TestHoldOverviewMatrixRoute(TestHoldOverviewRoutesBase):
    """Test GET /api/hold-overview/matrix endpoint."""

    @patch('mes_dashboard.routes.hold_overview_routes.get_wip_matrix')
    def test_matrix_passes_hold_filters(self, mock_service):
        mock_service.return_value = {
            'workcenters': [],
            'packages': [],
            'matrix': {},
            'workcenter_totals': {},
            'package_totals': {},
            'grand_total': 0,
        }

        response = self.client.get('/api/hold-overview/matrix?hold_type=non-quality&reason=特殊需求管控')
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with(
            include_dummy=False,
            status='HOLD',
            hold_type='non-quality',
            reason='特殊需求管控',
        )

    def test_matrix_invalid_hold_type(self):
        response = self.client.get('/api/hold-overview/matrix?hold_type=invalid')
        self.assertEqual(response.status_code, 400)

    @patch('mes_dashboard.routes.hold_overview_routes.get_wip_matrix')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 7))
    def test_matrix_rate_limited_returns_429(self, _mock_limit, mock_service):
        response = self.client.get('/api/hold-overview/matrix')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '7')
        mock_service.assert_not_called()


class TestHoldOverviewTreemapRoute(TestHoldOverviewRoutesBase):
    """Test GET /api/hold-overview/treemap endpoint."""

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_overview_treemap')
    def test_treemap_passes_filters(self, mock_service):
        mock_service.return_value = {'items': []}

        response = self.client.get(
            '/api/hold-overview/treemap?hold_type=quality&reason=品質確認&workcenter=WB&package=QFN'
        )
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with(
            hold_type='quality',
            reason='品質確認',
            workcenter='WB',
            package='QFN',
            include_dummy=False,
        )

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_overview_treemap')
    def test_treemap_failure_returns_500(self, mock_service):
        mock_service.return_value = None
        response = self.client.get('/api/hold-overview/treemap')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload['success'])


class TestHoldOverviewLotsRoute(TestHoldOverviewRoutesBase):
    """Test GET /api/hold-overview/lots endpoint."""

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_passes_all_filters_and_caps_per_page(self, mock_service):
        mock_service.return_value = {
            'lots': [],
            'pagination': {'page': 2, 'perPage': 200, 'total': 0, 'totalPages': 1},
            'filters': {},
        }

        response = self.client.get(
            '/api/hold-overview/lots?hold_type=all&reason=品質確認'
            '&workcenter=WB&package=QFN&treemap_reason=品質確認'
            '&age_range=1-3&page=2&per_page=500'
        )
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once_with(
            reason='品質確認',
            hold_type=None,
            treemap_reason='品質確認',
            workcenter='WB',
            package='QFN',
            age_range='1-3',
            include_dummy=False,
            page=2,
            page_size=200,
        )

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_handles_page_less_than_one(self, mock_service):
        mock_service.return_value = {
            'lots': [],
            'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {},
        }

        response = self.client.get('/api/hold-overview/lots?page=0')
        self.assertEqual(response.status_code, 200)
        call_args = mock_service.call_args
        self.assertEqual(call_args.kwargs['page'], 1)

    def test_lots_invalid_age_range(self):
        response = self.client.get('/api/hold-overview/lots?age_range=invalid')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_lots_invalid_hold_type(self):
        response = self.client.get('/api/hold-overview/lots?hold_type=invalid')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 4))
    def test_lots_rate_limited_returns_429(self, _mock_limit, mock_service):
        response = self.client.get('/api/hold-overview/lots')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '4')
        mock_service.assert_not_called()
