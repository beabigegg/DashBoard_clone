# -*- coding: utf-8 -*-
"""Unit tests for WIP API routes.

Tests the WIP API endpoints in wip_routes.py.
"""

import unittest
from unittest.mock import patch
import json

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class TestWipRoutesBase(unittest.TestCase):
    """Base class for WIP routes tests."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()


class TestOverviewSummaryRoute(TestWipRoutesBase):
    """Test GET /api/wip/overview/summary endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_returns_success_with_data(self, mock_get_summary):
        """Should return success=True with summary data."""
        mock_get_summary.return_value = {
            'totalLots': 9073,
            'totalQtyPcs': 858878718,
            'byWipStatus': {
                'run': {'lots': 8000, 'qtyPcs': 800000000},
                'queue': {'lots': 953, 'qtyPcs': 504645323},
                'hold': {'lots': 120, 'qtyPcs': 8213395}
            },
            'dataUpdateDate': '2026-01-26 19:18:29'
        }

        response = self.client.get('/api/wip/overview/summary')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['totalLots'], 9073)
        self.assertEqual(data['data']['byWipStatus']['hold']['lots'], 120)

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_returns_error_on_failure(self, mock_get_summary):
        """Should return success=False and 500 on failure."""
        mock_get_summary.return_value = None

        response = self.client.get('/api/wip/overview/summary')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_passes_filters_and_include_dummy(self, mock_get_summary):
        """Should pass overview filter params to service layer."""
        mock_get_summary.return_value = {
            'totalLots': 0,
            'totalQtyPcs': 0,
            'byWipStatus': {},
            'dataUpdateDate': None,
        }

        self.client.get(
            '/api/wip/overview/summary?workorder=WO1&lotid=L1&package=SOT-23'
            '&type=PJA&firstname=WF001&waferdesc=SiC&include_dummy=true'
        )

        mock_get_summary.assert_called_once_with(
            include_dummy=True,
            workorder='WO1',
            lotid='L1',
            package='SOT-23',
            pj_type='PJA',
            firstname='WF001',
            waferdesc='SiC',
        )


class TestOverviewMatrixRoute(TestWipRoutesBase):
    """Test GET /api/wip/overview/matrix endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_wip_matrix')
    def test_returns_success_with_matrix(self, mock_get_matrix):
        """Should return success=True with matrix data."""
        mock_get_matrix.return_value = {
            'workcenters': ['切割', '焊接_DB'],
            'packages': ['SOT-23', 'SOD-323'],
            'matrix': {'切割': {'SOT-23': 50000000}},
            'workcenter_totals': {'切割': 50000000},
            'package_totals': {'SOT-23': 50000000},
            'grand_total': 50000000
        }

        response = self.client.get('/api/wip/overview/matrix')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('workcenters', data['data'])
        self.assertIn('packages', data['data'])
        self.assertIn('matrix', data['data'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_matrix')
    def test_returns_error_on_failure(self, mock_get_matrix):
        """Should return success=False and 500 on failure."""
        mock_get_matrix.return_value = None

        response = self.client.get('/api/wip/overview/matrix')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])

    def test_rejects_invalid_status(self):
        """Invalid status should return 400."""
        response = self.client.get('/api/wip/overview/matrix?status=INVALID')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('Invalid status', data['error'])

    def test_rejects_invalid_hold_type(self):
        """Invalid hold_type should return 400."""
        response = self.client.get('/api/wip/overview/matrix?status=HOLD&hold_type=oops')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('Invalid hold_type', data['error'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_matrix')
    def test_passes_filters_to_service(self, mock_get_matrix):
        """Should pass overview matrix filters to service layer."""
        mock_get_matrix.return_value = {
            'workcenters': [],
            'packages': [],
            'matrix': {},
            'workcenter_totals': {},
            'package_totals': {},
            'grand_total': 0,
        }

        self.client.get(
            '/api/wip/overview/matrix?workorder=WO1&lotid=L1&package=SOT-23&type=PJA'
            '&firstname=WF001&waferdesc=SiC&status=RUN&include_dummy=1'
        )

        mock_get_matrix.assert_called_once_with(
            include_dummy=True,
            workorder='WO1',
            lotid='L1',
            status='RUN',
            hold_type=None,
            package='SOT-23',
            pj_type='PJA',
            firstname='WF001',
            waferdesc='SiC',
        )


class TestOverviewHoldRoute(TestWipRoutesBase):
    """Test GET /api/wip/overview/hold endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_wip_hold_summary')
    def test_returns_success_with_hold_items(self, mock_get_hold):
        """Should return success=True with hold items."""
        mock_get_hold.return_value = {
            'items': [
                {'reason': '特殊需求管控', 'lots': 44, 'qty': 4235060},
                {'reason': 'YieldLimit', 'lots': 21, 'qty': 1084443}
            ]
        }

        response = self.client.get('/api/wip/overview/hold')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']['items']), 2)

    @patch('mes_dashboard.routes.wip_routes.get_wip_hold_summary')
    def test_returns_error_on_failure(self, mock_get_hold):
        """Should return success=False and 500 on failure."""
        mock_get_hold.return_value = None

        response = self.client.get('/api/wip/overview/hold')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_hold_summary')
    def test_passes_filters_and_include_dummy(self, mock_get_hold):
        """Should pass hold filter params to service layer."""
        mock_get_hold.return_value = {'items': []}

        self.client.get(
            '/api/wip/overview/hold?workorder=WO1&lotid=L1&package=SOT-23&type=PJA'
            '&firstname=WF001&waferdesc=SiC&include_dummy=1'
        )

        mock_get_hold.assert_called_once_with(
            include_dummy=True,
            workorder='WO1',
            lotid='L1',
            package='SOT-23',
            pj_type='PJA',
            firstname='WF001',
            waferdesc='SiC',
        )


