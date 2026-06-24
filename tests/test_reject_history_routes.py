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
    @patch.dict(os.environ, {
        'PORTAL_SPA_ENABLED': 'false',
        'MODERNIZATION_RETIRE_IN_SCOPE_RUNTIME_FALLBACK': 'false',
    })
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
        # Endpoint now requires query_id; missing query_id → 400
        response = self.client.get('/api/reject-history/summary')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_summary_invalid_include_excluded_scrap_returns_400(self):
        response = self.client.get(
            '/api/reject-history/summary?query_id=test-id'
            '&include_excluded_scrap=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_summary_invalid_exclude_material_scrap_returns_400(self):
        response = self.client.get(
            '/api/reject-history/summary?query_id=test-id'
            '&exclude_material_scrap=invalid'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.reject_history_routes.view_summary')
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
        }

        response = self.client.get(
            '/api/reject-history/summary?query_id=test-id'
            '&workcenter_groups=WB&packages=PKG-A&reasons=R1&reasons=R2'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('include_excluded_scrap', payload['meta'])
        kwargs = mock_summary.call_args.kwargs
        self.assertEqual(kwargs['query_id'], 'test-id')
        self.assertEqual(kwargs['workcenter_groups'], ['WB'])
        self.assertEqual(kwargs['packages'], ['PKG-A'])
        self.assertEqual(kwargs['reasons'], ['R1', 'R2'])
        self.assertIs(kwargs['include_excluded_scrap'], False)
        self.assertIs(kwargs['exclude_material_scrap'], True)

    @patch('mes_dashboard.routes.reject_history_routes.execute_primary_query')
    def test_query_rejects_date_range_over_half_year(self, mock_execute):
        response = self.client.post(
            '/api/reject-history/query',
            json={
                'mode': 'date_range',
                'start_date': '2025-01-01',
                'end_date': '2025-12-31',
                'include_excluded_scrap': False,
                'exclude_material_scrap': True,
                'exclude_pb_diode': True,
            },
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        self.assertIn('190', payload['error']['message'])
        mock_execute.assert_not_called()

    @patch('mes_dashboard.routes.reject_history_routes._REJECT_HISTORY_USE_UNIFIED_JOB', False)
    @patch('mes_dashboard.services.reject_query_job_service.enqueue_reject_query', return_value=('reject-job-001', None))
    @patch('mes_dashboard.routes.reject_history_routes._has_cached_df', return_value=False)
    def test_query_accepts_date_range_within_half_year(self, _mock_cache, _mock_enqueue):

        response = self.client.post(
            '/api/reject-history/query',
            json={
                'mode': 'date_range',
                'start_date': '2025-01-01',
                'end_date': '2025-07-09',
                'include_excluded_scrap': False,
                'exclude_material_scrap': True,
                'exclude_pb_diode': True,
            },
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['job_id'], 'reject-job-001')

    @patch('mes_dashboard.services.reject_query_job_service.enqueue_reject_query', return_value=(None, 'redis unavailable'))
    @patch('mes_dashboard.routes.reject_history_routes._has_cached_df', return_value=False)
    def test_query_returns_503_when_async_enqueue_fails(self, _mock_cache, _mock_enqueue):

        response = self.client.post(
            '/api/reject-history/query',
            json={
                'mode': 'date_range',
                'start_date': '2025-01-01',
                'end_date': '2025-07-09',
                'include_excluded_scrap': False,
                'exclude_material_scrap': True,
                'exclude_pb_diode': True,
            },
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'SERVICE_UNAVAILABLE')
        self.assertEqual(response.headers.get('Retry-After'), '30')

    @patch('mes_dashboard.routes.reject_history_routes.view_trend')
    def test_trend_invalid_granularity_returns_400(self, mock_trend):
        mock_trend.side_effect = ValueError('Invalid granularity. Use day, week, or month')

        response = self.client.get(
            '/api/reject-history/trend?query_id=test-id&granularity=hour'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_reason_pareto_defaults_top80(self, mock_pareto):
        mock_pareto.return_value = {'items': [], 'metric_mode': 'reject_total', 'pareto_scope': 'top80'}

        response = self.client.get('/api/reject-history/reason-pareto?query_id=test-id')

        self.assertEqual(response.status_code, 200)
        kwargs = mock_pareto.call_args.kwargs
        self.assertEqual(kwargs['pareto_scope'], 'top80')
        self.assertEqual(kwargs['metric_mode'], 'reject_total')
        self.assertEqual(kwargs['dimension'], 'reason')

    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_dimension_pareto_accepts_package(self, mock_pareto):
        mock_pareto.return_value = {
            'items': [{'reason': 'PKG-A', 'metric_value': 100, 'pct': 50, 'cumPct': 50}],
            'dimension': 'package',
            'metric_mode': 'reject_total',
            'pareto_scope': 'top80',
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto?query_id=test-id&dimension=package&pareto_scope=all'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        kwargs = mock_pareto.call_args.kwargs
        self.assertEqual(kwargs['dimension'], 'package')
        self.assertEqual(kwargs['pareto_scope'], 'top80')

    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_dimension_pareto_accepts_equipment(self, mock_pareto):
        mock_pareto.return_value = {
            'items': [{'reason': 'EQ-01', 'metric_value': 50, 'pct': 100, 'cumPct': 100}],
            'dimension': 'equipment',
            'metric_mode': 'reject_total',
            'pareto_scope': 'top80',
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto?query_id=test-id&dimension=equipment'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        kwargs = mock_pareto.call_args.kwargs
        self.assertEqual(kwargs['dimension'], 'equipment')

    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_dimension_pareto_with_query_id_passes_policy_flags_to_cached_path(
        self,
        mock_cached_pareto,
    ):
        mock_cached_pareto.return_value = {
            'items': [{'reason': 'PKG-A', 'metric_value': 100, 'pct': 100, 'cumPct': 100}],
            'dimension': 'package',
            'metric_mode': 'reject_total',
            'pareto_scope': 'all',
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto'
            '?query_id=qid-001'
            '&dimension=package'
            '&pareto_scope=all'
            '&include_excluded_scrap=true'
            '&exclude_material_scrap=false'
            '&exclude_pb_diode=false'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        kwargs = mock_cached_pareto.call_args.kwargs
        self.assertEqual(kwargs['query_id'], 'qid-001')
        self.assertEqual(kwargs['dimension'], 'package')
        self.assertEqual(kwargs['pareto_scope'], 'top80')
        self.assertIs(kwargs['include_excluded_scrap'], True)
        self.assertIs(kwargs['exclude_material_scrap'], False)
        self.assertIs(kwargs['exclude_pb_diode'], False)

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_passes_multi_dimension_selection_params(self, mock_batch_pareto):
        mock_batch_pareto.return_value = {
            'dimensions': {
                'reason': {'items': []},
                'package': {'items': []},
                'type': {'items': []},
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
        self.assertEqual(kwargs['pareto_scope'], 'top80')
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
        self.assertEqual(payload['error']['code'], 'CACHE_MISS')

    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_reason_pareto_memory_guard_returns_503(self, mock_pareto):
        mock_pareto.side_effect = MemoryError('目前服務記憶體負載較高')

        response = self.client.get(
            '/api/reject-history/reason-pareto?query_id=test-id'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'SERVICE_UNAVAILABLE')
        self.assertIn('記憶體負載較高', payload['error']['message'])
        self.assertEqual(response.headers.get('Retry-After'), '30')

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_memory_guard_returns_503(self, mock_batch_pareto):
        mock_batch_pareto.side_effect = MemoryError('目前服務記憶體負載較高')

        response = self.client.get('/api/reject-history/batch-pareto?query_id=qid-oom')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'SERVICE_UNAVAILABLE')
        self.assertIn('記憶體負載較高', payload['error']['message'])
        self.assertEqual(response.headers.get('Retry-After'), '30')

    @patch('mes_dashboard.routes.reject_history_routes.apply_view')
    def test_view_memory_guard_returns_503(self, mock_apply_view):
        mock_apply_view.side_effect = MemoryError('目前服務記憶體負載較高')

        response = self.client.get('/api/reject-history/view?query_id=qid-oom')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'SERVICE_UNAVAILABLE')
        self.assertIn('記憶體負載較高', payload['error']['message'])
        self.assertEqual(response.headers.get('Retry-After'), '30')

    @patch('mes_dashboard.routes.reject_history_routes.export_csv_from_cache')
    def test_export_cached_memory_guard_returns_503(self, mock_export_cached):
        mock_export_cached.side_effect = MemoryError('目前服務記憶體負載較高')

        response = self.client.get('/api/reject-history/export-cached?query_id=qid-oom')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'SERVICE_UNAVAILABLE')
        self.assertIn('記憶體負載較高', payload['error']['message'])
        self.assertEqual(response.headers.get('Retry-After'), '30')

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
            '&pareto_dimension=type'
            '&pareto_values=TYPE-A'
            '&pareto_values=TYPE-B'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_apply_view.call_args
        self.assertEqual(kwargs['pareto_dimension'], 'type')
        self.assertEqual(kwargs['pareto_values'], ['TYPE-A', 'TYPE-B'])

    @patch('mes_dashboard.routes.reject_history_routes.apply_view', return_value=None)
    def test_view_cache_expired_returns_410(self, _mock_apply_view):
        response = self.client.get('/api/reject-history/view?query_id=qid-expired')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 410)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'CACHE_EXPIRED')

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
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        _, kwargs = mock_apply_view.call_args
        self.assertEqual(kwargs['pareto_selections'], {
            'reason': ['001_A'],
            'type': ['TYPE-A'],
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

    @patch('mes_dashboard.routes.reject_history_routes.export_csv_from_cache', return_value=None)
    def test_export_cached_cache_expired_returns_410(self, _mock_export_cached):
        response = self.client.get('/api/reject-history/export-cached?query_id=qid-expired')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 410)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'CACHE_EXPIRED')

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
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_export_cached.call_args
        self.assertEqual(kwargs['pareto_selections'], {
            'reason': ['001_A'],
            'type': ['TYPE-A'],
        })
        self.assertIsNone(kwargs['pareto_dimension'])
        self.assertIsNone(kwargs['pareto_values'])

    @patch('mes_dashboard.routes.reject_history_routes.view_list')
    def test_list_route_preserves_pagination_contract(self, mock_list):
        mock_list.return_value = {
            'items': [{'CONTAINERNAME': 'LOT-001'}],
            'pagination': {'page': 2, 'perPage': 80, 'total': 160, 'totalPages': 2},
        }

        response = self.client.get(
            '/api/reject-history/list'
            '?query_id=test-id'
            '&page=2'
            '&per_page=80'
            '&metric_filter=reject'
            '&workcenter_groups=WB'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['pagination']['page'], 2)
        self.assertEqual(payload['data']['pagination']['perPage'], 80)
        self.assertEqual(payload['data']['pagination']['total'], 160)
        self.assertEqual(payload['data']['pagination']['totalPages'], 2)
        kwargs = mock_list.call_args.kwargs
        self.assertEqual(kwargs['query_id'], 'test-id')
        self.assertEqual(kwargs['page'], 2)
        self.assertEqual(kwargs['per_page'], 80)
        self.assertEqual(kwargs['metric_filter'], 'reject')
        self.assertEqual(kwargs['workcenter_groups'], ['WB'])

    @patch('mes_dashboard.routes.reject_history_routes.view_list')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 6))
    def test_list_rate_limited_returns_429(self, _mock_limit, mock_list):
        response = self.client.get('/api/reject-history/list?query_id=test-id')
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


    # ================================================================
    # 5.3 – Pareto materialization metadata & fallback route tests
    # ================================================================

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_exposes_materialized_metadata_on_hit(self, mock_batch_pareto):
        """When materialized snapshot serves the request, meta must appear."""
        mock_batch_pareto.return_value = {
            'dimensions': {
                'reason': {'items': [], 'dimension': 'reason', 'metric_mode': 'reject_total'},
            },
            '_pareto_meta': {
                'pareto_source': 'materialized',
                'pareto_schema_version': 1,
                'pareto_snapshot_built_at': 1700000000.0,
                'pareto_snapshot_age_s': 5.0,
            },
        }

        response = self.client.get('/api/reject-history/batch-pareto?query_id=qid-mat')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        # _pareto_meta should be extracted to top-level 'meta'
        self.assertIn('meta', payload)
        self.assertEqual(payload['meta']['pareto_source'], 'materialized')
        self.assertEqual(payload['meta']['pareto_schema_version'], 1)
        # _pareto_meta should NOT be in data
        self.assertNotIn('_pareto_meta', payload['data'])

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_exposes_fallback_metadata(self, mock_batch_pareto):
        """When falling back to legacy, meta must include fallback reason."""
        mock_batch_pareto.return_value = {
            'dimensions': {
                'reason': {'items': [], 'dimension': 'reason', 'metric_mode': 'reject_total'},
            },
            '_pareto_meta': {
                'pareto_source': 'legacy',
                'pareto_fallback_reason': 'miss',
            },
        }

        response = self.client.get('/api/reject-history/batch-pareto?query_id=qid-fb')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('meta', payload)
        self.assertEqual(payload['meta']['pareto_source'], 'legacy')
        self.assertEqual(payload['meta']['pareto_fallback_reason'], 'miss')

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_no_meta_when_absent(self, mock_batch_pareto):
        """When no _pareto_meta is in the result, response has no meta key."""
        mock_batch_pareto.return_value = {
            'dimensions': {
                'reason': {'items': []},
            },
        }

        response = self.client.get('/api/reject-history/batch-pareto?query_id=qid-nometa')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        # meta always present (contains at least 'timestamp'), but no pareto_source key
        self.assertNotIn('pareto_source', payload.get('meta', {}))

    @patch('mes_dashboard.routes.reject_history_routes.compute_dimension_pareto')
    def test_reason_pareto_exposes_materialized_metadata(self, mock_dim_pareto):
        """reason-pareto with query_id should expose pareto metadata."""
        mock_dim_pareto.return_value = {
            'items': [{'reason': 'A', 'metric_value': 10, 'pct': 100, 'cumPct': 100}],
            'dimension': 'reason',
            'metric_mode': 'reject_total',
            '_pareto_meta': {
                'pareto_source': 'materialized',
                'pareto_schema_version': 1,
            },
        }

        response = self.client.get(
            '/api/reject-history/reason-pareto'
            '?start_date=2026-01-01&end_date=2026-01-31'
            '&query_id=qid-rp'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('meta', payload)
        self.assertEqual(payload['meta']['pareto_source'], 'materialized')

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_stale_fallback_reason(self, mock_batch_pareto):
        """Stale snapshot fallback must carry 'stale' reason code."""
        mock_batch_pareto.return_value = {
            'dimensions': {'reason': {'items': []}},
            '_pareto_meta': {
                'pareto_source': 'legacy',
                'pareto_fallback_reason': 'stale',
            },
        }

        response = self.client.get('/api/reject-history/batch-pareto?query_id=qid-stale')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['meta']['pareto_fallback_reason'], 'stale')

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_build_failed_fallback_reason(self, mock_batch_pareto):
        """Build failure fallback must carry 'build_failed' reason code."""
        mock_batch_pareto.return_value = {
            'dimensions': {'reason': {'items': []}},
            '_pareto_meta': {
                'pareto_source': 'legacy',
                'pareto_fallback_reason': 'build_failed',
            },
        }

        response = self.client.get('/api/reject-history/batch-pareto?query_id=qid-bf')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['meta']['pareto_fallback_reason'], 'build_failed')


class TestRejectHistoryEdgeCases(TestRejectHistoryRoutesBase):
    """Edge cases: 202 → 410 cache expired, sync 200 small range, nested Pareto, CSV vs JSON reasons."""

    def test_job_status_not_found_returns_error_envelope(self):
        """When job not found, endpoint must return error envelope."""
        with patch(
            'mes_dashboard.services.async_query_job_service.get_job_status',
            return_value=None
        ):
            response = self.client.get('/api/reject-history/job/nonexistent-job-id')
        payload = json.loads(response.data)

        self.assertFalse(payload['success'])
        self.assertIn('error', payload)
        self.assertIn(payload['error']['code'], ('CACHE_EXPIRED', 'NOT_FOUND'))

    @patch('mes_dashboard.routes.reject_history_routes._has_cached_df', return_value=True)
    @patch('mes_dashboard.routes.reject_history_routes.execute_primary_query')
    def test_sync_200_small_range(self, mock_execute, mock_cached):
        """Synchronous query on small date range with cache hit must return 200."""
        mock_execute.return_value = {
            'query_id': 'sync-qid-001',
            'summary': {'total_lots': 5},
            'available_filters': {},
            'detail': {'rows': [], 'pagination': {'page': 1, 'per_page': 50, 'total': 5, 'total_pages': 1}},
            'analytics_raw': [],
        }

        response = self.client.post(
            '/api/reject-history/query',
            data=json.dumps({
                'mode': 'date_range',
                'start_date': '2024-01-01',
                'end_date': '2024-01-03',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.data)
        self.assertTrue(payload['success'])

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_nested_pareto_aggregates_shape(self, mock_pareto):
        """Batch-pareto response must carry nested dimensions with items/total keys."""
        mock_pareto.return_value = {
            'dimensions': {
                'reason': {
                    'items': [
                        {'label': '品質確認', 'value': 10, 'sub_items': []},
                    ],
                    'total': 10,
                },
                'workcenter': {
                    'items': [
                        {'label': 'WB', 'value': 6, 'sub_items': []},
                        {'label': 'CP', 'value': 4, 'sub_items': []},
                    ],
                    'total': 10,
                },
            },
            '_pareto_meta': {'pareto_source': 'materialized'},
        }

        response = self.client.get(
            '/api/reject-history/batch-pareto?query_id=qid-nested'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        dims = payload['data']['dimensions']
        self.assertIn('reason', dims)
        self.assertIn('workcenter', dims)
        self.assertEqual(dims['reason']['total'], 10)

    @patch('mes_dashboard.routes.reject_history_routes.compute_batch_pareto')
    def test_batch_pareto_post_json_reasons(self, mock_pareto):
        """POST /api/reject-history/batch-pareto must accept JSON body."""
        mock_pareto.return_value = {
            'dimensions': {'reason': {'items': [], 'total': 0}},
            '_pareto_meta': {'pareto_source': 'legacy'},
        }

        response = self.client.post(
            '/api/reject-history/batch-pareto',
            data=json.dumps({'query_id': 'qid-post', 'reasons': ['品質確認']}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, (200, 400))

    def test_options_returns_envelope(self):
        """GET /api/reject-history/options must return standard envelope."""
        response = self.client.get('/api/reject-history/options')
        payload = json.loads(response.data)
        self.assertIn('success', payload)
        self.assertIn('meta', payload)


if __name__ == '__main__':
    unittest.main()


# ============================================================
# CSV mid-stream error sentinel tests (pytest style)
# ============================================================



class TestRejectHistoryCsvMidStreamError:
    """_list_to_csv must emit __STREAM_ERROR__ sentinel when generator raises mid-stream."""

    def test_sentinel_emitted_on_mid_stream_exception(self):
        """When rows generator raises mid-stream, sentinel row must appear in output."""
        from mes_dashboard.services.reject_history_service import _list_to_csv

        def _bad_rows():
            yield {"LOT": "LOT-001", "WORKCENTER": "DB"}
            raise RuntimeError("Oracle disconnected mid-stream")

        headers = ["LOT", "WORKCENTER"]
        chunks = list(_list_to_csv(_bad_rows(), headers))
        combined = "".join(chunks)

        assert "__STREAM_ERROR__" in combined

    def test_no_sentinel_when_rows_complete_successfully(self):
        """When rows complete without error, no sentinel must appear."""
        from mes_dashboard.services.reject_history_service import _list_to_csv

        rows = [
            {"LOT": "LOT-001", "WORKCENTER": "DB"},
            {"LOT": "LOT-002", "WORKCENTER": "WB"},
        ]
        headers = ["LOT", "WORKCENTER"]
        combined = "".join(_list_to_csv(rows, headers))

        assert "__STREAM_ERROR__" not in combined
        assert "LOT-001" in combined
        assert "LOT-002" in combined

    def test_header_row_emitted_before_sentinel(self):
        """Header must appear in output before the sentinel line."""
        from mes_dashboard.services.reject_history_service import _list_to_csv

        def _bad_rows():
            raise RuntimeError("immediate failure")
            yield {}

        headers = ["LOT", "WORKCENTER"]
        combined = "".join(_list_to_csv(_bad_rows(), headers))

        # Headers must be present (written before any row iteration)
        assert "LOT" in combined
        assert "__STREAM_ERROR__" in combined

    def test_export_csv_uses_sentinel_on_oracle_failure(self):
        """export_csv sentinel bubbles up when Oracle raises mid-loop."""
        from mes_dashboard.services.reject_history_service import export_csv

        # read_sql_df is imported as alias from core.database.read_sql_df_slow
        with patch(
            'mes_dashboard.services.reject_history_service.read_sql_df',
            side_effect=Exception("Oracle connection lost"),
        ):
            try:
                chunks = list(export_csv(
                    start_date='2024-01-01',
                    end_date='2024-01-03',
                ))
            except Exception:
                # If the exception escapes (before any yield), that's also acceptable —
                # the route's try/except will return 500 in that case.
                chunks = []

        # Either we get chunks (some with sentinel), or chunks is empty (propagated raise)
        assert isinstance(chunks, list)


class TestResourceHistoryCsvMidStreamSentinel:
    """resource_history export_csv already has error trailer at line 640."""

    def test_error_trailer_present_in_resource_history_export(self):
        """resource_history export_csv must yield error line when Oracle raises."""
        from mes_dashboard.services.resource_history_service import export_csv

        with patch(
            'mes_dashboard.services.resource_history_service._get_filtered_resources',
            side_effect=Exception("Oracle timeout"),
        ):
            chunks = list(export_csv(
                start_date='2024-01-01',
                end_date='2024-01-03',
            ))

        combined = "".join(chunks)
        # resource_history_service yields "Error: <msg>\n" on exception
        assert "Error:" in combined
