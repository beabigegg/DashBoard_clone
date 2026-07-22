# -*- coding: utf-8 -*-
"""Unit tests for Hold History API routes (two-phase query/view pattern)."""

import json
import unittest
from unittest.mock import patch

import pytest

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
        """Route must forward all four params to execute_primary_query with non-default values."""
        mock_exec.return_value = {'query_id': 'x', 'trend': {}, 'reason_pareto': {}, 'duration': {}, 'list': {}}

        # Use non-default values to ensure they are truly forwarded (not filled by defaults)
        self.client.post(
            '/api/hold-history/query',
            json={
                'start_date': '2026-02-01',
                'end_date': '2026-02-07',  # < 90 days so sync path is used
                'hold_type': 'non-quality',
                'record_type': 'on_hold',
            },
        )

        mock_exec.assert_called_once()
        kw = mock_exec.call_args.kwargs
        self.assertEqual(kw['start_date'], '2026-02-01')
        self.assertEqual(kw['end_date'], '2026-02-07')
        self.assertEqual(kw['hold_type'], 'non-quality')
        self.assertEqual(kw['record_type'], 'on_hold')

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


class TestHoldHistoryAsyncQueryRoute(TestHoldHistoryRoutesBase):
    """Tests for the async RQ branch in POST /api/hold-history/query (AC-1, AC-2, AC-6, AC-8)."""

    # ── fixtures ─────────────────────────────────────────────────────────────

    LONG_RANGE_BODY = {
        'start_date': '2025-01-01',
        'end_date': '2025-06-01',   # 151 days — well above default threshold of 90
        'hold_type': 'quality',
        'record_type': 'new',
    }

    SHORT_RANGE_BODY = {
        'start_date': '2026-02-01',
        'end_date': '2026-02-07',   # 6 days — below threshold
        'hold_type': 'quality',
        'record_type': 'new',
    }

    SYNC_RESULT = {
        'query_id': 'sync-abc',
        'trend': {'days': []},
        'reason_pareto': {'items': []},
        'duration': {'items': []},
        'list': {'items': [], 'pagination': {}},
    }

    # ── AC-1: long range with enabled flag + available worker → 202 ──────────

    @patch('mes_dashboard.routes.hold_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.hold_history_routes.enqueue_job_dynamic', return_value=('job-001', None))
    def test_query_long_range_returns_202(self, _mock_enq, _mock_avail):
        response = self.client.post('/api/hold-history/query', json=self.LONG_RANGE_BODY)
        self.assertEqual(response.status_code, 202)
        payload = json.loads(response.data)
        self.assertTrue(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.hold_history_routes.enqueue_job_dynamic', return_value=('job-002', None))
    def test_query_202_response_has_job_id(self, _mock_enq, _mock_avail):
        response = self.client.post('/api/hold-history/query', json=self.LONG_RANGE_BODY)
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 202)
        self.assertIn('job_id', payload['data'])
        self.assertEqual(payload['data']['job_id'], 'job-002')
        self.assertIn('status_url', payload['data'])
        self.assertIn('hold-history', payload['data']['status_url'])
        self.assertTrue(payload['data']['async'])

    # ── AC-2: short range → sync 200 ─────────────────────────────────────────

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    def test_query_short_range_returns_200_sync(self, mock_exec):
        mock_exec.return_value = self.SYNC_RESULT
        response = self.client.post('/api/hold-history/query', json=self.SHORT_RANGE_BODY)
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('query_id', payload['data'])
        mock_exec.assert_called_once()

    # ── AC-2: HOLD_ASYNC_ENABLED=False → sync 200 ────────────────────────────

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    def test_query_async_flag_false_returns_200_sync(self, mock_exec, monkeypatch=None):
        mock_exec.return_value = self.SYNC_RESULT
        import mes_dashboard.routes.hold_history_routes as _rmod
        orig = _rmod.HOLD_ASYNC_ENABLED
        _rmod.HOLD_ASYNC_ENABLED = False
        try:
            response = self.client.post('/api/hold-history/query', json=self.LONG_RANGE_BODY)
            payload = json.loads(response.data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload['success'])
            mock_exec.assert_called_once()
        finally:
            _rmod.HOLD_ASYNC_ENABLED = orig

    # ── AC-8: is_async_available=False → fall through to sync 200 (no error) ─

    @patch('mes_dashboard.routes.hold_history_routes.execute_primary_query')
    @patch('mes_dashboard.routes.hold_history_routes.is_async_available', return_value=False)
    def test_query_redis_down_falls_back_to_sync(self, _mock_avail, mock_exec):
        mock_exec.return_value = self.SYNC_RESULT
        response = self.client.post('/api/hold-history/query', json=self.LONG_RANGE_BODY)
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        mock_exec.assert_called_once()

    # ── AC-6: default constant values ────────────────────────────────────────

    def test_hold_async_enabled_default_is_true(self):
        """HOLD_ASYNC_ENABLED route-module constant must default to True."""
        import mes_dashboard.routes.hold_history_routes as _rmod
        # The constant is frozen at import time; read directly from the module.
        # To assert the default we check the unpatched value against True.
        # (monkeypatch.setattr is the prescribed override mechanism in tests,
        # but the default must be True per env-contract pinned default.)
        import importlib
        import os
        # Save and temporarily remove env override to confirm code default
        _old = os.environ.pop("HOLD_ASYNC_ENABLED", None)
        try:
            # Reload to evaluate default expression fresh
            importlib.reload(_rmod)
            self.assertTrue(_rmod.HOLD_ASYNC_ENABLED)
        finally:
            if _old is not None:
                os.environ["HOLD_ASYNC_ENABLED"] = _old
            else:
                importlib.reload(_rmod)  # restore original module state

    def test_hold_async_day_threshold_removed(self):
        """HOLD_ASYNC_DAY_THRESHOLD must NOT be present on the route module (query-path-c-elimination-cleanup, IP-7).

        Replaced by _classify_query_cost(domain="hold", ...) with unified CostPolicy.
        """
        import mes_dashboard.routes.hold_history_routes as _rmod
        self.assertFalse(
            hasattr(_rmod, 'HOLD_ASYNC_DAY_THRESHOLD'),
            "HOLD_ASYNC_DAY_THRESHOLD was removed in IP-7 but is still present on the module."
        )


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

        mock_view.assert_called_once()
        kw = mock_view.call_args.kwargs
        self.assertEqual(kw['query_id'], 'abc123')
        self.assertEqual(kw['hold_type'], 'non-quality')
        self.assertEqual(kw['reason'], '品質確認')
        self.assertEqual(kw['record_type'], 'new')
        self.assertIsNone(kw['duration_range'])
        self.assertIsNone(kw['day_filter'])
        self.assertEqual(kw['page'], 2)
        self.assertEqual(kw['per_page'], 20)
        self.assertFalse(kw['export_mode'])

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

    def test_view_invalid_day_filter_returns_400(self):
        response = self.client.get(
            '/api/hold-history/view?query_id=abc123&day_filter=garbage'
        )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error']['code'], 'VALIDATION_ERROR')

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    def test_view_passes_day_filter(self, mock_view):
        mock_view.return_value = {
            'trend': {'days': []},
            'reason_pareto': {'items': []},
            'duration': {'items': []},
            'list': {'items': [], 'pagination': {}},
        }

        self.client.get(
            '/api/hold-history/view?query_id=abc123&day_filter=2026-01-03:new'
        )

        call_kwargs = mock_view.call_args.kwargs
        self.assertEqual(call_kwargs['day_filter'], '2026-01-03:new')

    @patch('mes_dashboard.routes.hold_history_routes.apply_view')
    @patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
    def test_view_rate_limited_returns_429(self, _mock_limit, mock_view):
        response = self.client.get('/api/hold-history/view?query_id=abc123')
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload['error']['code'], 'TOO_MANY_REQUESTS')
        self.assertEqual(response.headers.get('Retry-After'), '5')
        mock_view.assert_not_called()