class TestDetailRoute(TestWipRoutesBase):
    """Test GET /api/wip/detail/<workcenter> endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_returns_success_with_detail(self, mock_get_detail):
        """Should return success=True with detail data."""
        mock_get_detail.return_value = {
            'workcenter': '焊接_DB',
            'summary': {
                'total_lots': 859,
                'on_equipment_lots': 312,
                'waiting_lots': 547,
                'hold_lots': 15
            },
            'specs': ['Spec1', 'Spec2'],
            'lots': [
                {'lot_id': 'GA25102485', 'equipment': 'GSMP-0054',
                 'status': 'ACTIVE', 'hold_reason': None,
                 'qty': 750, 'package': 'SOT-23', 'spec': 'Spec1'}
            ],
            'pagination': {
                'page': 1, 'page_size': 100,
                'total_count': 859, 'total_pages': 9
            },
            'sys_date': '2026-01-26 19:18:29'
        }

        response = self.client.get('/api/wip/detail/焊接_DB')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['workcenter'], '焊接_DB')
        self.assertIn('summary', data['data'])
        self.assertIn('lots', data['data'])
        self.assertIn('pagination', data['data'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_passes_query_parameters(self, mock_get_detail):
        """Should pass query parameters to service function."""
        mock_get_detail.return_value = {
            'workcenter': '焊接_DB',
            'summary': {'total_lots': 100, 'on_equipment_lots': 50,
                        'waiting_lots': 50, 'hold_lots': 0},
            'specs': [],
            'lots': [],
            'pagination': {'page': 2, 'page_size': 50,
                           'total_count': 100, 'total_pages': 2},
            'sys_date': None
        }

        response = self.client.get(
            '/api/wip/detail/焊接_DB?package=SOT-23&type=PJA&firstname=WF001&waferdesc=SiC'
            '&status=RUN&page=2&page_size=50'
        )

        mock_get_detail.assert_called_once_with(
            workcenter='焊接_DB',
            package='SOT-23',
            pj_type='PJA',
            firstname='WF001',
            waferdesc='SiC',
            status='RUN',
            hold_type=None,
            workorder=None,
            lotid=None,
            include_dummy=False,
            page=2,
            page_size=50
        )

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_limits_page_size_to_500(self, mock_get_detail):
        """Page size should be capped at 500."""
        mock_get_detail.return_value = {
            'workcenter': '切割',
            'summary': {'total_lots': 0, 'on_equipment_lots': 0,
                        'waiting_lots': 0, 'hold_lots': 0},
            'specs': [],
            'lots': [],
            'pagination': {'page': 1, 'page_size': 500,
                           'total_count': 0, 'total_pages': 1},
            'sys_date': None
        }

        response = self.client.get('/api/wip/detail/切割?page_size=1000')

        # Should be capped to 500
        call_args = mock_get_detail.call_args
        self.assertEqual(call_args.kwargs['page_size'], 500)

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_handles_page_less_than_one(self, mock_get_detail):
        """Page number less than 1 should be set to 1."""
        mock_get_detail.return_value = {
            'workcenter': '切割',
            'summary': {'total_lots': 0, 'on_equipment_lots': 0,
                        'waiting_lots': 0, 'hold_lots': 0},
            'specs': [],
            'lots': [],
            'pagination': {'page': 1, 'page_size': 100,
                           'total_count': 0, 'total_pages': 1},
            'sys_date': None
        }

        response = self.client.get('/api/wip/detail/切割?page=0')

        call_args = mock_get_detail.call_args
        self.assertEqual(call_args.kwargs['page'], 1)

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_handles_page_size_less_than_one(self, mock_get_detail):
        """Page size less than 1 should be set to 1."""
        mock_get_detail.return_value = {
            'workcenter': '切割',
            'summary': {'total_lots': 0, 'on_equipment_lots': 0,
                        'waiting_lots': 0, 'hold_lots': 0},
            'specs': [],
            'lots': [],
            'pagination': {'page': 1, 'page_size': 1,
                           'total_count': 0, 'total_pages': 1},
            'sys_date': None
        }

        self.client.get('/api/wip/detail/切割?page_size=0')

        call_args = mock_get_detail.call_args
        self.assertEqual(call_args.kwargs['page_size'], 1)

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    def test_returns_error_on_failure(self, mock_get_detail):
        """Should return success=False and 500 on failure."""
        mock_get_detail.return_value = None

        response = self.client.get('/api/wip/detail/不存在的工站')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])

    def test_rejects_invalid_status(self):
        """Invalid status should return 400."""
        response = self.client.get('/api/wip/detail/焊接_DB?status=INVALID')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('Invalid status', data['error'])

    def test_rejects_invalid_hold_type(self):
        """Invalid hold_type should return 400."""
        response = self.client.get('/api/wip/detail/焊接_DB?status=HOLD&hold_type=oops')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('Invalid hold_type', data['error'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_detail')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 7))
    def test_detail_rate_limited_returns_429(self, _mock_limit, mock_get_detail):
        """Rate-limited detail requests should return 429."""
        response = self.client.get('/api/wip/detail/焊接_DB')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], 'TOO_MANY_REQUESTS')
        mock_get_detail.assert_not_called()


class TestMetaWorkcentersRoute(TestWipRoutesBase):
    """Test GET /api/wip/meta/workcenters endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_workcenters')
    def test_returns_success_with_workcenters(self, mock_get_wcs):
        """Should return success=True with workcenters list."""
        mock_get_wcs.return_value = [
            {'name': '切割', 'lot_count': 1377},
            {'name': '焊接_DB', 'lot_count': 859}
        ]

        response = self.client.get('/api/wip/meta/workcenters')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 2)
        self.assertEqual(data['data'][0]['name'], '切割')

    @patch('mes_dashboard.routes.wip_routes.get_workcenters')
    def test_returns_error_on_failure(self, mock_get_wcs):
        """Should return success=False and 500 on failure."""
        mock_get_wcs.return_value = None

        response = self.client.get('/api/wip/meta/workcenters')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])


