# -*- coding: utf-8 -*-
"""Tests for analytics routes — anomaly summary endpoint.

Covers:
- Cache hit: warm summary with cache_state='warm'
- Cold-miss disambiguation: cache_state='cold' when cache is empty
- Envelope meta fields (timestamp, app_version, cache_state)
- Feature-disabled 404
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


@pytest.fixture
def client():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app.test_client()


class TestAnomalySummaryEnvelope:
    """Anomaly summary must return standard envelope with meta.cache_state."""

    def test_cache_miss_returns_cold_state(self, client):
        """When cache is empty, response must include meta.cache_state='cold'."""
        with patch(
            'mes_dashboard.routes.analytics_routes.get_cached_summary',
            return_value=None
        ), patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            True
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['meta']['cache_state'] == 'cold'
        assert data['meta']['source'] == 'cache_miss'

    def test_cache_hit_returns_warm_state(self, client):
        """When cache is populated, response must include meta.cache_state='warm'."""
        cached_payload = {
            "data": {"total_count": 3, "severity": "warning", "breakdown": {}},
            "meta": {"detector_run_at": "2024-01-01T00:00:00"},
        }
        with patch(
            'mes_dashboard.routes.analytics_routes.get_cached_summary',
            return_value=cached_payload
        ), patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            True
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['meta']['cache_state'] == 'warm'
        assert data['data']['total_count'] == 3

    def test_cache_hit_preserves_existing_cache_state(self, client):
        """If the cached payload already has cache_state, it must be preserved."""
        cached_payload = {
            "data": {"total_count": 1, "severity": "ok", "breakdown": {}},
            "meta": {"cache_state": "stale"},
        }
        with patch(
            'mes_dashboard.routes.analytics_routes.get_cached_summary',
            return_value=cached_payload
        ), patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            True
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        data = resp.get_json()
        assert data['meta']['cache_state'] == 'stale'

    def test_envelope_has_app_version(self, client):
        """Every response must carry meta.app_version."""
        with patch(
            'mes_dashboard.routes.analytics_routes.get_cached_summary',
            return_value=None
        ), patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            True
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        data = resp.get_json()
        assert 'app_version' in data['meta'], "meta.app_version is required in every response"
        assert data['meta']['app_version']  # must be non-empty

    def test_envelope_has_timestamp(self, client):
        """Every response must carry meta.timestamp."""
        with patch(
            'mes_dashboard.routes.analytics_routes.get_cached_summary',
            return_value=None
        ), patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            True
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        data = resp.get_json()
        assert 'timestamp' in data['meta']

    def test_feature_disabled_returns_not_found(self, client):
        """When analytics is disabled, endpoint must return 404 envelope."""
        with patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            False
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'NOT_FOUND'

    def test_cold_miss_data_shape(self, client):
        """Cold-miss response must have total_count=0 and severity='ok'."""
        with patch(
            'mes_dashboard.routes.analytics_routes.get_cached_summary',
            return_value=None
        ), patch(
            'mes_dashboard.routes.analytics_routes._ANALYTICS_ENABLED',
            True
        ):
            resp = client.get('/api/analytics/anomaly-summary')

        data = resp.get_json()
        assert data['data']['total_count'] == 0
        assert data['data']['severity'] == 'ok'
        assert isinstance(data['data']['breakdown'], dict)
