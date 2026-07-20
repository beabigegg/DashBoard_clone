# -*- coding: utf-8 -*-
"""Contract tests for the 7 /api/uph-performance/* endpoints (add-uph-performance-page).

Response-shape assertions per api-contract.md lines 266-272 and data-shape
§3.29. Mock-based (no live Oracle/Redis) -- validates the envelope/field
shapes the frontend and the response-shape-adr0007 gate depend on.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


def _empty_spool(tmp_path) -> str:
    path = str(tmp_path / "spool.parquet")
    schema = pa.schema([
        pa.field("LOT_ID", pa.string()),
        pa.field("EQUIPMENT_ID", pa.string()),
        pa.field("EQUIPMENT_FAMILY", pa.string()),
        pa.field("EVENT_TIME", pa.timestamp("us")),
        pa.field("PARAMETER_NAME", pa.string()),
        pa.field("UPH_VALUE", pa.float64()),
        pa.field("WORKCENTERNAME", pa.string()),
        pa.field("MODEL", pa.string()),
        pa.field("DB_WB_LABEL", pa.string()),
        pa.field("PACKAGE", pa.string()),
        pa.field("PJ_TYPE", pa.string()),
        pa.field("PJ_BOP", pa.string()),
        pa.field("PJ_FUNCTION", pa.string()),
        pa.field("DIE_COUNT", pa.string()),
        pa.field("WIRE_COUNT", pa.string()),
        pa.field("coarse_filter_hash", pa.string()),
    ])
    table = pa.table({f.name: pa.array([], type=f.type) for f in schema}, schema=schema)
    pq.write_table(table, path)
    return path


class TestSpoolEnvelopes:
    def test_spool_202_envelope_matches_schema(self, monkeypatch):
        """UphPerformanceSpoolJobAccepted: async, query_id, job_id, status_url."""
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: ("job-1", None, None),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "u",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 202
        data = resp.get_json()["data"]
        assert data["async"] is True
        assert isinstance(data["query_id"], str)
        assert isinstance(data["job_id"], str)
        assert isinstance(data["status_url"], str)

    def test_spool_200_spool_hit_envelope_matches_schema(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake.parquet",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["async"] is False
        assert isinstance(data["query_id"], str)
        assert "job_id" not in data
        assert "status_url" not in data

    def test_spool_503_service_unavailable_has_retry_after(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 503
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert resp.headers.get("Retry-After") is not None

    def test_spool_400_validation_error_envelope(self):
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02", "families": ["GWBK"]},
                content_type="application/json",
            )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "VALIDATION_ERROR"


class TestFilterOptionsShapes:
    def test_filter_options_response_shape(self, tmp_path, monkeypatch):
        spool_path = _empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/filter-options?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        for key in (
            "equipment_id_options", "workcenter_name_options",
            "package_options", "pj_type_options",
            "die_count_options", "wire_count_options",
        ):
            assert key in data
            assert isinstance(data[key], list)

    def test_product_filter_options_response_shape(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.services.container_filter_cache.get_filter_options",
            lambda selected=None: {"pj_types": ["T1"], "packages": ["P1"]},
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/product-filter-options")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["pj_types"] == ["T1"]
        assert data["product_lines"] == ["P1"]

    def test_product_filter_options_500_shape(self, monkeypatch):
        def _raise(*a, **kw):
            raise RuntimeError("cache unavailable")

        monkeypatch.setattr(
            "mes_dashboard.services.container_filter_cache.get_filter_options",
            _raise,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/product-filter-options")
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["success"] is False


class TestTrendRankingDetailShapes:
    def test_trend_response_shape_labels_series_group_by(self, tmp_path, monkeypatch):
        spool_path = _empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/trend?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert set(data.keys()) >= {"labels", "series", "group_by"}
        assert isinstance(data["labels"], list)
        assert isinstance(data["series"], list)
        assert data["group_by"] == "family"

    def test_ranking_response_shape_items_pj_types(self, tmp_path, monkeypatch):
        spool_path = _empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/ranking?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert set(data.keys()) >= {"items", "pj_types"}
        assert isinstance(data["items"], list)
        assert isinstance(data["pj_types"], list)

    def test_detail_response_shape_rows_meta(self, tmp_path, monkeypatch):
        spool_path = _empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/detail?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "rows" in data and isinstance(data["rows"], list)
        assert "meta" in data
        for key in ("page", "per_page", "total_count", "total_pages"):
            assert key in data["meta"]


def _populated_spool_with_die_wire_counts(tmp_path) -> str:
    """Spool with 2 rows carrying distinct DIE_COUNT/WIRE_COUNT (VARCHAR, per
    the CAST-to-VARCHAR exact-match filter architecture) -- exercises the new
    die_count/wire_count fine-filter axis + trend group_by dimension end to
    end (_EXACT_FILTER_COLUMNS / GROUP_DIMENSIONS wiring)."""
    import pandas as pd

    path = str(tmp_path / "spool_die_wire.parquet")
    df = pd.DataFrame({
        "LOT_ID": ["LOT001", "LOT002"],
        "EQUIPMENT_ID": ["GDBA-01", "GDBA-02"],
        "EQUIPMENT_FAMILY": ["GDBA", "GDBA"],
        "EVENT_TIME": pd.to_datetime(["2026-01-01 01:00:00", "2026-01-01 02:00:00"]),
        "PARAMETER_NAME": ["BondUPH", "BondUPH"],
        "UPH_VALUE": [100.0, 200.0],
        "WORKCENTERNAME": ["WC1", "WC2"],
        "MODEL": ["M1", "M2"],
        "DB_WB_LABEL": [None, None],
        "PACKAGE": ["PKG-A", "PKG-B"],
        "PJ_TYPE": ["TYPE-A", "TYPE-B"],
        "PJ_BOP": ["BOP-A", "BOP-B"],
        "PJ_FUNCTION": ["FUNC-A", "FUNC-B"],
        "DIE_COUNT": ["12", "24"],
        "WIRE_COUNT": ["4", "8"],
        "coarse_filter_hash": ["abcd1234", "abcd1234"],
    })
    df.to_parquet(path, engine="pyarrow")
    return path


class TestDieWireCountAxes:
    """New fine-filter axes + trend group_by values (DIE_COUNT/WIRE_COUNT via
    the PRODUCTNAME -> DWH.MES_PRODUCT bridge) -- wired purely through
    _EXACT_FILTER_COLUMNS / GROUP_DIMENSIONS, no bespoke handling."""

    def test_filter_options_returns_die_and_wire_count_options(self, tmp_path, monkeypatch):
        spool_path = _populated_spool_with_die_wire_counts(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/filter-options?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert sorted(data["die_count_options"]) == ["12", "24"]
        assert sorted(data["wire_count_options"]) == ["4", "8"]

    def test_trend_group_by_die_count_groups_correctly(self, tmp_path, monkeypatch):
        spool_path = _populated_spool_with_die_wire_counts(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/trend?query_id=qid&group_by=die_count")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["group_by"] == "die_count"
        names = sorted(s["name"] for s in data["series"])
        assert names == ["12", "24"]

    def test_trend_group_by_wire_count_groups_correctly(self, tmp_path, monkeypatch):
        spool_path = _populated_spool_with_die_wire_counts(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/trend?query_id=qid&group_by=wire_count")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["group_by"] == "wire_count"
        names = sorted(s["name"] for s in data["series"])
        assert names == ["4", "8"]

    def test_die_count_wire_count_filter_narrows_rows(self, tmp_path, monkeypatch):
        """die_count[]/wire_count[] fine filters narrow the detail rows exactly
        like the existing package/pj_type axes (_build_filter_where)."""
        spool_path = _populated_spool_with_die_wire_counts(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/detail?query_id=qid&die_count[]=12")
        assert resp.status_code == 200
        rows = resp.get_json()["data"]["rows"]
        assert len(rows) == 1
        assert rows[0]["lot_id"] == "LOT001"


class TestOpenApiSchemaResolution:
    def test_openapi_schema_resolves_for_all_6_endpoints(self):
        """AC-7: contracts/openapi.json resolves for all 6 GET/status endpoints
        (the 7th, POST /spool, is covered by TestSpoolEnvelopes above and the
        typed UphPerformanceSpoolJobAccepted schema)."""
        openapi_path = Path(__file__).parent.parent.parent / "contracts" / "openapi.json"
        if not openapi_path.exists():
            pytest.skip("contracts/openapi.json not found -- run cdd-kit openapi export first")

        doc = json.loads(openapi_path.read_text(encoding="utf-8"))
        paths = doc.get("paths", {})

        expected = [
            ("post", "/api/uph-performance/spool"),
            ("get", "/api/uph-performance/spool/status"),
            ("get", "/api/uph-performance/filter-options"),
            ("get", "/api/uph-performance/product-filter-options"),
            ("get", "/api/uph-performance/trend"),
            ("get", "/api/uph-performance/ranking"),
            ("get", "/api/uph-performance/detail"),
        ]
        for method, path in expected:
            assert path in paths, f"{path} missing from openapi.json paths"
            assert method in paths[path], f"{method.upper()} {path} missing from openapi.json"
