# -*- coding: utf-8 -*-
"""POST contract tests for reject-history batch-pareto and view endpoints.

Verifies that:
- Endpoints accept POST + JSON body
- Multi-value params arrive as Python lists at the service layer
- Native bool false is not misread as True
- GET with CSV format still works (backward-compat)
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


@pytest.fixture
def client():
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True
    return app.test_client()


def test_reject_batch_pareto_accepts_post(client):
    """POST /api/reject-history/batch-pareto with large arrays must reach service correctly."""
    reasons = [f"Reason{i}" for i in range(30)]
    trend_dates = [f"2025-01-{i + 1:02d}" for i in range(20)]

    payload = {
        "query_id": "TEST-QID-001",
        "reasons": reasons,
        "trend_dates": trend_dates,
        "packages": ["DIP-B", "QFN"],
    }

    with patch("mes_dashboard.routes.reject_history_routes.compute_batch_pareto") as mock_svc:
        mock_svc.return_value = {"by_reason": [], "by_package": [], "_pareto_meta": None}

        resp = client.post("/api/reject-history/batch-pareto", json=payload)

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True

        kwargs = mock_svc.call_args.kwargs
        assert kwargs["query_id"] == "TEST-QID-001"
        assert isinstance(kwargs["reasons"], list)
        assert len(kwargs["reasons"]) == len(reasons)
        assert isinstance(kwargs["trend_dates"], list)
        assert len(kwargs["trend_dates"]) == len(trend_dates)
        assert kwargs["packages"] == ["DIP-B", "QFN"]


def test_reject_view_accepts_post(client):
    """POST /api/reject-history/view must pass correct types to service."""
    payload = {
        "query_id": "TEST-QID-002",
        "packages": ["DIP-B", "QFN", "SOD"],
        "reasons": ["ReasonA", "ReasonB"],
        "page": 2,
        "per_page": 80,
    }

    mock_result = {
        "lots": [],
        "pagination": {"page": 2, "per_page": 80, "total": 0},
        "total_row_count": 0,
    }

    with patch("mes_dashboard.routes.reject_history_routes.apply_view") as mock_svc:
        mock_svc.return_value = mock_result

        resp = client.post("/api/reject-history/view", json=payload)

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True

        kwargs = mock_svc.call_args.kwargs
        assert kwargs["query_id"] == "TEST-QID-002"
        assert isinstance(kwargs["packages"], list)
        assert len(kwargs["packages"]) == 3
        assert isinstance(kwargs["reasons"], list)
        assert isinstance(kwargs["page"], int)
        assert kwargs["page"] == 2
        assert isinstance(kwargs["per_page"], int)
        assert kwargs["per_page"] == 80


def test_reject_view_native_bool_post(client):
    """POST body exclude_material_scrap: false must arrive as False (not True)."""
    payload = {
        "query_id": "TEST-QID-003",
        "exclude_material_scrap": False,
        "include_excluded_scrap": False,
        "exclude_pb_diode": True,
    }

    mock_result = {"lots": [], "pagination": {}, "total_row_count": 0}

    with patch("mes_dashboard.routes.reject_history_routes.apply_view") as mock_svc:
        mock_svc.return_value = mock_result

        resp = client.post("/api/reject-history/view", json=payload)

        assert resp.status_code == 200

        kwargs = mock_svc.call_args.kwargs
        assert kwargs["exclude_material_scrap"] is False, (
            "exclude_material_scrap: false in POST body must not be coerced to True"
        )
        assert kwargs["include_excluded_scrap"] is False
        assert kwargs["exclude_pb_diode"] is True


def test_reject_batch_pareto_get_still_works(client):
    """GET with CSV-format params must still return 200 (backward-compat)."""
    with patch("mes_dashboard.routes.reject_history_routes.compute_batch_pareto") as mock_svc:
        mock_svc.return_value = {"by_reason": [], "_pareto_meta": None}

        resp = client.get(
            "/api/reject-history/batch-pareto"
            "?query_id=TEST-QID-004"
            "&reasons=ReasonA,ReasonB"
            "&packages=DIP-B"
        )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True

        kwargs = mock_svc.call_args.kwargs
        assert kwargs["query_id"] == "TEST-QID-004"
        assert "ReasonA" in (kwargs["reasons"] or [])
        assert "ReasonB" in (kwargs["reasons"] or [])
