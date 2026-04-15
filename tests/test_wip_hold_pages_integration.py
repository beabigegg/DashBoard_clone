# -*- coding: utf-8 -*-
"""Integration tests for WIP Overview / WIP Detail / Hold Detail page contracts."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


@pytest.fixture
def client():
    """Create a test client with isolated DB engine state."""
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True
    return app.test_client()


def test_wip_pages_render_vite_assets(client):
    """Core WIP/Hold direct entries should redirect to canonical shell routes."""
    overview = client.get("/wip-overview", follow_redirects=False)
    detail = client.get("/wip-detail", follow_redirects=False)
    hold = client.get("/hold-detail?reason=YieldLimit", follow_redirects=False)

    assert overview.status_code == 302
    assert detail.status_code == 302
    assert hold.status_code == 302

    assert overview.location.endswith("/portal-shell/wip-overview")
    assert detail.location.endswith("/portal-shell/wip-detail")
    assert hold.location.endswith("/portal-shell/hold-detail?reason=YieldLimit")


def test_wip_overview_and_detail_status_parameter_contract(client):
    """Status/type params should be accepted across overview and detail APIs."""
    with (
        patch("mes_dashboard.routes.wip_routes.get_wip_matrix") as mock_matrix,
        patch("mes_dashboard.routes.wip_routes.get_wip_detail") as mock_detail,
    ):
        mock_matrix.return_value = {
            "workcenters": [],
            "packages": [],
            "matrix": {},
            "workcenter_totals": {},
            "package_totals": {},
            "grand_total": 0,
        }
        mock_detail.return_value = {
            "workcenter": "TMTT",
            "summary": {
                "total_lots": 0,
                "on_equipment_lots": 0,
                "waiting_lots": 0,
                "hold_lots": 0,
            },
            "specs": [],
            "lots": [],
            "pagination": {"page": 1, "page_size": 100, "total_count": 0, "total_pages": 1},
            "sys_date": None,
        }

        matrix_resp = client.get("/api/wip/overview/matrix?type=PJA3460&status=queue")
        detail_resp = client.get("/api/wip/detail/TMTT?type=PJA3460&status=queue&page=1&page_size=100")

        assert matrix_resp.status_code == 200
        assert detail_resp.status_code == 200
        assert json.loads(matrix_resp.data)["success"] is True
        assert json.loads(detail_resp.data)["success"] is True

        mock_matrix.assert_called_once_with(
            include_dummy=False,
            workorder=None,
            lotid=None,
            status="QUEUE",
            hold_type=None,
            package=None,
            pj_type="PJA3460",
            firstname=None,
            waferdesc=None,
        )
        mock_detail.assert_called_once_with(
            workcenter="TMTT",
            package=None,
            pj_type="PJA3460",
            status="QUEUE",
            hold_type=None,
            workorder=None,
            lotid=None,
            firstname=None,
            waferdesc=None,
            include_dummy=False,
            page=1,
            page_size=100,
        )


def test_wip_overview_post_avoids_url_length_limit(client):
    """POST body should be accepted on summary, matrix, and filter-options.

    This covers the 'Request Line is too large' regression: when many lot IDs
    or work orders are selected the query string exceeds Gunicorn's 4094-byte
    limit.  The frontend now sends POST with a JSON body; the backend must
    accept it and pass parsed params to the service layer identically to GET.
    """
    many_lots = ",".join(f"LOT{i:04d}" for i in range(60))  # ~420 chars just for lotid
    payload = {"lotid": many_lots, "type": "PJA3460", "status": "queue"}

    with (
        patch("mes_dashboard.routes.wip_routes.get_wip_summary") as mock_summary,
        patch("mes_dashboard.routes.wip_routes.get_wip_matrix") as mock_matrix,
        patch("mes_dashboard.routes.wip_routes.get_wip_filter_options") as mock_opts,
    ):
        mock_summary.return_value = {
            "totalLots": 0, "totalQtyPcs": 0, "byWipStatus": {}, "dataUpdateDate": None,
        }
        mock_matrix.return_value = {
            "workcenters": [], "packages": [], "matrix": {},
            "workcenter_totals": {}, "package_totals": {}, "grand_total": 0,
        }
        mock_opts.return_value = {
            "workorders": [], "lotids": [], "packages": [],
            "types": [], "firstnames": [], "waferdescs": [],
        }

        summary_resp = client.post(
            "/api/wip/overview/summary",
            json=payload,
        )
        matrix_resp = client.post(
            "/api/wip/overview/matrix",
            json=payload,
        )
        opts_resp = client.post(
            "/api/wip/meta/filter-options",
            json={"lotid": many_lots, "type": "PJA3460"},
        )

        assert summary_resp.status_code == 200
        assert matrix_resp.status_code == 200
        assert opts_resp.status_code == 200
        assert json.loads(summary_resp.data)["success"] is True
        assert json.loads(matrix_resp.data)["success"] is True
        assert json.loads(opts_resp.data)["success"] is True

        mock_summary.assert_called_once_with(
            include_dummy=False,
            workorder=None,
            lotid=many_lots,
            package=None,
            pj_type="PJA3460",
            firstname=None,
            waferdesc=None,
        )
        mock_matrix.assert_called_once_with(
            include_dummy=False,
            workorder=None,
            lotid=many_lots,
            status="QUEUE",
            hold_type=None,
            package=None,
            pj_type="PJA3460",
            firstname=None,
            waferdesc=None,
        )
        mock_opts.assert_called_once_with(
            include_dummy=False,
            workorder=None,
            lotid=many_lots,
            package=None,
            pj_type="PJA3460",
            firstname=None,
            waferdesc=None,
            status=None,
            hold_type=None,
        )


def test_wip_detail_post_avoids_url_length_limit(client):
    """POST body should be accepted on /api/wip/detail/<workcenter>."""
    many_lots = ",".join(f"LOT{i:04d}" for i in range(60))

    with patch("mes_dashboard.routes.wip_routes.get_wip_detail") as mock_detail:
        mock_detail.return_value = {
            "workcenter": "TMTT",
            "summary": {
                "total_lots": 0, "on_equipment_lots": 0,
                "waiting_lots": 0, "hold_lots": 0,
            },
            "specs": [],
            "lots": [],
            "pagination": {"page": 1, "page_size": 20, "total_count": 0, "total_pages": 1},
            "sys_date": None,
        }

        resp = client.post(
            "/api/wip/detail/TMTT",
            json={"lotid": many_lots, "type": "PJA3460", "page": 1, "page_size": 20},
        )

        assert resp.status_code == 200
        assert json.loads(resp.data)["success"] is True

        mock_detail.assert_called_once_with(
            workcenter="TMTT",
            package=None,
            pj_type="PJA3460",
            status=None,
            hold_type=None,
            workorder=None,
            lotid=many_lots,
            firstname=None,
            waferdesc=None,
            include_dummy=False,
            page=1,
            page_size=20,
        )


def test_wip_overview_get_still_works_after_post_support(client):
    """Adding POST must not break existing GET callers."""
    with patch("mes_dashboard.routes.wip_routes.get_wip_matrix") as mock_matrix:
        mock_matrix.return_value = {
            "workcenters": [], "packages": [], "matrix": {},
            "workcenter_totals": {}, "package_totals": {}, "grand_total": 0,
        }

        resp = client.get("/api/wip/overview/matrix?type=PJA3460&status=queue")

        assert resp.status_code == 200
        assert json.loads(resp.data)["success"] is True
        mock_matrix.assert_called_once_with(
            include_dummy=False,
            workorder=None,
            lotid=None,
            status="QUEUE",
            hold_type=None,
            package=None,
            pj_type="PJA3460",
            firstname=None,
            waferdesc=None,
        )


def test_hold_detail_api_contract_flow(client):
    """Hold detail summary/distribution/lots should all accept the same reason."""
    with (
        patch("mes_dashboard.routes.hold_routes.get_hold_detail_summary") as mock_summary,
        patch("mes_dashboard.routes.hold_routes.get_hold_detail_distribution") as mock_distribution,
        patch("mes_dashboard.routes.hold_routes.get_hold_detail_lots") as mock_lots,
    ):
        mock_summary.return_value = {
            "totalLots": 10,
            "totalQty": 1000,
            "avgAge": 1.2,
            "maxAge": 5.0,
            "workcenterCount": 2,
        }
        mock_distribution.return_value = {
            "byWorkcenter": [],
            "byPackage": [],
            "byAge": [],
        }
        mock_lots.return_value = {
            "lots": [],
            "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 1},
            "filters": {"workcenter": None, "package": None, "ageRange": None},
        }

        reason = "YieldLimit"
        summary_resp = client.get(f"/api/wip/hold-detail/summary?reason={reason}")
        dist_resp = client.get(f"/api/wip/hold-detail/distribution?reason={reason}")
        lots_resp = client.get(
            f"/api/wip/hold-detail/lots?reason={reason}&workcenter=DA&package=DIP-B&age_range=1-3&page=2&per_page=80"
        )

        assert summary_resp.status_code == 200
        assert dist_resp.status_code == 200
        assert lots_resp.status_code == 200

        assert json.loads(summary_resp.data)["success"] is True
        assert json.loads(dist_resp.data)["success"] is True
        assert json.loads(lots_resp.data)["success"] is True

        mock_summary.assert_called_once_with(reason=reason, include_dummy=False)
        mock_distribution.assert_called_once_with(reason=reason, include_dummy=False)
        mock_lots.assert_called_once_with(
            reason=reason,
            workcenter="DA",
            package="DIP-B",
            age_range="1-3",
            include_dummy=False,
            page=2,
            page_size=80,
        )
