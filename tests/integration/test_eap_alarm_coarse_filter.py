# -*- coding: utf-8 -*-
"""Mock-based integration tests for EAP ALARM coarse-filter new dims (AC-1 / AC-2).

All tests are fully mock-based (monkeypatched read_sql_df_slow, spool dir,
RQ logging, register_spool_file, enqueue_query_job).  No real Oracle or Redis
required, so the marker is integration (PR-gate) not integration_real.

Test classes:
  TestEapAlarmWorkerFnNewDims — AC-1/AC-2 lot_ids IN clause + EXISTS semi-join
                                 SQL assertions; route per-kwarg forwarding.
  TestEapAlarmFineFilterRouteParams — product-dim fine filters + pareto dim /
                                 trend group_by route param validation & forwarding.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


# ---------------------------------------------------------------------------
# TestEapAlarmWorkerFnNewDims — AC-1/AC-2 new dim forwarding
# ---------------------------------------------------------------------------

class TestEapAlarmWorkerFnNewDims:
    """AC-1/AC-2: Worker fn passes lot_ids IN clause and EXISTS clauses in SQL."""

    def _base_monkeypatch(self, monkeypatch, tmp_path, captured_sql: list, captured_params: list):
        """Common monkeypatches for worker SQL capture tests."""
        import pandas as pd

        def mock_read_sql(sql, params=None, timeout_seconds=None, caller="unknown"):
            captured_sql.append(sql)
            if params:
                captured_params.append(dict(params))
            return pd.DataFrame(columns=["EVENT_ID", "EQP_ID", "EQP_TYPE", "LOT_ID", "EVENT_TYPE", "ALARM_ID", "ALARM_TIME"])

        monkeypatch.setattr("mes_dashboard.core.database.read_sql_df_slow", mock_read_sql)
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

    def test_lot_ids_in_clause_present_in_sql(self, tmp_path, monkeypatch):
        """AC-1: lot_ids → 'LOT_ID IN' present in Oracle SQL."""
        captured_sql: list = []
        captured_params: list = []
        self._base_monkeypatch(monkeypatch, tmp_path, captured_sql, captured_params)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job(
            job_id="test-lot-in",
            date_from="2025-01-01",
            date_to="2025-01-07",
            lot_ids=["LOT-001", "LOT-002"],
        )

        assert any("LOT_ID IN" in sql for sql in captured_sql), (
            f"'LOT_ID IN' must appear in Oracle SQL when lot_ids supplied. "
            f"Captured SQL: {captured_sql}"
        )

    def test_exists_clause_present_in_sql_for_pj_types(self, tmp_path, monkeypatch):
        """AC-2: pj_types → EXISTS clause in Oracle SQL."""
        captured_sql: list = []
        captured_params: list = []
        self._base_monkeypatch(monkeypatch, tmp_path, captured_sql, captured_params)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job(
            job_id="test-exists-pjt",
            date_from="2025-01-01",
            date_to="2025-01-07",
            pj_types=["TypeA"],
        )

        assert any("EXISTS" in sql and "PJ_TYPE" in sql for sql in captured_sql), (
            f"EXISTS clause for PJ_TYPE must appear in SQL. Captured: {captured_sql}"
        )

    def test_exists_clause_present_in_sql_for_product_lines(self, tmp_path, monkeypatch):
        """AC-2: product_lines → EXISTS clause in Oracle SQL."""
        captured_sql: list = []
        captured_params: list = []
        self._base_monkeypatch(monkeypatch, tmp_path, captured_sql, captured_params)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job(
            job_id="test-exists-pln",
            date_from="2025-01-01",
            date_to="2025-01-07",
            product_lines=["LineA"],
        )

        assert any("EXISTS" in sql and "PRODUCTLINENAME" in sql for sql in captured_sql), (
            f"EXISTS clause for PRODUCTLINENAME must appear in SQL. Captured: {captured_sql}"
        )

    def test_exists_clause_present_in_sql_for_pj_bops(self, tmp_path, monkeypatch):
        """AC-2: pj_bops → EXISTS clause in Oracle SQL."""
        captured_sql: list = []
        captured_params: list = []
        self._base_monkeypatch(monkeypatch, tmp_path, captured_sql, captured_params)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job(
            job_id="test-exists-bop",
            date_from="2025-01-01",
            date_to="2025-01-07",
            pj_bops=["BopA"],
        )

        assert any("EXISTS" in sql and "PJ_BOP" in sql for sql in captured_sql), (
            f"EXISTS clause for PJ_BOP must appear in SQL. Captured: {captured_sql}"
        )

    def test_multiple_dims_produce_multiple_exists_clauses(self, tmp_path, monkeypatch):
        """AC-2: pj_types + product_lines → 2 separate EXISTS clauses (AND-semantics)."""
        captured_sql: list = []
        captured_params: list = []
        self._base_monkeypatch(monkeypatch, tmp_path, captured_sql, captured_params)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job(
            job_id="test-multi-exists",
            date_from="2025-01-01",
            date_to="2025-01-07",
            pj_types=["TypeA"],
            product_lines=["LineA"],
        )

        for sql in captured_sql:
            exists_count = sql.count("EXISTS")
            if exists_count > 0:
                assert exists_count >= 2, (
                    f"Two product dims must produce at least 2 EXISTS clauses, got {exists_count}"
                )
                break

    def test_route_forwards_lot_ids_per_kwarg(self, monkeypatch):
        """Route forwards lot_ids per-kwarg to enqueue (AC-1 route forwarding)."""
        captured: dict = {}

        def mock_enqueue_query_job(job_type, owner, params, **kw):
            captured.update(params)
            return ("test-job-001", None, None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            mock_enqueue_query_job,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/eap-alarm/spool",
                json={
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-07",
                    "lot_ids": ["LOT-001", "LOT-002"],
                    "pj_types": ["TypeA"],
                    "product_lines": ["LineB"],
                    "pj_bops": ["BopC"],
                },
                content_type="application/json",
            )

        assert resp.status_code in (200, 202), f"Expected 200/202, got {resp.status_code}: {resp.get_json()}"
        assert captured.get("lot_ids") == ["LOT-001", "LOT-002"], (
            f"lot_ids must be forwarded per-kwarg, got: {captured.get('lot_ids')!r}"
        )
        assert captured.get("pj_types") == ["TypeA"], (
            f"pj_types must be forwarded per-kwarg, got: {captured.get('pj_types')!r}"
        )
        assert captured.get("product_lines") == ["LineB"], (
            f"product_lines must be forwarded per-kwarg, got: {captured.get('product_lines')!r}"
        )
        assert captured.get("pj_bops") == ["BopC"], (
            f"pj_bops must be forwarded per-kwarg, got: {captured.get('pj_bops')!r}"
        )


# ---------------------------------------------------------------------------
# TestEapAlarmFineFilterRouteParams — new fine filters + dim/group_by params
# ---------------------------------------------------------------------------

class TestEapAlarmFineFilterRouteParams:
    """Routes parse product-dim fine filters and validate dim/group_by enums."""

    def _spool_hit(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
            lambda key: "/tmp/fake_spool.parquet",
        )

    def test_summary_forwards_product_fine_filters(self, monkeypatch):
        """GET /summary forwards lot_id/pj_type/product_line/pj_bop per-kwarg."""
        self._spool_hit(monkeypatch)
        captured: Dict[str, Any] = {}

        def _mock_get_summary(spool_path, filters):
            captured["filters"] = dict(filters)
            return {"total_alarm_count": 0}

        monkeypatch.setattr(
            "mes_dashboard.services.eap_alarm_service.get_summary",
            _mock_get_summary,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get(
                "/api/eap-alarm/summary?query_id=k1"
                "&lot_id[]=LOT-001&lot_id[]=LOT-002"
                "&pj_type[]=TypeA&product_line[]=LineB&pj_bop[]=BopC"
            )

        assert resp.status_code == 200, resp.get_json()
        filters = captured["filters"]
        assert filters["lot_id"] == ["LOT-001", "LOT-002"]
        assert filters["pj_type"] == ["TypeA"]
        assert filters["product_line"] == ["LineB"]
        assert filters["pj_bop"] == ["BopC"]

    def test_pareto_forwards_dim(self, monkeypatch):
        """GET /pareto?dim=product_line forwards dim kwarg to service."""
        self._spool_hit(monkeypatch)
        captured: Dict[str, Any] = {}

        def _mock_get_pareto(spool_path, filters, dim="alarm_text"):
            captured["dim"] = dim
            return {"items": [], "dim": dim, "total": 0}

        monkeypatch.setattr(
            "mes_dashboard.services.eap_alarm_service.get_pareto",
            _mock_get_pareto,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/eap-alarm/pareto?query_id=k1&dim=product_line")

        assert resp.status_code == 200, resp.get_json()
        assert captured["dim"] == "product_line"

    def test_pareto_invalid_dim_returns_400(self, monkeypatch):
        """GET /pareto with unknown dim → 400 VALIDATION_ERROR (closed enum)."""
        self._spool_hit(monkeypatch)
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/eap-alarm/pareto?query_id=k1&dim=bogus")
        assert resp.status_code == 400, resp.get_json()

    def test_trend_forwards_group_by(self, monkeypatch):
        """GET /trend?group_by=pj_type forwards group_by kwarg to service."""
        self._spool_hit(monkeypatch)
        captured: Dict[str, Any] = {}

        def _mock_get_trend(spool_path, filters, granularity="day", group_by="alarm_text"):
            captured["granularity"] = granularity
            captured["group_by"] = group_by
            return {"labels": [], "series": [], "group_by": group_by}

        monkeypatch.setattr(
            "mes_dashboard.services.eap_alarm_service.get_trend",
            _mock_get_trend,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get(
                "/api/eap-alarm/trend?query_id=k1&granularity=hour&group_by=pj_type"
            )

        assert resp.status_code == 200, resp.get_json()
        assert captured["group_by"] == "pj_type"
        assert captured["granularity"] == "hour"

    def test_trend_invalid_group_by_returns_400(self, monkeypatch):
        """GET /trend with unknown group_by → 400 VALIDATION_ERROR (closed enum)."""
        self._spool_hit(monkeypatch)
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/eap-alarm/trend?query_id=k1&group_by=bogus")
        assert resp.status_code == 400, resp.get_json()
