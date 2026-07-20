# -*- coding: utf-8 -*-
"""Integration tests for UPH Performance RQ async dispatch and route behavior.

pytestmark = pytest.mark.integration_real
(mirrors tests/integration/test_eap_alarm_rq_async.py -- mock-based, no real
Redis/Oracle required to run; marked integration_real only so the Tier-1
`unit-mock-integration` CI gate command (--ignore=tests/integration) skips
this file, per test-plan.md Test Families Required.)

Test classes:
  TestUphPerformanceSpoolTrigger  -- POST /spool -> 202/400/503 branches
  TestUphPerformanceSpoolCacheHit -- spool-hit -> 200
  TestUphPerformanceWorkerBridges -- worker fn bridges container/resource dims
  TestUphPerformanceFineFilters   -- trend/ranking/detail route forwarding + shapes
  TestUphPerformanceResilience    -- Oracle fault / Redis unavailable -> no fallback
"""
from __future__ import annotations

import importlib
import uuid
from typing import Any, Dict
from unittest.mock import patch

import pandas as pd
import pytest

pytestmark = pytest.mark.integration_real


def _reset_registry() -> None:
    from mes_dashboard.services import job_registry as _reg_mod
    _reg_mod._REGISTRY.clear()


def _reload_uph_performance_worker() -> None:
    import mes_dashboard.workers.uph_performance_worker as _w
    _reset_registry()
    importlib.reload(_w)


def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


# ---------------------------------------------------------------------------
# TestUphPerformanceSpoolTrigger
# ---------------------------------------------------------------------------

