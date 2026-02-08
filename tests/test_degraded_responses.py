# -*- coding: utf-8 -*-
"""Degraded response contract tests."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.core.database import (
    DatabasePoolExhaustedError,
    DatabaseCircuitOpenError,
)


def _client():
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True

    @app.route("/api/__test__/pool")
    def _pool_error():
        raise DatabasePoolExhaustedError("pool exhausted", retry_after_seconds=7)

    @app.route("/api/__test__/circuit")
    def _circuit_error():
        raise DatabaseCircuitOpenError("circuit open", retry_after_seconds=11)

    return app.test_client()


def test_pool_exhausted_error_handler_contract():
    response = _client().get("/api/__test__/pool")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "7"

    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "DB_POOL_EXHAUSTED"
    assert payload["meta"]["retry_after_seconds"] == 7


def test_circuit_open_error_handler_contract():
    response = _client().get("/api/__test__/circuit")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "11"

    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "CIRCUIT_BREAKER_OPEN"
    assert payload["meta"]["retry_after_seconds"] == 11


@patch(
    "mes_dashboard.routes.wip_routes.get_wip_summary",
    side_effect=DatabasePoolExhaustedError("pool exhausted", retry_after_seconds=5),
)
def test_wip_route_propagates_degraded_contract(_mock_summary):
    response = _client().get("/api/wip/overview/summary")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error"]["code"] == "DB_POOL_EXHAUSTED"


@patch(
    "mes_dashboard.routes.resource_routes.get_resource_status_summary",
    side_effect=DatabasePoolExhaustedError("pool exhausted", retry_after_seconds=9),
)
def test_resource_route_propagates_degraded_contract(_mock_summary):
    response = _client().get("/api/resource/status/summary")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error"]["code"] == "DB_POOL_EXHAUSTED"
    assert payload["meta"]["retry_after_seconds"] == 9


@patch(
    "mes_dashboard.routes.dashboard_routes.query_dashboard_kpi",
    side_effect=DatabaseCircuitOpenError("circuit open", retry_after_seconds=13),
)
def test_dashboard_route_propagates_degraded_contract(_mock_kpi):
    response = _client().post("/api/dashboard/kpi", json={})
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error"]["code"] == "CIRCUIT_BREAKER_OPEN"
    assert payload["meta"]["retry_after_seconds"] == 13
