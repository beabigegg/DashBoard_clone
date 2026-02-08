# -*- coding: utf-8 -*-
"""Health route telemetry tests."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


def _client():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app.test_client()


@patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.check_redis', return_value=('error', 'redis-down'))
@patch('mes_dashboard.routes.health_routes.get_route_cache_status')
def test_health_includes_route_cache_and_degraded_warning(
    mock_route_cache,
    _mock_redis,
    _mock_db,
):
    mock_route_cache.return_value = {
        'mode': 'l1-only',
        'degraded': True,
        'reads_total': 10,
        'l1_hits': 9,
        'misses': 1,
    }

    response = _client().get('/health')
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['status'] == 'degraded'
    assert payload['route_cache']['mode'] == 'l1-only'
    assert payload['route_cache']['degraded'] is True
    assert 'resilience' in payload
    assert payload['resilience']['thresholds']['restart_churn_threshold'] >= 1
    assert payload['resilience']['recovery_recommendation']['action'] == 'continue_degraded_mode'
    assert any('degraded' in warning.lower() for warning in payload.get('warnings', []))


@patch('mes_dashboard.core.permissions.is_admin_logged_in', return_value=True)
@patch('mes_dashboard.core.metrics.get_metrics_summary', return_value={'p50_ms': 1, 'p95_ms': 2, 'p99_ms': 3, 'count': 10, 'slow_count': 0, 'slow_rate': 0.0, 'worker_pid': 123})
@patch('mes_dashboard.core.circuit_breaker.get_circuit_breaker_status', return_value={'state': 'CLOSED'})
@patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.check_redis', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.get_route_cache_status')
def test_deep_health_exposes_route_cache_telemetry(
    mock_route_cache,
    _mock_redis,
    _mock_db,
    _mock_cb,
    _mock_metrics,
    _mock_admin,
):
    mock_route_cache.return_value = {
        'mode': 'l1+l2',
        'degraded': False,
        'reads_total': 20,
        'l1_hits': 8,
        'l2_hits': 11,
        'misses': 1,
    }

    response = _client().get('/health/deep')
    assert response.status_code == 200
    payload = response.get_json()

    route_cache = payload['checks']['route_cache']
    assert route_cache['mode'] == 'l1+l2'
    assert route_cache['reads_total'] == 20
    assert route_cache['degraded'] is False
    assert payload['resilience']['recovery_recommendation']['action'] == 'none'
    assert payload['resilience']['thresholds']['pool_saturation_warning'] >= 0.5