class TestHoldHistoryTodaySnapshotRoute(TestHoldHistoryRoutesBase):
    """Test POST /api/hold-history/today-snapshot endpoint."""

    GOOD_RESULT = {
        'query_id': 'today_quality_123',
        'summary': {
            'onHoldTotalCount': 50,
            'onHoldTotalQty': 200,
            'todayNewQty': 10,
            'todayReleaseQty': 5,
            'todayFutureHoldQty': 2,
            'onHoldAvgHours': 24.5,
            'onHoldMaxHours': 120.0,
        },
        'reason_pareto': {'items': []},
        'duration': {'items': []},
        'list': {'items': [], 'pagination': {'page': 1, 'perPage': 50, 'total': 0, 'totalPages': 1}},
    }

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_success_returns_200(self, mock_exec):
        mock_exec.return_value = self.GOOD_RESULT
        response = self.client.post('/api/hold-history/today-snapshot', json={})
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('summary', payload['data'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_summary_keys_present(self, mock_exec):
        mock_exec.return_value = self.GOOD_RESULT
        response = self.client.post('/api/hold-history/today-snapshot', json={})
        data = json.loads(response.data)['data']
        expected_keys = {
            'onHoldTotalCount', 'onHoldTotalQty', 'todayNewQty',
            'todayReleaseQty', 'todayFutureHoldQty',
            'onHoldAvgHours', 'onHoldMaxHours',
        }
        self.assertTrue(expected_keys.issubset(set(data['summary'].keys())))

    def test_today_snapshot_invalid_record_type_returns_400(self):
        response = self.client.post(
            '/api/hold-history/today-snapshot',
            json={'record_type': 'released'},  # 'released' is range-mode only
        )
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_today_snapshot_invalid_duration_range_returns_400(self):
        response = self.client.post(
            '/api/hold-history/today-snapshot',
            json={'duration_range': 'invalid-range'},
        )
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_db_unavailable_returns_503(self, mock_exec):
        from mes_dashboard.core.database import DatabaseCircuitOpenError
        mock_exec.side_effect = DatabaseCircuitOpenError('circuit open')
        response = self.client.post('/api/hold-history/today-snapshot', json={})
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_pool_exhausted_returns_503(self, mock_exec):
        from mes_dashboard.core.database import DatabasePoolExhaustedError
        mock_exec.side_effect = DatabasePoolExhaustedError('pool exhausted')
        response = self.client.post('/api/hold-history/today-snapshot', json={})
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_runtime_error_returns_503(self, mock_exec):
        mock_exec.side_effect = RuntimeError('unexpected')
        response = self.client.post('/api/hold-history/today-snapshot', json={})
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload['success'])

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_valid_record_types(self, mock_exec):
        mock_exec.return_value = self.GOOD_RESULT
        for rt in ['on_hold', 'new', 'release', 'on_hold,new', 'new,release']:
            response = self.client.post(
                '/api/hold-history/today-snapshot',
                json={'record_type': rt},
            )
            self.assertEqual(response.status_code, 200, f'record_type={rt!r} should be 200')

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_default_hold_type_is_quality(self, mock_exec):
        mock_exec.return_value = self.GOOD_RESULT
        self.client.post('/api/hold-history/today-snapshot', json={})
        call_kwargs = mock_exec.call_args[1]
        self.assertEqual(call_kwargs['hold_type'], 'quality')

    @patch('mes_dashboard.routes.hold_history_routes.execute_today_snapshot')
    def test_today_snapshot_no_trend_key(self, mock_exec):
        """Today-snapshot response must NOT include a trend field."""
        mock_exec.return_value = self.GOOD_RESULT
        response = self.client.post('/api/hold-history/today-snapshot', json={})
        data = json.loads(response.data)['data']
        self.assertNotIn('trend', data)


class TestHoldHistoryConfigRoute(TestHoldHistoryRoutesBase):
    """Test GET /api/hold-history/config endpoint."""

    def test_config_returns_200(self):
        response = self.client.get('/api/hold-history/config')
        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])

    def test_config_has_feature_flag_keys(self):
        response = self.client.get('/api/hold-history/config')
        data = json.loads(response.data)['data']
        self.assertIn('today_mode_enabled', data)
        self.assertIn('auto_refresh_seconds', data)

    def test_config_has_hold_async_keys(self):
        """Route module must expose HOLD_ASYNC_ENABLED and other keys (AC-6).

        HOLD_ASYNC_DAY_THRESHOLD removed (query-path-c-elimination-cleanup, IP-7);
        routing now uses _classify_query_cost(domain="hold", ...) with unified CostPolicy.
        """
        import mes_dashboard.routes.hold_history_routes as _rmod
        self.assertTrue(hasattr(_rmod, 'HOLD_ASYNC_ENABLED'))
        # HOLD_ASYNC_DAY_THRESHOLD removed — assert absent
        self.assertFalse(
            hasattr(_rmod, 'HOLD_ASYNC_DAY_THRESHOLD'),
            "HOLD_ASYNC_DAY_THRESHOLD was removed in IP-7 but is still present."
        )
        self.assertTrue(hasattr(_rmod, 'HOLD_WORKER_QUEUE'))
        self.assertTrue(hasattr(_rmod, 'HOLD_JOB_TIMEOUT_SECONDS'))