class TestMetaPackagesRoute(TestWipRoutesBase):
    """Test GET /api/wip/meta/packages endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_packages')
    def test_returns_success_with_packages(self, mock_get_pkgs):
        """Should return success=True with packages list."""
        mock_get_pkgs.return_value = [
            {'name': 'SOT-23', 'lot_count': 2234},
            {'name': 'SOD-323', 'lot_count': 1392}
        ]

        response = self.client.get('/api/wip/meta/packages')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 2)
        self.assertEqual(data['data'][0]['name'], 'SOT-23')

    @patch('mes_dashboard.routes.wip_routes.get_packages')
    def test_returns_error_on_failure(self, mock_get_pkgs):
        """Should return success=False and 500 on failure."""
        mock_get_pkgs.return_value = None

        response = self.client.get('/api/wip/meta/packages')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])


class TestMetaFilterOptionsRoute(TestWipRoutesBase):
    """Test GET /api/wip/meta/filter-options endpoint."""

    @patch('mes_dashboard.routes.wip_routes.get_wip_filter_options')
    def test_returns_success_with_options(self, mock_get_options):
        mock_get_options.return_value = {
            'workorders': ['WO1'],
            'lotids': ['LOT1'],
            'packages': ['PKG1'],
            'types': ['TYPE1'],
            'firstnames': ['WF001'],
            'waferdescs': ['SiC'],
        }

        response = self.client.get('/api/wip/meta/filter-options')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['workorders'], ['WO1'])
        self.assertEqual(data['data']['waferdescs'], ['SiC'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_filter_options')
    def test_passes_include_dummy_flag(self, mock_get_options):
        mock_get_options.return_value = {
            'workorders': [],
            'lotids': [],
            'packages': [],
            'types': [],
            'firstnames': [],
            'waferdescs': [],
        }

        self.client.get('/api/wip/meta/filter-options?include_dummy=true')
        mock_get_options.assert_called_once_with(
            include_dummy=True,
            workorder=None,
            lotid=None,
            package=None,
            pj_type=None,
            firstname=None,
            waferdesc=None,
        )

    @patch('mes_dashboard.routes.wip_routes.get_wip_filter_options')
    def test_passes_cross_filter_parameters(self, mock_get_options):
        mock_get_options.return_value = {
            'workorders': ['WO1'],
            'lotids': ['LOT1'],
            'packages': ['PKG1'],
            'types': ['TYPE1'],
            'firstnames': ['WF001'],
            'waferdescs': ['SiC'],
        }

        self.client.get(
            '/api/wip/meta/filter-options?workorder=WO1,WO2&lotid=L1&package=PKG1'
            '&type=PJA&firstname=WF001&waferdesc=SiC'
        )

        mock_get_options.assert_called_once_with(
            include_dummy=False,
            workorder='WO1,WO2',
            lotid='L1',
            package='PKG1',
            pj_type='PJA',
            firstname='WF001',
            waferdesc='SiC',
        )

    @patch('mes_dashboard.routes.wip_routes.get_wip_filter_options')
    def test_returns_error_on_failure(self, mock_get_options):
        mock_get_options.return_value = None

        response = self.client.get('/api/wip/meta/filter-options')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])


class TestPageRoutes(TestWipRoutesBase):
    """Test page routes for WIP dashboards."""

    def test_wip_overview_page_exists(self):
        """GET /wip-overview should redirect to canonical shell route."""
        response = self.client.get('/wip-overview', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/wip-overview'))

    def test_wip_detail_page_exists(self):
        """GET /wip-detail should redirect to canonical shell route."""
        response = self.client.get('/wip-detail', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/portal-shell/wip-detail'))

    def test_wip_detail_page_with_workcenter(self):
        """GET /wip-detail?workcenter=xxx should preserve query during redirect."""
        response = self.client.get('/wip-detail?workcenter=焊接_DB', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/portal-shell/wip-detail?workcenter=', response.location)

    def test_old_wip_route_removed(self):
        """GET /wip should return 404 (route removed)."""
        response = self.client.get('/wip')
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
