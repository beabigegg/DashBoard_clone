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
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        self.assertIsNone(kw['reason'])
        self.assertIsNone(kw['hold_type'])
        self.assertFalse(kw['include_dummy'])
        self.assertEqual(kw['workflow'], '')
        self.assertEqual(kw['bop'], '')
        self.assertEqual(kw['pj_function'], '')

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
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['reason'], ['品質確認'])
        self.assertIsNone(kw['hold_type'])
        self.assertFalse(kw['include_dummy'])
        self.assertEqual(kw['workflow'], '')
        self.assertEqual(kw['bop'], '')
        self.assertEqual(kw['pj_function'], '')

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
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        self.assertFalse(kw['include_dummy'])
        self.assertEqual(kw['status'], 'HOLD')
        self.assertEqual(kw['hold_type'], 'non-quality')
        self.assertEqual(kw['reason'], ['特殊需求管控'])
        self.assertEqual(kw['workflow'], '')
        self.assertEqual(kw['bop'], '')
        self.assertEqual(kw['pj_function'], '')

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
            reason=['品質確認'],
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
            reason=['品質確認'],
            hold_type=None,
            treemap_reason='品質確認',
            workcenter='WB',
            package='QFN',
            workorder=None,
            lotid=None,
            pj_type=None,
            firstname=None,
            waferdesc=None,
            age_range='1-3',
            include_dummy=False,
            page=2,
            page_size=200,
            workflow='',
            bop='',
            pj_function='',
            export_mode=False,
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


class TestHoldOverviewTreemapEdgeCases(TestHoldOverviewRoutesBase):
    """Treemap edge cases: 3-level nesting, leaf without children, POST reasons, GET compat."""

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_overview_treemap')
    def test_treemap_3_level_nesting(self, mock_service):
        """Treemap with 3-level nested children must pass through intact."""
        three_level = {
            'items': [
                {
                    'name': 'quality',
                    'value': 10,
                    'children': [
                        {
                            'name': '品質確認',
                            'value': 10,
                            'children': [
                                {'name': 'WB', 'value': 5, 'children': []},
                                {'name': 'CP', 'value': 5, 'children': []},
                            ]
                        }
                    ]
                }
            ]
        }
        mock_service.return_value = three_level

        response = self.client.get('/api/hold-overview/treemap')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        children = payload['data']['items'][0]['children'][0]['children']
        self.assertEqual(len(children), 2)
        self.assertEqual(children[0]['name'], 'WB')

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_overview_treemap')
    def test_treemap_leaf_without_children(self, mock_service):
        """Treemap leaf node with no children key must be handled gracefully."""
        leaf_only = {
            'items': [
                {'name': 'quality', 'value': 5}  # no 'children' key
            ]
        }
        mock_service.return_value = leaf_only

        response = self.client.get('/api/hold-overview/treemap')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        # Leaf node is passed through unchanged
        self.assertEqual(payload['data']['items'][0]['name'], 'quality')

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_overview_treemap')
    def test_treemap_post_json_reasons(self, mock_service):
        """POST /api/hold-overview/treemap must accept JSON body with reasons list."""
        mock_service.return_value = {'items': []}

        response = self.client.post(
            '/api/hold-overview/treemap',
            data=json.dumps({'reason': ['品質確認', '特殊需求管控'], 'hold_type': 'quality'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        call_args = mock_service.call_args
        self.assertEqual(call_args.kwargs.get('reason'), ['品質確認', '特殊需求管控'])
        self.assertEqual(call_args.kwargs.get('hold_type'), 'quality')

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_overview_treemap')
    def test_treemap_get_legacy_compat(self, mock_service):
        """GET /api/hold-overview/treemap still works (legacy compatibility)."""
        mock_service.return_value = {'items': []}

        response = self.client.get('/api/hold-overview/treemap?hold_type=quality')
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.data)
        self.assertTrue(payload['success'])


class TestHoldOverviewNonIndexedFilterForwarding(TestHoldOverviewRoutesBase):
    """Regression: workflow/bop/pj_function must be forwarded to the service.

    Bug history: routes silently dropped these params at the request layer; tests
    used assert_called_once_with whitelists that omitted them, so the drop never
    failed CI. These tests verify each non-indexed filter reaches the service
    layer with the exact value supplied in the request.
    """

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_summary')
    def test_summary_forwards_workflow_bop_pj_function(self, mock_service):
        mock_service.return_value = {
            'totalLots': 0, 'totalQty': 0, 'avgAge': 0, 'maxAge': 0,
            'workcenterCount': 0, 'dataUpdateDate': None,
        }
        self.client.get(
            '/api/hold-overview/summary'
            '?workflow=FLOW_A&bop=EAC17&pj_function=FUNC_Y'
        )
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['workflow'], 'FLOW_A')
        self.assertEqual(kw['bop'], 'EAC17')
        self.assertEqual(kw['pj_function'], 'FUNC_Y')

    @patch('mes_dashboard.routes.hold_overview_routes.get_wip_matrix')
    def test_matrix_forwards_workflow_bop_pj_function(self, mock_service):
        mock_service.return_value = {
            'workcenters': [], 'packages': [], 'matrix': {},
            'workcenter_totals': {}, 'package_totals': {}, 'grand_total': 0,
        }
        self.client.get(
            '/api/hold-overview/matrix'
            '?workflow=FLOW_A&bop=EAC17&pj_function=FUNC_Y'
        )
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['workflow'], 'FLOW_A')
        self.assertEqual(kw['bop'], 'EAC17')
        self.assertEqual(kw['pj_function'], 'FUNC_Y')

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_forwards_workflow_bop_pj_function(self, mock_service):
        mock_service.return_value = {
            'lots': [],
            'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            'filters': {},
        }
        self.client.get(
            '/api/hold-overview/lots'
            '?workflow=FLOW_A&bop=EAC17&pj_function=FUNC_Y'
        )
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['workflow'], 'FLOW_A')
        self.assertEqual(kw['bop'], 'EAC17')
        self.assertEqual(kw['pj_function'], 'FUNC_Y')

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_summary')
    def test_summary_forwards_multi_value_csv(self, mock_service):
        """Multi-select CSV values (comma-separated) must reach the service intact."""
        mock_service.return_value = {
            'totalLots': 0, 'totalQty': 0, 'avgAge': 0, 'maxAge': 0,
            'workcenterCount': 0, 'dataUpdateDate': None,
        }
        self.client.get('/api/hold-overview/summary?bop=EAC17,EAC18&workflow=A,B')
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['bop'], 'EAC17,EAC18')
        self.assertEqual(kw['workflow'], 'A,B')