class TestUphPerformanceSpoolTrigger:
    """AC-2/AC-5: POST /api/uph-performance/spool -> 202/400/503."""

    def test_enqueue_to_uph_performance_queue(self, monkeypatch):
        import mes_dashboard.workers.uph_performance_worker as _w  # noqa: F401
        from mes_dashboard.services.job_registry import get_job_type_config

        config = get_job_type_config("uph-performance")
        assert config is not None
        assert config.queue_name == "uph-performance-query"
        assert config.always_async is True

        captured: Dict[str, Any] = {}

        def _mock_enqueue_query_job(job_type, owner, params, **kwargs):
            captured["job_type"] = job_type
            captured["params"] = dict(params)
            return ("uph-performance-test-001", None, None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            _mock_enqueue_query_job,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={
                    "date_from": "2026-01-01",
                    "date_to": "2026-01-02",
                    "families": ["GDBA"],
                },
                content_type="application/json",
            )

        data = resp.get_json()
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {data}"
        assert data["success"] is True
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]
        assert "query_id" in data["data"]
        assert captured.get("job_type") == "uph-performance"
        assert captured["params"].get("families") == ["GDBA"]

    def test_post_spool_missing_date_returns_400(self):
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_post_spool_family_outside_enum_returns_400(self):
        """UPH-02: GWBK/GWMT/GPTA outside {GDBA, GWBA} -> 400."""
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={
                    "date_from": "2026-01-01",
                    "date_to": "2026-01-02",
                    "families": ["GWBK"],
                },
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_spool_miss_returns_202_with_job_id(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: ("job-abc", None, None),
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 202
        assert resp.get_json()["data"]["job_id"] == "job-abc"

    def test_spool_miss_worker_unavailable_returns_503_no_fallback(self, monkeypatch):
        """UPH-ASYNC/ASYNC-06: queue unavailable -> 503, never a sync downgrade."""
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
        data = resp.get_json()
        assert data["success"] is False
        assert resp.headers.get("Retry-After") is not None

    def test_env_flag_off_is_pure_kill_switch_503_on_miss(self, monkeypatch):
        """UPH-ASYNC: flag off -> job type never registered -> 503 on spool-miss."""
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._UPH_PERFORMANCE_USE_UNIFIED_JOB",
            False,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )
        _reset_registry()

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 503

    def test_route_forwards_families_workcenter_package_pj_type_equipment_ids_per_kwarg(self, monkeypatch):
        """Route forwards every coarse dim per-kwarg (non-default values), not assert_called_once_with()."""
        captured: Dict[str, Any] = {}

        def _mock_enqueue_query_job(job_type, owner, params, **kwargs):
            captured.update(params)
            return ("job-xyz", None, None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            _mock_enqueue_query_job,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            client.post(
                "/api/uph-performance/spool",
                json={
                    "date_from": "2026-01-01",
                    "date_to": "2026-01-02",
                    "families": ["GDBA"],
                    "workcenter_names": ["焊接_DB_1線"],
                    "packages": ["PKG-A"],
                    "pj_types": ["TYPE-A"],
                    "equipment_ids": ["GDBA-01"],
                },
                content_type="application/json",
            )

        assert captured.get("families") == ["GDBA"]
        assert captured.get("workcenter_names") == ["焊接_DB_1線"]
        assert captured.get("packages") == ["PKG-A"]
        assert captured.get("pj_types") == ["TYPE-A"]
        assert captured.get("equipment_ids") == ["GDBA-01"]

    def test_async_route_worker_signature_bind(self):
        """Route↔worker signature contract: enqueue kwargs must bind cleanly."""
        import inspect
        from mes_dashboard.workers.uph_performance_worker import execute_uph_performance_unified_job

        kwargs = {
            "job_id": "job-1",
            "date_from": "2026-01-01",
            "date_to": "2026-01-02",
            "families": ["GDBA"],
            "workcenter_names": [],
            "packages": [],
            "pj_types": [],
            "equipment_ids": [],
        }
        inspect.signature(execute_uph_performance_unified_job).bind(**kwargs)


# ---------------------------------------------------------------------------
# TestUphPerformanceSpoolCacheHit
# ---------------------------------------------------------------------------

class TestUphPerformanceSpoolCacheHit:
    def test_spool_cache_hit_returns_200(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake_spool.parquet",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["async"] is False
        assert "query_id" in data["data"]


# ---------------------------------------------------------------------------
# TestUphPerformanceWorkerBridges — AC-4
# ---------------------------------------------------------------------------

class TestUphPerformanceWorkerBridges:
    def test_worker_fn_bridges_container_and_resource_dims(self, tmp_path, monkeypatch):
        """LOT_ID -> DW_MES_CONTAINER and EQUIPMENT_ID -> DW_MES_RESOURCE bridges resolve;
        DB/WB label comes from workcenter_groups, not prefix enumeration (AC-4/UPH-05)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid-bridge", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01",
        })
        job.pre_query()
        job._spool_path = str(tmp_path / "spool.parquet")

        import pyarrow as pa
        import pyarrow.parquet as pq

        events_table = pa.table({
            "LOT_ID": ["LOT001"],
            "EQUIPMENT_ID": ["GDBA-01"],
            "EQUIPMENT_FAMILY": ["GDBA"],
            "EVENT_TIME": pd.to_datetime(["2026-01-01 01:00:00"]),
            "PARAMETER_NAME": ["BondUPH"],
            "UPH_VALUE_RAW": ["100.0"],
        })
        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        pq.write_table(events_table, chunk_dir / "chunk-0000-0000.parquet")

        lot_product_df = pd.DataFrame({
            "LOT_ID": ["LOT001"], "PACKAGE": ["PKG-A"], "PJ_TYPE": ["TYPE-A"],
            "PJ_BOP": ["BOP-A"], "PJ_FUNCTION": ["FUNC-A"], "PRODUCTNAME": ["PROD-A"],
        })
        workcenter_df = pd.DataFrame({
            "EQUIPMENT_ID": ["GDBA-01"], "WORKCENTERNAME": ["焊接_DB_1線"],
            "DB_WB_LABEL": ["焊接_DB"],
        })
        mes_product_df = pd.DataFrame({
            "PRODUCTNAME": ["PROD-A"], "DIE_COUNT": [12], "WIRE_COUNT": [4],
        })

        with patch(
            "mes_dashboard.workers.uph_performance_worker._safe_lot_product_df",
            return_value=lot_product_df,
        ), patch(
            "mes_dashboard.workers.uph_performance_worker._safe_workcenter_df",
            return_value=workcenter_df,
        ), patch(
            "mes_dashboard.workers.uph_performance_worker._safe_mes_product_df",
            return_value=mes_product_df,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            return_value=True,
        ):
            spool_path = job.post_aggregate(None)

        df = pq.read_table(spool_path).to_pandas()
        assert df.loc[0, "PACKAGE"] == "PKG-A"
        assert df.loc[0, "PJ_TYPE"] == "TYPE-A"
        assert df.loc[0, "WORKCENTERNAME"] == "焊接_DB_1線"
        assert df.loc[0, "DB_WB_LABEL"] == "焊接_DB"
        assert df.loc[0, "DIE_COUNT"] == "12"
        assert df.loc[0, "WIRE_COUNT"] == "4"

    def test_worker_fn_time_chunks_never_exceed_6h(self):
        """Structural: chunk_strategy=TIME + window size (UPH-01)."""
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob, _build_time_chunks

        assert UphPerformanceJob.chunk_strategy == ChunkStrategy.TIME
        chunks = _build_time_chunks("2026-01-01", "2026-01-05")
        from datetime import datetime, timedelta
        for c in chunks:
            start = datetime.strptime(c["chunk_start"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(c["chunk_end"], "%Y-%m-%d %H:%M:%S")
            assert end - start <= timedelta(hours=6)

    def test_worker_fn_oracle_sql_contains_last_update_time_predicate(self):
        sql_text = (
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "src" / "mes_dashboard" / "sql" / "uph_performance.sql"
        ).read_text(encoding="utf-8")
        assert "LAST_UPDATE_TIME" in sql_text
        assert ":chunk_start" in sql_text
        assert ":chunk_end" in sql_text


# ---------------------------------------------------------------------------
# TestUphPerformanceFineFilters — trend/ranking/detail
# ---------------------------------------------------------------------------

class TestUphPerformanceFineFilters:
    def test_ranking_endpoint_pj_type_filter_independent_of_global_pj_type(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def _mock_get_ranking(spool_path, pj_types=None):
            captured["pj_types"] = pj_types
            return {"items": [], "pj_types": []}

        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake.parquet",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.uph_performance_service.get_ranking",
            _mock_get_ranking,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get(
                "/api/uph-performance/ranking?query_id=qid&pj_type[]=TYPE-A"
            )
        assert resp.status_code == 200
        assert captured["pj_types"] == ["TYPE-A"]

    def test_ranking_pj_type_empty_while_global_pj_type_populated(self, monkeypatch):
        """Ranking's own pj_type[] axis stays empty even if a request also carries an
        unrelated global-style pj_type param elsewhere -- ranking must not read it."""
        captured: Dict[str, Any] = {}

        def _mock_get_ranking(spool_path, pj_types=None):
            captured["pj_types"] = pj_types
            return {"items": [], "pj_types": []}

        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake.parquet",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.uph_performance_service.get_ranking",
            _mock_get_ranking,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/ranking?query_id=qid")
        assert resp.status_code == 200
        assert captured["pj_types"] == []

    def test_ranking_sorted_ascending_by_avg_uph(self, tmp_path):
        import duckdb
        import pyarrow as pa
        import pyarrow.parquet as pq
        from mes_dashboard.services.uph_performance_service import get_ranking

        spool_path = str(tmp_path / "spool.parquet")
        table = pa.table({
            "EQUIPMENT_ID": ["E1", "E2", "E3"],
            "WORKCENTERNAME": ["WC1", "WC2", "WC3"],
            "DB_WB_LABEL": ["焊接_DB", "焊接_DB", None],
            "PJ_TYPE": ["T1", "T1", "T1"],
            "UPH_VALUE": [50.0, 10.0, 30.0],
        })
        pq.write_table(table, spool_path)

        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_ranking(spool_path, pj_types=["T1"])

        avg_uphs = [item["avg_uph"] for item in result["items"]]
        assert avg_uphs == sorted(avg_uphs)

    def test_ranking_avg_uph_null_not_zero_for_zero_sample(self, tmp_path):
        import duckdb
        import pyarrow as pa
        import pyarrow.parquet as pq
        from mes_dashboard.services.uph_performance_service import get_ranking

        spool_path = str(tmp_path / "spool.parquet")
        table = pa.table({
            "EQUIPMENT_ID": ["E1"],
            "WORKCENTERNAME": ["WC1"],
            "DB_WB_LABEL": [None],
            "PJ_TYPE": ["T1"],
            "UPH_VALUE": pa.array([None], type=pa.float64()),
        })
        pq.write_table(table, spool_path)

        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_ranking(spool_path, pj_types=["T1"])

        assert result["items"][0]["avg_uph"] is None
        assert result["items"][0]["sample_count"] == 0

    def test_trend_group_by_default_family(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def _mock_get_trend(spool_path, filters=None, group_by="family"):
            captured["group_by"] = group_by
            return {"labels": [], "series": [], "group_by": group_by}

        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake.parquet",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.uph_performance_service.get_trend",
            _mock_get_trend,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/trend?query_id=qid")
        assert resp.status_code == 200
        assert captured["group_by"] == "family"

    def test_trend_group_by_unknown_value_returns_400(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake.parquet",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/trend?query_id=qid&group_by=bogus")
        assert resp.status_code == 400

    def test_trend_missing_hour_bucket_is_null_not_zero(self, tmp_path):
        import duckdb
        import pyarrow as pa
        import pyarrow.parquet as pq
        from mes_dashboard.services.uph_performance_service import get_trend

        spool_path = str(tmp_path / "spool.parquet")
        table = pa.table({
            "EQUIPMENT_FAMILY": ["GDBA", "GWBA"],
            "EVENT_TIME": pd.to_datetime(["2026-01-01 01:00:00", "2026-01-01 02:00:00"]),
            "UPH_VALUE": [100.0, 90.0],
        })
        pq.write_table(table, spool_path)

        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_trend(spool_path, group_by="family")

        gdba_series = next(s for s in result["series"] if s["name"] == "GDBA")
        # GDBA has no data at the 02:00 bucket -> must be null, never 0.
        idx = result["labels"].index("2026-01-01 02:00")
        assert gdba_series["data"][idx] is None

    def test_detail_per_page_capped_at_200(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def _mock_get_detail(spool_path, filters=None, page=1, per_page=50):
            captured["per_page"] = per_page
            return {"rows": [], "meta": {"page": page, "per_page": per_page, "total_count": 0, "total_pages": 1}}

        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: "/tmp/fake.parquet",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.uph_performance_service.get_detail",
            _mock_get_detail,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/detail?query_id=qid&per_page=500")
        assert resp.status_code == 200
        # The service itself caps at 200 -- route just forwards the raw value.
        from mes_dashboard.services.uph_performance_service import _DETAIL_PER_PAGE_MAX
        assert _DETAIL_PER_PAGE_MAX == 200


# ---------------------------------------------------------------------------
# TestUphPerformanceResilience
# ---------------------------------------------------------------------------

class TestUphPerformanceResilience:
    def test_oracle_fault_mid_chunk_no_partial_spool(self, tmp_path, monkeypatch):
        """An Oracle fault during chunk fan-out must not leave a partial/corrupt
        canonical spool file in place (mirrors downtime/eap_alarm fault injection)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid-fault", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01",
        })

        class _BoomReader:
            def chunk_iter(self, sql, params):
                raise RuntimeError("simulated Oracle fault")

        job.pre_query()
        job._reader = _BoomReader()

        with pytest.raises(RuntimeError):
            job.run()

        assert not (tmp_path / "uph_performance" / f"{job._spool_key}.parquet").exists()

    def test_redis_unavailable_returns_503_no_legacy_fallback(self, monkeypatch):
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
