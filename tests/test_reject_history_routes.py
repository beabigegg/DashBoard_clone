# -*- coding: utf-8 -*-
"""Unit tests for reject-history routes."""

import json
import os
import unittest
from unittest.mock import patch

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


def _login_as_admin(client):
    with client.session_transaction() as sess:
        sess['admin'] = {'displayName': 'Admin', 'employeeNo': 'A001'}


class TestRejectHistoryRoutesBase(unittest.TestCase):
    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()


class TestRejectHistoryPageRoute(unittest.TestCase):
    @patch.dict(os.environ, {'PORTAL_SPA_ENABLED': 'false'})
    @patch('mes_dashboard.app.os.path.exists', return_value=False)
    def test_reject_history_page_fallback_contains_vite_entry(self, _mock_exists):
        db._ENGINE = None
        app = create_app('testing')
        app.config['TESTING'] = True
        client = app.test_client()
        _login_as_admin(client)

        response = client.get('/reject-history', follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('/static/dist/reject-history.js', html)


class TestRejectHistoryApiRoutes(TestRejectHistoryRoutesBase):
    @patch('mes_dashboard.routes.reject_history_routes.get_filter_options')
    @patch('mes_dashboard.routes.reject_history_routes.cache_get')
    def test_options_uses_cache_hit_without_service_call(self, mock_cache_get, mock_options):
        mock_cache_get.return_value = {
            'success': True,
            'data': {'workcenter_groups': [], 'packages': [], 'reasons': []},
            'meta': {'include_excluded_scrap': False},
        }

        response = self.client.get(
            '/api/reject-history/options?start_date=2026-02-01&end_date=2026-02-07'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('data', payload)
        mock_options.assert_not_called()

    @patch('mes_dashboard.routes.reject_history_routes.get_filter_options')
    def test_options_passes_full_draft_filters(self, mock_options):
        mock_options.return_value = {
            'workcenter_groups': [],
            'packages': [],
            'reasons': [],
            'meta': {},
        }

        response = self.client.get(
            '/api/reject-history/options'
            '?start_date=2026-02-01'
            '&end_date=2026-02-07'
            '&workcenter_groups=WB'
            '&workcenter_groups=TEST'
            '&packages=PKG-A'
            '&reasons=001_A'
            '&reason=002_B'
            '&include_excluded_scrap=true'
            '&exclude_material_scrap=false'
            '&exclude_pb_diode=true'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_options.call_args
        self.assertEqual(kwargs['workcenter_groups'], ['WB', 'TEST'])
        self.assertEqual(kwargs['packages'], ['PKG-A'])
        self.assertEqual(kwargs['reasons'], ['001_A', '002_B'])
        self.assertIs(kwargs['include_excluded_scrap'], True)
        self.assertIs(kwargs['exclude_material_scrap'], False)
        self.assertIs(kwargs['exclude_pb_diode'], True)

    def test_summary_missing_dates_returns_400(self):
        response = self.client.get('/api/reject-history/summary')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_summary_invalid_include_excluded_scrap_returns_400(self):
        response = self.client.get(
            '/api/reject-history/summary?start_date=2026-02-01&end_date=2026-02-07'
            '&include_excluded_scrap=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_summary_invalid_exclude_material_scrap_returns_400(self):
        response = self.client.get(
            '/api/reject-history/summary?start_date=2026-02-01&end_date=2026-02-07'
            '&exclude_material_scrap=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.reject_history_routes.query_summary')
    def test_summary_passes_filters_and_meta(self, mock_summary):
        mock_summary.return_value = {
            'MOVEIN_QTY': 100,
            'REJECT_TOTAL_QTY': 10,
            'DEFECT_QTY': 5,
            'REJECT_RATE_PCT': 10,
            'DEFECT_RATE_PCT': 5,
            'REJECT_SHARE_PCT': 66.7,
            'AFFECTED_LOT_COUNT': 8,
            'AFFECTED_WORKORDER_COUNT': 4,
            'meta': {
                'include_excluded_scrap': False,
                'exclusion_applied': True,
                'excluded_reason_count': 2,
            },
        }

        response = self.client.get(
            '/api/reject-history/summary?start_date=2026-02-01&end_date=2026-02-07'
            '&workcenter_groups=WB&packages=PKG-A&reasons=R1&reasons=R2'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['meta']['include_excluded_scrap'], False)
        _, kwargs = mock_summary.call_args
        self.assertEqual(kwargs['workcenter_groups'], ['WB'])
        self.assertEqual(kwargs['packages'], ['PKG-A'])
        self.assertEqual(kwargs['reasons'], ['R1', 'R2'])
        self.assertIs(kwargs['include_excluded_scrap'], False)
        self.assertIs(kwargs['exclude_material_scrap'], True)

    @patch('mes_dashboard.routes.reject_history_routes.query_trend')
    def test_trend_invalid_granularity_returns_400(self, mock_trend):
        mock_trend.side_effect = ValueError('Invalid granularity. Use day, week, or month')

        response = self.client.get(
            '/api/reject-history/trend?start_date=2026-02-01&end_date=2026-02-07&granularity=hour'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.reject_history_routes.query_dimension_pareto')
    def test_reason_pareto_defaults_top80(self, mock_pareto):
        mock_pareto.return_value = {'items': [], 'metric_mode': 'reject_total', 'pareto_scope': 'top80', 'meta': {}}

        response = self.client.get('/api/reject-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07')

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_pareto.call_args
        self.assertEqual(kwargs['pareto_scope'], 'top80')
        self.assertEqual(kwargs['metric_mode'], 'reject_total')
        self.assertEqual(kwargs['dimension'], 'reason')

    @patch('mes_dashboard.routes.reject_history_routes.query_dimension_pareto')
    def test_dimension_pareto_accepts_package(self, mock_pareto):
        mock_pareto.return_value = {
            'items': [{'reason': 'PKG-A', 'metric_value': 100, 'pct': 50, 'cumPct': 50}],
            'dimension': 'package',
            'metric_mode': 'reject_total',
            'pareto_scope': 'all',
            'meta': {},
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07&dimension=package&pareto_scope=all'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_pareto.call_args
        self.assertEqual(kwargs['dimension'], 'package')

    @patch('mes_dashboard.routes.reject_history_routes.query_dimension_pareto')
    def test_dimension_pareto_accepts_equipment(self, mock_pareto):
        mock_pareto.return_value = {
            'items': [{'reason': 'EQ-01', 'metric_value': 50, 'pct': 100, 'cumPct': 100}],
            'dimension': 'equipment',
            'metric_mode': 'reject_total',
            'pareto_scope': 'top80',
            'meta': {},
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-07&dimension=equipment'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_pareto.call_args
        self.assertEqual(kwargs['dimension'], 'equipment')

    @patch('mes_dashboard.routes.reject_history_routes.query_dimension_pareto')
    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_dimension_pareto_with_query_id_passes_policy_flags_to_cached_path(
        self,
        mock_cached_pareto,
        mock_sql_pareto,
    ):
        mock_cached_pareto.return_value = {
            'items': [{'reason': 'PKG-A', 'metric_value': 100, 'pct': 100, 'cumPct': 100}],
            'dimension': 'package',
            'metric_mode': 'reject_total',
            'pareto_scope': 'all',
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto'
            '?start_date=2026-02-01'
            '&end_date=2026-02-07'
            '&query_id=qid-001'
            '&dimension=package'
            '&pareto_scope=all'
            '&include_excluded_scrap=true'
            '&exclude_material_scrap=false'
            '&exclude_pb_diode=false'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_cached_pareto.call_args
        self.assertEqual(kwargs['query_id'], 'qid-001')
        self.assertEqual(kwargs['dimension'], 'package')
        self.assertEqual(kwargs['pareto_scope'], 'all')
        self.assertIs(kwargs['include_excluded_scrap'], True)
        self.assertIs(kwargs['exclude_material_scrap'], False)
        self.assertIs(kwargs['exclude_pb_diode'], False)
        mock_sql_pareto.assert_not_called()

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_passes_multi_dimension_selection_params(self, mock_batch_pareto):
        mock_batch_pareto.return_value = {
            'dimensions': {
                'reason': {'items': []},
                'package': {'items': []},
                'type': {'items': []},
                'workflow': {'items': []},
                'workcenter': {'items': []},
                'equipment': {'items': []},
            }
        }

        response = self.client.get(
            '/api/reject-history/batch-pareto'
            '?query_id=qid-001'
            '&metric_mode=reject_total'
            '&pareto_scope=all'
            '&pareto_display_scope=top20'
            '&sel_reason=001_A'
            '&sel_type=TYPE-A'
            '&sel_type=TYPE-B'
            '&include_excluded_scrap=true'
            '&exclude_material_scrap=false'
            '&exclude_pb_diode=false'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_batch_pareto.call_args
        self.assertEqual(kwargs['query_id'], 'qid-001')
        self.assertEqual(kwargs['pareto_display_scope'], 'top20')
        self.assertEqual(kwargs['pareto_scope'], 'all')
        self.assertEqual(kwargs['pareto_selections'], {'reason': ['001_A'], 'type': ['TYPE-A', 'TYPE-B']})
        self.assertIs(kwargs['include_excluded_scrap'], True)
        self.assertIs(kwargs['exclude_material_scrap'], False)
        self.assertIs(kwargs['exclude_pb_diode'], False)

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto', return_value=None)
    def test_batch_pareto_cache_miss_returns_400(self, _mock_batch_pareto):
        response = self.client.get('/api/reject-history/batch-pareto?query_id=missing-qid')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error'], 'cache_miss')

    @patch('mes_dashboard.routes.reject_history_routes.apply_view')
    def test_view_passes_pareto_multi_select_filters(self, mock_apply_view):
        mock_apply_view.return_value = {
            'analytics_raw': [],
            'summary': {},
            'detail': {
                'items': [],
                'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1},
            },
        }

        response = self.client.get(
            '/api/reject-history/view'
            '?query_id=qid-001'
            '&pareto_dimension=workflow'
            '&pareto_values=WF-A'
            '&pareto_values=WF-B'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_apply_view.call_args
        self.assertEqual(kwargs['pareto_dimension'], 'workflow')
        self.assertEqual(kwargs['pareto_values'], ['WF-A', 'WF-B'])

    @patch('mes_dashboard.routes.reject_history_routes.apply_view')
    def test_view_invalid_pareto_dimension_returns_400(self, mock_apply_view):
        response = self.client.get(
            '/api/reject-history/view'
            '?query_id=qid-001'
            '&pareto_dimension=invalid'
            '&pareto_values=X'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        mock_apply_view.assert_not_called()

    @patch('mes_dashboard.routes.reject_history_routes.apply_view')
    def test_view_passes_multi_dimension_selection_filters(self, mock_apply_view):
        mock_apply_view.return_value = {
            'analytics_raw': [],
            'summary': {},
            'detail': {'items': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1}},
        }

        response = self.client.get(
            '/api/reject-history/view'
            '?query_id=qid-001'
            '&sel_reason=001_A'
            '&sel_type=TYPE-A'
            '&sel_workflow=WF-01'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_apply_view.call_args
        self.assertEqual(kwargs['pareto_selections'], {
            'reason': ['001_A'],
            'type': ['TYPE-A'],
            'workflow': ['WF-01'],
        })
        self.assertIsNone(kwargs['pareto_dimension'])
        self.assertIsNone(kwargs['pareto_values'])

    @patch('mes_dashboard.routes.reject_history_routes.apply_view')
    def test_view_sel_filters_take_precedence_over_legacy_dimension(self, mock_apply_view):
        mock_apply_view.return_value = {
            'analytics_raw': [],
            'summary': {},
            'detail': {'items': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1}},
        }

        response = self.client.get(
            '/api/reject-history/view'
            '?query_id=qid-001'
            '&sel_reason=001_A'
            '&pareto_dimension=invalid'
            '&pareto_values=bad'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_apply_view.call_args
        self.assertEqual(kwargs['pareto_selections'], {'reason': ['001_A']})
        self.assertIsNone(kwargs['pareto_dimension'])
        self.assertIsNone(kwargs['pareto_values'])

    @patch('mes_dashboard.routes.reject_history_routes._list_to_csv')
    @patch('mes_dashboard.routes.reject_history_routes.export_csv_from_cache')
    def test_export_cached_passes_pareto_multi_select_filters(
        self,
        mock_export_cached,
        mock_list_to_csv,
    ):
        mock_export_cached.return_value = [{'LOT': 'LOT-001'}]
        mock_list_to_csv.return_value = iter(['A,B\n', '1,2\n'])

        response = self.client.get(
            '/api/reject-history/export-cached'
            '?query_id=qid-001'
            '&pareto_dimension=type'
            '&pareto_values=TYPE-A'
            '&pareto_values=TYPE-C'
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_export_cached.call_args
        self.assertEqual(kwargs['pareto_dimension'], 'type')
        self.assertEqual(kwargs['pareto_values'], ['TYPE-A', 'TYPE-C'])

    @patch('mes_dashboard.routes.reject_history_routes.export_csv_from_cache')
    def test_export_cached_invalid_pareto_dimension_returns_400(self, mock_export_cached):
        response = self.client.get(
            '/api/reject-history/export-cached'
            '?query_id=qid-001'
            '&pareto_dimension=invalid'
            '&pareto_values=TYPE-A'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        mock_export_cached.assert_not_called()

    @patch('mes_dashboard.routes.reject_history_routes._list_to_csv')
    @patch('mes_dashboard.routes.reject_history_routes.export_csv_from_cache')
    def test_export_cached_passes_multi_dimension_selection_filters(
        self,
        mock_export_cached,
        mock_list_to_csv,
    ):
        mock_export_cached.return_value = [{'LOT': 'LOT-001'}]
        mock_list_to_csv.return_value = iter(['A,B\n', '1,2\n'])

        response = self.client.get(
            '/api/reject-history/export-cached'
            '?query_id=qid-001'
            '&sel_reason=001_A'
            '&sel_type=TYPE-A'
            '&sel_equipment=EQ-01'
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_export_cached.call_args
        self.assertEqual(kwargs['pareto_selections'], {
            'reason': ['001_A'],
            'type': ['TYPE-A'],
            'equipment': ['EQ-01'],
        })
        self.assertIsNone(kwargs['pareto_dimension'])
        self.assertIsNone(kwargs['pareto_values'])

    @patch('mes_dashboard.routes.reject_history_routes.query_list')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 6))
    def test_list_rate_limited_returns_429(self, _mock_limit, mock_list):
        response = self.client.get('/api/reject-history/list?start_date=2026-02-01&end_date=2026-02-07')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '6')
        mock_list.assert_not_called()

    @patch('mes_dashboard.routes.reject_history_routes.export_csv')
    def test_export_returns_csv_response(self, mock_export):
        mock_export.return_value = iter(['A,B\n', '1,2\n'])

        response = self.client.get('/api/reject-history/export?start_date=2026-02-01&end_date=2026-02-07')

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment; filename=reject_history_2026-02-01_to_2026-02-07.csv', response.headers.get('Content-Disposition', ''))
        self.assertIn('text/csv', response.headers.get('Content-Type', ''))


if __name__ == '__main__':
    unittest.main()