class TestHoldOverviewSummaryPostCompat(TestHoldOverviewRoutesBase):
    """POST /api/hold-overview/summary compatibility tests."""

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_summary')
    def test_summary_post_json_body(self, mock_service):
        """POST with JSON body must work identically to GET with query params."""
        mock_service.return_value = {
            'totalLots': 5,
            'totalQty': 100,
            'avgAge': 2.0,
            'maxAge': 8.0,
            'workcenterCount': 2,
            'dataUpdateDate': None,
        }

        response = self.client.post(
            '/api/hold-overview/summary',
            data=json.dumps({'reason': ['品質確認'], 'hold_type': 'quality'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.data)
        self.assertTrue(payload['success'])


class TestHoldOverviewLotsExportMode(TestHoldOverviewRoutesBase):
    """Export mode tests for GET/POST /api/hold-overview/lots.

    AC-2: export=true fetches full dataset (pagination cap bypassed).
    AC-6: existing paginated behavior unchanged when export is absent/false.
    AC-7: full-data request bounded by HOLD_OVERVIEW_EXPORT_MAX_ROWS env var.
    """

    def _sample_service_result(self, lots_count=2, total=2):
        """Build a minimal valid service return value."""
        lots = [
            {
                'lotId': f'LOT{i}',
                'workorder': f'WO{i}',
                'qty': 100,
                'product': 'PROD-A',
                'package': 'QFN',
                'workcenter': 'WB',
                'holdReason': '品質確認',
                'spec': 'SPEC1',
                'age': 1.0,
                'holdBy': 'user',
                'dept': 'dept',
                'holdComment': None,
                'futureHoldComment': None,
            }
            for i in range(lots_count)
        ]
        return {
            'lots': lots,
            'pagination': {
                'page': 1,
                'perPage': lots_count,
                'total': total,
                'totalPages': 1,
            },
            'filters': {},
        }

    # ------------------------------------------------------------------
    # AC-2 / GET: export=true bypasses per_page clamp, forwards export_mode=True
    # ------------------------------------------------------------------

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_export_bypasses_pagination_get(self, mock_service):
        """GET ?export=true must call service with export_mode=True (not clamped page_size)."""
        mock_service.return_value = self._sample_service_result(lots_count=5000, total=5000)

        response = self.client.get('/api/hold-overview/lots?export=true&per_page=50')
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        # export_mode must be True when export param is true
        self.assertTrue(kw['export_mode'])
        # per_page clamp (max 200) must NOT apply – page_size should exceed 200
        self.assertGreater(kw['page_size'], 200)

    # ------------------------------------------------------------------
    # AC-2 / POST: export=true bypasses per_page clamp, forwards export_mode=True
    # ------------------------------------------------------------------

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_export_bypasses_pagination_post(self, mock_service):
        """POST with export:true must call service with export_mode=True."""
        mock_service.return_value = self._sample_service_result(lots_count=5000, total=5000)

        response = self.client.post(
            '/api/hold-overview/lots',
            data=json.dumps({'export': True, 'per_page': 50}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        self.assertTrue(kw['export_mode'])
        self.assertGreater(kw['page_size'], 200)

    # ------------------------------------------------------------------
    # AC-7: cap enforced even in export mode (HOLD_OVERVIEW_EXPORT_MAX_ROWS)
    # ------------------------------------------------------------------

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_export_capped_at_max_rows(self, mock_service):
        """page_size passed in export mode must be <= HOLD_OVERVIEW_EXPORT_MAX_ROWS."""
        import os
        os.environ['HOLD_OVERVIEW_EXPORT_MAX_ROWS'] = '500'
        try:
            mock_service.return_value = self._sample_service_result(lots_count=500, total=99999)

            response = self.client.get('/api/hold-overview/lots?export=true')
            self.assertEqual(response.status_code, 200)
            mock_service.assert_called_once()
            kw = mock_service.call_args.kwargs
            self.assertTrue(kw['export_mode'])
            self.assertLessEqual(kw['page_size'], 500)
        finally:
            os.environ.pop('HOLD_OVERVIEW_EXPORT_MAX_ROWS', None)

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_export_capped_at_max_rows_post(self, mock_service):
        """POST export mode: page_size must not exceed HOLD_OVERVIEW_EXPORT_MAX_ROWS."""
        import os
        os.environ['HOLD_OVERVIEW_EXPORT_MAX_ROWS'] = '300'
        try:
            mock_service.return_value = self._sample_service_result(lots_count=300, total=50000)

            response = self.client.post(
                '/api/hold-overview/lots',
                data=json.dumps({'export': True}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)
            mock_service.assert_called_once()
            kw = mock_service.call_args.kwargs
            self.assertTrue(kw['export_mode'])
            self.assertLessEqual(kw['page_size'], 300)
        finally:
            os.environ.pop('HOLD_OVERVIEW_EXPORT_MAX_ROWS', None)

    # ------------------------------------------------------------------
    # AC-6: existing paginated behavior unchanged when export is absent
    # ------------------------------------------------------------------

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_normal_pagination_unchanged_get(self, mock_service):
        """GET without export must keep per_page clamp at 200 and export_mode=False."""
        mock_service.return_value = self._sample_service_result()

        response = self.client.get('/api/hold-overview/lots?per_page=500&page=2')
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        # Normal path: per_page clamped to 200
        self.assertEqual(kw['page_size'], 200)
        self.assertEqual(kw['page'], 2)
        # export_mode must be False (or absent)
        self.assertFalse(kw.get('export_mode', False))

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_normal_pagination_unchanged_post(self, mock_service):
        """POST without export must keep per_page clamp at 200 and export_mode=False."""
        mock_service.return_value = self._sample_service_result()

        response = self.client.post(
            '/api/hold-overview/lots',
            data=json.dumps({'per_page': 500, 'page': 3}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['page_size'], 200)
        self.assertEqual(kw['page'], 3)
        self.assertFalse(kw.get('export_mode', False))

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_export_false_does_not_bypass_pagination(self, mock_service):
        """Explicit export=false must behave identically to absent export param."""
        mock_service.return_value = self._sample_service_result()

        response = self.client.get('/api/hold-overview/lots?export=false&per_page=500')
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once()
        kw = mock_service.call_args.kwargs
        self.assertEqual(kw['page_size'], 200)
        self.assertFalse(kw.get('export_mode', False))

    # ------------------------------------------------------------------
    # Filter forwarding in export mode (per-kwarg assertions, AC-2 service fwd)
    # ------------------------------------------------------------------

    @patch('mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots')
    def test_lots_export_forwards_all_filters(self, mock_service):
        """In export mode all filter params must reach the service unchanged."""
        mock_service.return_value = self._sample_service_result()

        response = self.client.get(
            '/api/hold-overview/lots?export=true'
            '&hold_type=quality&reason=品質確認&workcenter=WB&package=QFN'
            '&workflow=FLOW_A&bop=EAC17&pj_function=FUNC_Y'
        )
        self.assertEqual(response.status_code, 200)
        kw = mock_service.call_args.kwargs
        self.assertTrue(kw['export_mode'])
        self.assertEqual(kw['hold_type'], 'quality')
        self.assertEqual(kw['reason'], ['品質確認'])
        self.assertEqual(kw['workcenter'], 'WB')
        self.assertEqual(kw['package'], 'QFN')
        self.assertEqual(kw['workflow'], 'FLOW_A')
        self.assertEqual(kw['bop'], 'EAC17')
        self.assertEqual(kw['pj_function'], 'FUNC_Y')
