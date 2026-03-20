# -*- coding: utf-8 -*-
"""Wave B native-route smoke coverage for shell migration."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _login_as_admin(client) -> None:
    with client.session_transaction() as sess:
        sess["user"] = {"username": "A001", "displayName": "Admin", "mail": "admin@test.com", "is_admin": True}


def _build_excel_file() -> io.BytesIO:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "LOT_ID"
    sheet["B1"] = "QTY"
    sheet["A2"] = "LOT001"
    sheet["B2"] = 100
    sheet["A3"] = "LOT002"
    sheet["B3"] = 200

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def test_job_query_native_smoke_query_search_export(client):
    shell = client.get("/portal-shell/job-query?start_date=2026-02-01&end_date=2026-02-11")
    assert shell.status_code == 200

    page = client.get("/job-query", follow_redirects=False)
    assert page.status_code == 302
    assert page.location.endswith("/portal-shell/job-query")

    with (
        patch(
            "mes_dashboard.services.resource_cache.get_all_resources",
            return_value=[
                {
                    "RESOURCEID": "EQ-01",
                    "RESOURCENAME": "Machine-01",
                    "WORKCENTERNAME": "WC-A",
                    "RESOURCEFAMILYNAME": "FAMILY-A",
                }
            ],
        ),
        patch(
            "mes_dashboard.routes.job_query_routes.get_jobs_by_resources",
            return_value={
                "data": [{"JOBID": "JOB001", "RESOURCENAME": "Machine-01"}],
                "total": 1,
                "resource_count": 1,
            },
        ),
        patch(
            "mes_dashboard.routes.job_query_routes.export_jobs_with_history",
            return_value=iter(["JOBID,RESOURCEID\n", "JOB001,EQ-01\n"]),
        ),
    ):
        resources = client.get("/api/job-query/resources")
        assert resources.status_code == 200
        assert resources.get_json()["data"]["total"] == 1

        query = client.post(
            "/api/job-query/jobs",
            json={
                "resource_ids": ["EQ-01"],
                "start_date": "2026-02-01",
                "end_date": "2026-02-11",
            },
        )
        assert query.status_code == 200
        assert query.get_json()["data"]["total"] == 1

        export = client.post(
            "/api/job-query/export",
            json={
                "resource_ids": ["EQ-01"],
                "start_date": "2026-02-01",
                "end_date": "2026-02-11",
            },
        )
        assert export.status_code == 200
        assert "text/csv" in export.content_type


def test_excel_query_native_smoke_upload_detect_query_export(client):
    _login_as_admin(client)

    shell = client.get("/portal-shell/excel-query?mode=upload")
    assert shell.status_code == 200

    page = client.get("/excel-query", follow_redirects=False)
    assert page.status_code == 302
    assert page.location.endswith("/portal-shell/excel-query")

    from mes_dashboard.routes.excel_query_routes import _uploaded_excel_cache

    _uploaded_excel_cache.clear()

    upload = client.post(
        "/api/excel-query/upload",
        data={"file": (_build_excel_file(), "smoke.xlsx")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200
    assert "LOT_ID" in upload.get_json()["data"]["columns"]

    detect = client.post(
        "/api/excel-query/column-type",
        json={"column_name": "LOT_ID"},
    )
    assert detect.status_code == 200
    assert detect.get_json()["data"]["column_name"] == "LOT_ID"

    with (
        patch(
            "mes_dashboard.routes.excel_query_routes.execute_advanced_batch_query",
            return_value={
                "data": [{"LOT_ID": "LOT001", "QTY": 100}],
                "columns": ["LOT_ID", "QTY"],
                "total": 1,
            },
        ),
        patch(
            "mes_dashboard.routes.excel_query_routes.execute_batch_query",
            return_value={
                "data": [{"LOT_ID": "LOT001", "QTY": 100}],
                "columns": ["LOT_ID", "QTY"],
                "total": 1,
            },
        ),
    ):
        query = client.post(
            "/api/excel-query/execute-advanced",
            json={
                "table_name": "DWH.DW_MES_WIP",
                "search_column": "LOT_ID",
                "return_columns": ["LOT_ID", "QTY"],
                "search_values": ["LOT001"],
                "query_type": "in",
            },
        )
        assert query.status_code == 200
        assert query.get_json()["data"]["total"] == 1

        export = client.post(
            "/api/excel-query/export-csv",
            json={
                "table_name": "DWH.DW_MES_WIP",
                "search_column": "LOT_ID",
                "return_columns": ["LOT_ID", "QTY"],
                "search_values": ["LOT001"],
            },
        )
        assert export.status_code == 200
        assert "text/csv" in export.content_type


def test_query_tool_native_smoke_resolve_history_association(client):
    _login_as_admin(client)

    shell = client.get("/portal-shell/query-tool?input_type=lot_id")
    assert shell.status_code == 200

    page = client.get("/query-tool", follow_redirects=False)
    assert page.status_code == 302
    assert page.location.endswith("/portal-shell/query-tool")

    with (
        patch(
            "mes_dashboard.routes.query_tool_routes.resolve_lots",
            return_value={
                "data": [{"container_id": "488103800029578b"}],
                "total": 1,
                "input_count": 1,
                "not_found": [],
            },
        ),
        patch(
            "mes_dashboard.routes.query_tool_routes.get_lot_history",
            return_value={"data": [{"CONTAINERID": "488103800029578b"}], "total": 1},
        ),
        patch(
            "mes_dashboard.routes.query_tool_routes.get_lot_materials",
            return_value={"data": [{"MATERIALLOTID": "MAT001"}], "total": 1},
        ),
    ):
        resolve = client.post(
            "/api/query-tool/resolve",
            json={"input_type": "lot_id", "values": ["GA23100020-A00-001"]},
        )
        assert resolve.status_code == 200
        assert resolve.get_json()["data"]["total"] == 1

        history = client.get("/api/query-tool/lot-history?container_id=488103800029578b")
        assert history.status_code == 200
        assert history.get_json()["data"]["total"] == 1

        associations = client.get(
            "/api/query-tool/lot-associations?container_id=488103800029578b&type=materials"
        )
        assert associations.status_code == 200
        assert associations.get_json()["data"]["total"] == 1


def test_reject_history_native_smoke_query_sections_and_export(client):
    _login_as_admin(client)

    shell = client.get("/portal-shell/reject-history?start_date=2026-02-01&end_date=2026-02-11")
    assert shell.status_code == 200

    page = client.get("/reject-history", follow_redirects=False)
    if page.status_code == 302:
        assert page.status_code == 302
        assert page.location.endswith("/portal-shell/reject-history")
    elif page.status_code == 200:
        assert page.status_code == 200
    else:
        raise AssertionError(f"unexpected status for /reject-history: {page.status_code}")

    with (
        patch(
            "mes_dashboard.routes.reject_history_routes.get_filter_options",
            return_value={
                "workcenter_groups": [{"name": "WB", "sequence": 1}],
                "reasons": ["R1"],
                "meta": {"include_excluded_scrap": False},
            },
        ),
        patch(
            "mes_dashboard.routes.reject_history_routes.query_summary",
            return_value={
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 10,
                "DEFECT_QTY": 2,
                "REJECT_RATE_PCT": 10.0,
                "DEFECT_RATE_PCT": 2.0,
                "REJECT_SHARE_PCT": 83.3333,
                "AFFECTED_LOT_COUNT": 5,
                "AFFECTED_WORKORDER_COUNT": 3,
                "meta": {"include_excluded_scrap": False},
            },
        ),
        patch(
            "mes_dashboard.routes.reject_history_routes.query_trend",
            return_value={
                "items": [
                    {
                        "bucket_date": "2026-02-01",
                        "MOVEIN_QTY": 100,
                        "REJECT_TOTAL_QTY": 10,
                        "DEFECT_QTY": 2,
                        "REJECT_RATE_PCT": 10.0,
                        "DEFECT_RATE_PCT": 2.0,
                    }
                ],
                "granularity": "day",
                "meta": {"include_excluded_scrap": False},
            },
        ),
        patch(
            "mes_dashboard.routes.reject_history_routes.query_dimension_pareto",
            return_value={
                "items": [
                    {
                        "reason": "R1",
                        "category": "CAT1",
                        "metric_value": 10,
                        "pct": 100.0,
                        "cumPct": 100.0,
                    }
                ],
                "metric_mode": "reject_total",
                "pareto_scope": "top80",
                "meta": {"include_excluded_scrap": False},
            },
        ),
        patch(
            "mes_dashboard.routes.reject_history_routes.query_list",
            return_value={
                "items": [
                    {
                        "TXN_DAY": "2026-02-01",
                        "WORKCENTER_GROUP": "WB",
                        "WORKCENTERNAME": "WB01",
                        "LOSSREASONNAME": "R1",
                        "REJECT_TOTAL_QTY": 10,
                        "DEFECT_QTY": 2,
                    }
                ],
                "pagination": {"page": 1, "perPage": 50, "total": 1, "totalPages": 1},
                "meta": {"include_excluded_scrap": False},
            },
        ),
        patch(
            "mes_dashboard.routes.reject_history_routes.export_csv",
            return_value=iter(
                [
                    "TXN_DAY,REJECT_TOTAL_QTY,DEFECT_QTY\n",
                    "2026-02-01,10,2\n",
                ]
            ),
        ),
    ):
        options = client.get("/api/reject-history/options?start_date=2026-02-01&end_date=2026-02-11")
        assert options.status_code == 200
        assert options.get_json()["success"] is True
        assert options.get_json()["data"]["reasons"] == ["R1"]

        summary = client.get("/api/reject-history/summary?start_date=2026-02-01&end_date=2026-02-11")
        assert summary.status_code == 200
        summary_payload = summary.get_json()
        assert summary_payload["success"] is True
        assert summary_payload["data"]["REJECT_TOTAL_QTY"] == 10

        trend = client.get("/api/reject-history/trend?start_date=2026-02-01&end_date=2026-02-11")
        assert trend.status_code == 200
        assert trend.get_json()["success"] is True
        assert trend.get_json()["data"]["items"][0]["bucket_date"] == "2026-02-01"

        pareto = client.get("/api/reject-history/reason-pareto?start_date=2026-02-01&end_date=2026-02-11")
        assert pareto.status_code == 200
        assert pareto.get_json()["success"] is True
        assert pareto.get_json()["data"]["items"][0]["reason"] == "R1"

        detail = client.get("/api/reject-history/list?start_date=2026-02-01&end_date=2026-02-11")
        assert detail.status_code == 200
        assert detail.get_json()["success"] is True
        assert detail.get_json()["data"]["pagination"]["total"] == 1

        export = client.get("/api/reject-history/export?start_date=2026-02-01&end_date=2026-02-11")
        assert export.status_code == 200
        assert "text/csv" in export.content_type
