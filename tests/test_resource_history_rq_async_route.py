# -*- coding: utf-8 -*-
"""Unit tests for the async 202 branch in resource_history_routes.api_resource_history_query.

Tests the threshold gating, flag-off fallback, Redis-down fallback,
and env-var default pinning for the resource-history RQ async path.

AC coverage: AC-1, AC-2, AC-5, AC-6, AC-7.
"""
from __future__ import annotations

import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import mes_dashboard.core.database as db


class TestResourceHistoryAsyncRoute(unittest.TestCase):
    """Unit tests for the async 202 branch of POST /api/resource/history/query."""

    def setUp(self):
        """Set up test client with async-capable configuration."""
        db._ENGINE = None
        from mes_dashboard.app import create_app
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def _post_query(self, start_date, end_date, extra=None):
        """Helper: POST /api/resource/history/query."""
        body = {"start_date": start_date, "end_date": end_date}
        if extra:
            body.update(extra)
        return self.client.post('/api/resource/history/query', json=body)

    # ── AC-1: long span → 202 ────────────────────────────────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.resource_history_routes.get_owner_token', return_value='user-token')
    @patch('mes_dashboard.routes.resource_history_routes.enqueue_job_dynamic')
    def test_query_long_span_returns_202(self, mock_enqueue, _mock_owner, _mock_avail):
        """Day span ≥ threshold + async enabled + worker available → HTTP 202 (AC-1)."""
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_enqueue.return_value = ("job-abc-001", None)

        # Patch module-level constants to ensure threshold is met
        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                # 200 days span → well above 90
                response = self._post_query("2024-01-01", "2024-07-20")

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertTrue(data['data']['async'])
        self.assertIn('job_id', data['data'])
        self.assertIn('status_url', data['data'])
        self.assertIn('resource-history', data['data']['status_url'])
        mock_enqueue.assert_called_once()

    # ── AC-2: short span → 200 sync ──────────────────────────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
        return_value=(None, None),
    )
    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_query_short_span_returns_200_sync(self, mock_query, _mock_canonical, _mock_avail):
        """Day span < threshold → HTTP 200 sync (AC-2)."""
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_query.return_value = {
            'query_id': 'sync-qid-001',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                # 7 days → well below 90
                response = self._post_query("2024-01-01", "2024-01-07")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('query_id', data['data'])
        mock_query.assert_called_once()

    # ── AC-2 / AC-6: flag off → 200 sync ────────────────────────────────────

    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
        return_value=(None, None),
    )
    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_query_async_flag_false_returns_200_sync(self, mock_query, _mock_canonical):
        """RESOURCE_ASYNC_ENABLED=False → HTTP 200 sync regardless of span (AC-2, AC-6)."""
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_query.return_value = {
            'query_id': 'sync-flagoff-001',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', False):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                # 200 days span, but flag is off
                response = self._post_query("2024-01-01", "2024-07-20")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('query_id', data['data'])
        mock_query.assert_called_once()

    # ── AC-6: Redis unavailable → 200 sync ──────────────────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=False)
    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
        return_value=(None, None),
    )
    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_redis_unavailable_falls_back_to_sync(self, mock_query, _mock_canonical, _mock_avail):
        """is_async_available() False → falls back to sync 200 (AC-6)."""
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_query.return_value = {
            'query_id': 'sync-redis-down-001',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                # 200 days, but Redis is down
                response = self._post_query("2024-01-01", "2024-07-20")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        mock_query.assert_called_once()

    # ── AC-7: owner in _params dict ──────────────────────────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.resource_history_routes.get_owner_token', return_value='owner-123')
    @patch('mes_dashboard.routes.resource_history_routes.enqueue_job_dynamic')
    def test_owner_in_params_dict(self, mock_enqueue, _mock_owner, _mock_avail):
        """owner must be inside _params dict forwarded to enqueue_job_dynamic (AC-7).

        Asserts via call_args.kwargs["params"]["owner"] — per-kwarg assertion,
        not assert_called_once_with().
        """
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_enqueue.return_value = ("job-owner-check-001", None)

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                self._post_query("2024-01-01", "2024-07-20")

        # Assert per-kwarg: params dict must contain owner
        call_args = mock_enqueue.call_args
        params_dict = call_args.kwargs.get("params", {})
        self.assertEqual(
            params_dict.get("owner"), "owner-123",
            f"owner must be inside params dict (AC-7); got params={params_dict!r}"
        )

    # ── AC-5: env var defaults pinned ────────────────────────────────────────

    def test_resource_async_enabled_default_is_true(self):
        """RESOURCE_ASYNC_ENABLED module constant must default to True (AC-5).

        Tests via monkeypatch.setattr pattern by checking the live module constant
        (env vars are module-level — setenv has no effect post-import).
        """
        import importlib
        import mes_dashboard.routes.resource_history_routes as _rmod
        _old = os.environ.pop("RESOURCE_ASYNC_ENABLED", None)
        try:
            importlib.reload(_rmod)
            self.assertTrue(
                _rmod.RESOURCE_ASYNC_ENABLED,
                f"RESOURCE_ASYNC_ENABLED must default True, got {_rmod.RESOURCE_ASYNC_ENABLED!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_ASYNC_ENABLED"] = _old
            else:
                importlib.reload(_rmod)

    def test_resource_async_day_threshold_default_is_90(self):
        """RESOURCE_ASYNC_DAY_THRESHOLD module constant must default to 90 (AC-5)."""
        import importlib
        import mes_dashboard.routes.resource_history_routes as _rmod
        _old = os.environ.pop("RESOURCE_ASYNC_DAY_THRESHOLD", None)
        try:
            importlib.reload(_rmod)
            self.assertEqual(
                _rmod.RESOURCE_ASYNC_DAY_THRESHOLD, 90,
                f"RESOURCE_ASYNC_DAY_THRESHOLD must default 90, got {_rmod.RESOURCE_ASYNC_DAY_THRESHOLD!r}"
            )
        finally:
            if _old is not None:
                os.environ["RESOURCE_ASYNC_DAY_THRESHOLD"] = _old
            else:
                importlib.reload(_rmod)

    # ── AC-6: enqueue failure → fall through to sync ────────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.resource_history_routes.get_owner_token', return_value='user-token')
    @patch('mes_dashboard.routes.resource_history_routes.enqueue_job_dynamic')
    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
        return_value=(None, None),
    )
    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_enqueue_failure_falls_through_to_sync(
        self, mock_query, _mock_canonical, mock_enqueue, _mock_owner, _mock_avail
    ):
        """enqueue_job_dynamic returning None job_id → falls through to sync 200 (AC-6)."""
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_enqueue.return_value = (None, "queue full")  # enqueue failure
        mock_query.return_value = {
            'query_id': 'sync-fallback-001',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                response = self._post_query("2024-01-01", "2024-07-20")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        mock_query.assert_called_once()

    # ── AC-6: enqueue exception → fall through to sync ──────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.resource_history_routes.get_owner_token', return_value='user-token')
    @patch('mes_dashboard.routes.resource_history_routes.enqueue_job_dynamic')
    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
        return_value=(None, None),
    )
    @patch('mes_dashboard.routes.resource_history_routes.execute_primary_query')
    def test_enqueue_exception_falls_through_to_sync(
        self, mock_query, _mock_canonical, mock_enqueue, _mock_owner, _mock_avail
    ):
        """enqueue_job_dynamic raising exception → falls through to sync 200 silently (AC-6)."""
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_enqueue.side_effect = RuntimeError("Redis connection timeout")
        mock_query.return_value = {
            'query_id': 'sync-exception-001',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                response = self._post_query("2024-01-01", "2024-07-20")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        mock_query.assert_called_once()

    # ── Canonical spool hit skips async dispatch ─────────────────────────────

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.resource_history_routes.get_owner_token', return_value='user-token')
    @patch('mes_dashboard.routes.resource_history_routes.enqueue_job_dynamic')
    @patch(
        'mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
    )
    def test_canonical_spool_hit_on_long_span_returns_200_no_rq(
        self, mock_canonical, mock_enqueue, _mock_owner, _mock_avail
    ):
        """Canonical spool hit → 200 sync even for long-range query; RQ never dispatched.

        After the first RQ job primes the canonical spool, subsequent filter-change
        queries with the same date range must be served from DuckDB (no Oracle,
        no new RQ job) regardless of day_span.
        """
        import mes_dashboard.routes.resource_history_routes as _rmod
        _canonical_result = {
            'query_id': 'canonical-qid-long-001',
            'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
            'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
        }
        mock_canonical.return_value = (_canonical_result, {"canonical_spool_latency_s": 0.3})

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True):
            with patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
                # 200 days span — would normally dispatch RQ, but canonical spool hits first
                response = self._post_query("2024-01-01", "2024-07-20")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['query_id'], 'canonical-qid-long-001')
        # RQ must NOT have been dispatched
        mock_enqueue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
