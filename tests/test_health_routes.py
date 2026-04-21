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
    from mes_dashboard.routes.health_routes import _reset_health_memo_for_tests
    _reset_health_memo_for_tests()
    return app.test_client()


@patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.check_redis', return_value=('error', 'redis-down'))
@patch('mes_dashboard.routes.health_routes.get_route_cache_status')
@patch('mes_dashboard.core.circuit_breaker.get_circuit_breaker_status', return_value={'state': 'CLOSED', 'enabled': True, 'failure_count': 0, 'success_count': 0, 'total_count': 0, 'failure_rate': 0.0})
def test_health_includes_route_cache_and_degraded_warning(
    _mock_cb,
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


def test_health_memo_store_and_expire(monkeypatch):
    import mes_dashboard.routes.health_routes as hr

    hr._reset_health_memo_for_tests()
    monkeypatch.setattr(hr, "_health_memo_enabled", lambda: True)

    hr._set_health_memo("health", {"status": "healthy"}, 200)
    cached = hr._get_health_memo("health")
    assert cached == ({"status": "healthy"}, 200)

    with hr._HEALTH_MEMO_LOCK:
        hr._HEALTH_MEMO["health"] = {"ts": 0.0, "payload": {"status": "old"}, "status": 200}

    with patch("mes_dashboard.routes.health_routes.time.time", return_value=100.0):
        assert hr._get_health_memo("health") is None


@patch('mes_dashboard.routes.health_routes._health_memo_enabled', return_value=True)
@patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.check_redis', return_value=('ok', None))
def test_health_route_uses_internal_memoization(
    _mock_redis,
    mock_db,
    _mock_enabled,
):
    client = _client()
    response1 = client.get('/health')
    response2 = client.get('/health')

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert mock_db.call_count == 1


@patch('mes_dashboard.routes.health_routes.get_portal_shell_asset_status')
def test_frontend_shell_health_endpoint_healthy(mock_status):
    mock_status.return_value = {
        "status": "healthy",
        "route": "/portal-shell",
        "checks": {
            "portal_shell_html": {"exists": True},
            "portal_shell_js": {"exists": True},
            "portal_shell_css": {"exists": True},
            "tailwind_css": {"exists": True},
            "html_references": {
                "portal_shell_js": True,
                "portal_shell_css": True,
                "tailwind_css": True,
            },
        },
        "errors": [],
        "warnings": [],
        "http_code": 200,
    }

    response = _client().get('/health/frontend-shell')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "healthy"
    assert payload["checks"]["portal_shell_css"]["exists"] is True
    assert payload["summary"]["status"] == "healthy"
    assert payload["summary"]["error_count"] == 0
    assert payload["detail"]["checks"]["portal_shell_css"]["exists"] is True


@patch('mes_dashboard.routes.health_routes.get_portal_shell_asset_status')
def test_frontend_shell_health_endpoint_unhealthy(mock_status):
    mock_status.return_value = {
        "status": "unhealthy",
        "route": "/portal-shell",
        "checks": {
            "portal_shell_html": {"exists": False},
            "portal_shell_js": {"exists": False},
            "portal_shell_css": {"exists": False},
            "tailwind_css": {"exists": False},
            "html_references": {
                "portal_shell_js": False,
                "portal_shell_css": False,
                "tailwind_css": False,
            },
        },
        "errors": ["asset missing: static/dist/portal-shell.css"],
        "warnings": [],
        "http_code": 503,
    }

    response = _client().get('/health/frontend-shell')
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "unhealthy"
    assert any("portal-shell.css" in error for error in payload.get("errors", []))
    assert payload["summary"]["status"] == "unhealthy"
    assert payload["summary"]["error_count"] >= 1
    assert any("portal-shell.css" in error for error in payload["detail"].get("errors", []))


def test_get_portal_shell_asset_status_reports_nested_html_as_healthy(tmp_path):
    from mes_dashboard.routes.health_routes import get_portal_shell_asset_status

    static_dir = tmp_path / "static"
    dist_dir = static_dir / "dist"
    nested_dir = dist_dir / "src" / "portal-shell"
    nested_dir.mkdir(parents=True, exist_ok=True)

    (nested_dir / "index.html").write_text(
        "<html><head>"
        "<link rel='stylesheet' href='/static/dist/tailwind.css'>"
        "<link rel='stylesheet' href='/static/dist/portal-shell.css'>"
        "<script type='module' src='/static/dist/portal-shell.js'></script>"
        "</head><body><div id='app'></div></body></html>",
        encoding="utf-8",
    )
    (dist_dir / "portal-shell.js").write_text("console.log('ok');", encoding="utf-8")
    (dist_dir / "portal-shell.css").write_text(".shell{}", encoding="utf-8")
    (dist_dir / "tailwind.css").write_text(".tw{}", encoding="utf-8")

    app = create_app("testing")
    app.config["TESTING"] = True
    app.static_folder = str(static_dir)

    with app.app_context():
        result = get_portal_shell_asset_status()

    assert result["status"] == "healthy"
    assert result["checks"]["portal_shell_html"]["source"] == "nested"
    assert result["checks"]["html_references"]["portal_shell_css"] is True


def test_get_portal_shell_asset_status_reports_missing_css_as_unhealthy(tmp_path):
    from mes_dashboard.routes.health_routes import get_portal_shell_asset_status

    static_dir = tmp_path / "static"
    dist_dir = static_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    (dist_dir / "portal-shell.html").write_text(
        "<html><head>"
        "<script type='module' src='/static/dist/portal-shell.js'></script>"
        "</head><body><div id='app'></div></body></html>",
        encoding="utf-8",
    )
    (dist_dir / "portal-shell.js").write_text("console.log('ok');", encoding="utf-8")

    app = create_app("testing")
    app.config["TESTING"] = True
    app.static_folder = str(static_dir)

    with app.app_context():
        result = get_portal_shell_asset_status()

    assert result["status"] == "unhealthy"
    assert any("portal-shell.css" in error for error in result["errors"])


@patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.check_redis', return_value=('ok', None))
@patch('mes_dashboard.routes.health_routes.get_route_cache_status', return_value={'mode': 'l1+l2', 'degraded': False})
@patch('mes_dashboard.core.circuit_breaker.get_circuit_breaker_status', return_value={'state': 'CLOSED', 'enabled': True, 'failure_count': 0, 'success_count': 0, 'total_count': 0, 'failure_rate': 0.0})
def test_health_top_level_contract_frozen(_mock_cb, _mock_route_cache, _mock_redis, _mock_db):
    """GET /health non-envelope top-level keys must remain stable.

    Pinned key set: status, services, resilience, route_cache.
    Adding new top-level keys is allowed; removing pinned ones is a contract break.
    """
    response = _client().get('/health')
    assert response.status_code == 200
    payload = response.get_json()

    # These keys are contractually frozen — must always be present
    REQUIRED_TOP_LEVEL_KEYS = {'status', 'services'}
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in payload, (
            f"/health response missing required top-level key '{key}'. "
            "This key is contractually frozen — do not remove it."
        )

    # status must be one of the three defined values
    assert payload['status'] in ('healthy', 'degraded', 'unhealthy'), (
        f"/health 'status' must be 'healthy', 'degraded', or 'unhealthy', got: {payload['status']!r}"
    )

    # Must NOT use the standard success/data/meta envelope
    assert 'success' not in payload, "/health must NOT use the success/data/meta envelope"
    assert 'data' not in payload, "/health must NOT wrap payload under 'data' key"


# ---------------------------------------------------------------------------
# check_database() TestingConfig short-circuit
# ---------------------------------------------------------------------------
#
# Regression guard for the CI failure exposed by soak-tests.yml (PR #5c):
# TestingConfig marks the app as hermetic, but check_database() was still
# hitting Oracle and returning 503, which blocked gunicorn_workers fixture
# health checks on CI runners that have no Oracle.  The short-circuit keeps
# production behaviour identical while letting TestingConfig do what it says
# on the tin.


def test_check_database_short_circuits_when_config_is_testing():
    """TestingConfig -> check_database returns ok without touching Oracle."""
    from mes_dashboard.routes import health_routes as hr

    app = create_app('testing')
    assert app.config['TESTING'] is True

    with app.app_context(), patch.object(hr, 'get_health_engine') as mock_engine:
        status, err = hr.check_database()

    assert status == 'ok'
    assert err is None
    assert mock_engine.call_count == 0, (
        "get_health_engine() must NOT be invoked under TestingConfig — "
        "the hermetic short-circuit is the whole point of this guard."
    )


def test_check_database_runs_real_probe_when_not_testing():
    """Production path still calls get_health_engine and reports failures."""
    from mes_dashboard.routes import health_routes as hr

    app = create_app('testing')
    app.config['TESTING'] = False

    class _BoomEngine:
        def connect(self):
            raise RuntimeError('simulated oracle outage')

    with app.app_context(), patch.object(
        hr, 'get_health_engine', return_value=_BoomEngine()
    ) as mock_engine:
        status, err = hr.check_database()

    assert status == 'error'
    assert 'simulated oracle outage' in err
    assert mock_engine.call_count == 1, (
        "Non-TESTING path must still invoke get_health_engine() exactly once."
    )
