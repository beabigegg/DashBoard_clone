# -*- coding: utf-8 -*-
"""Runtime hardening tests for startup security, CSRF, and shutdown lifecycle."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.routes.health_routes import check_database


@pytest.fixture
def testing_app_factory(monkeypatch):
    def _factory(*, csrf_enabled: bool = False):
        from mes_dashboard.routes import auth_routes

        monkeypatch.setenv("REALTIME_EQUIPMENT_CACHE_ENABLED", "false")
        with auth_routes._rate_limit_lock:
            auth_routes._login_attempts.clear()
        db._ENGINE = None
        db._HEALTH_ENGINE = None
        app = create_app("testing")
        app.config["TESTING"] = True
        app.config["CSRF_ENABLED"] = csrf_enabled
        return app

    return _factory


def _shutdown(app):
    shutdown = app.extensions.get("runtime_shutdown")
    if callable(shutdown):
        shutdown()


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("REALTIME_EQUIPMENT_CACHE_ENABLED", "false")
    db._ENGINE = None
    db._HEALTH_ENGINE = None

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


def test_login_post_rejects_missing_csrf(testing_app_factory):
    app = testing_app_factory(csrf_enabled=True)
    client = app.test_client()

    response = client.post("/admin/login", data={"username": "user", "password": "pw"})

    assert response.status_code == 403
    assert "CSRF" in response.get_data(as_text=True)
    _shutdown(app)


def test_login_success_rotates_session_and_clears_legacy_state(testing_app_factory):
    app = testing_app_factory(csrf_enabled=True)
    client = app.test_client()

    client.get("/admin/login")
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "seed-token"
        sess["legacy"] = "keep-me-out"

    with (
        patch("mes_dashboard.routes.auth_routes.authenticate") as mock_auth,
        patch("mes_dashboard.routes.auth_routes.is_admin", return_value=True),
    ):
        mock_auth.return_value = {
            "username": "admin",
            "displayName": "Admin",
            "mail": "admin@example.com",
            "department": "IT",
        }

        response = client.post(
            "/admin/login?next=/",
            data={
                "username": "admin",
                "password": "secret",
                "csrf_token": "seed-token",
            },
            follow_redirects=False,
        )

    assert response.status_code == 302

    with client.session_transaction() as sess:
        assert "legacy" not in sess
        assert "admin" in sess
        assert sess.get("_csrf_token")
        assert sess.get("_csrf_token") != "seed-token"

    _shutdown(app)


def test_runtime_shutdown_hook_invokes_all_cleanup_handlers(testing_app_factory):
    app = testing_app_factory(csrf_enabled=False)

    with (
        patch("mes_dashboard.app.stop_cache_updater") as mock_cache_stop,
        patch("mes_dashboard.app.stop_equipment_status_sync_worker") as mock_sync_stop,
        patch("mes_dashboard.app.close_redis") as mock_close_redis,
        patch("mes_dashboard.app.dispose_engine") as mock_dispose_engine,
    ):
        app.extensions["runtime_shutdown"]()

    mock_cache_stop.assert_called_once()
    mock_sync_stop.assert_called_once()
    mock_close_redis.assert_called_once()
    mock_dispose_engine.assert_called_once()

    _shutdown(app)


def test_health_check_uses_dedicated_health_engine():
    with patch("mes_dashboard.routes.health_routes.get_health_engine") as mock_engine:
        conn_ctx = mock_engine.return_value.connect.return_value
        status, error = check_database()

    assert status == "ok"
    assert error is None
    mock_engine.assert_called_once()
    conn_ctx.__enter__.assert_called_once()


@patch("mes_dashboard.routes.health_routes.check_database", return_value=("ok", None))
@patch("mes_dashboard.routes.health_routes.check_redis", return_value=("ok", None))
@patch("mes_dashboard.routes.health_routes.get_route_cache_status", return_value={"mode": "l1+l2", "degraded": False})
@patch("mes_dashboard.routes.health_routes.get_pool_status", return_value={"saturation": 1.0})
@patch("mes_dashboard.core.circuit_breaker.get_circuit_breaker_status", return_value={"state": "CLOSED"})
def test_health_reports_pool_saturation_degraded_reason(
    _mock_circuit,
    _mock_pool_status,
    _mock_route_cache,
    _mock_redis,
    _mock_db,
    testing_app_factory,
):
    app = testing_app_factory(csrf_enabled=False)
    response = app.test_client().get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["degraded_reason"] == "db_pool_saturated"
    assert payload["resilience"]["recovery_recommendation"]["action"] == "consider_controlled_worker_restart"

    _shutdown(app)


def test_security_headers_applied_globally(testing_app_factory):
    app = testing_app_factory(csrf_enabled=False)
    response = app.test_client().get("/", follow_redirects=True)

    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
    assert "'unsafe-eval'" not in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Referrer-Policy" in response.headers

    _shutdown(app)


def test_hsts_header_enabled_in_production(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-key")
    monkeypatch.setenv("REALTIME_EQUIPMENT_CACHE_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_CONTRACT_ENFORCE", "false")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1")
    db._ENGINE = None
    db._HEALTH_ENGINE = None

    app = create_app("production")
    app.config["TESTING"] = True
    # Simulate HTTPS via trusted proxy header so HSTS is emitted.
    response = app.test_client().get(
        "/",
        follow_redirects=True,
        headers={"X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 200
    assert "Strict-Transport-Security" in response.headers

    _shutdown(app)


def test_hsts_header_omitted_over_plain_http(monkeypatch):
    """HSTS must NOT be sent when the request arrives over plain HTTP."""
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-key")
    monkeypatch.setenv("REALTIME_EQUIPMENT_CACHE_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_CONTRACT_ENFORCE", "false")
    db._ENGINE = None
    db._HEALTH_ENGINE = None

    app = create_app("production")
    app.config["TESTING"] = True
    response = app.test_client().get("/", follow_redirects=True)

    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers

    _shutdown(app)


def test_csp_unsafe_eval_can_be_enabled_via_env(monkeypatch):
    monkeypatch.setenv("CSP_ALLOW_UNSAFE_EVAL", "true")
    # Build app directly to control env behavior.
    monkeypatch.setenv("REALTIME_EQUIPMENT_CACHE_ENABLED", "false")
    db._ENGINE = None
    db._HEALTH_ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True

    response = app.test_client().get("/", follow_redirects=True)
    assert response.status_code == 200
    assert "'unsafe-eval'" in response.headers["Content-Security-Policy"]

    _shutdown(app)


def test_production_trusted_proxy_requires_allowlist(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-key")
    monkeypatch.setenv("REALTIME_EQUIPMENT_CACHE_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_CONTRACT_ENFORCE", "false")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    db._ENGINE = None
    db._HEALTH_ENGINE = None

    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_IPS"):
        create_app("production")
