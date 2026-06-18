# -*- coding: utf-8 -*-
"""Integration tests for EAP ALARM RQ async dispatch and worker-fn parity.

pytestmark = pytest.mark.integration_real
(requires real Redis + RQ worker environment to run fully)

Test classes:
  TestEapAlarmSpoolTrigger   — POST /spool → 202, job_id returned
  TestEapAlarmWorkerFn       — mock Oracle + parquet write → parquet exists, correct columns
  TestEapAlarmSpoolCacheHit  — second POST with same params → 200 (spool hit)
  test_spool_miss_returns_410  — GET /filter-options with unknown query_id → 410
  test_detail_no_extra_oracle_query — GET /detail reads DETAIL_PARAMS from spool; 0 extra Oracle calls
"""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_registry() -> None:
    """Clear the job registry for clean re-registration tests."""
    from mes_dashboard.services import job_registry as _reg_mod
    _reg_mod._REGISTRY.clear()


def _reload_eap_alarm_worker() -> None:
    """Reload eap_alarm_worker so register_job_type() re-fires."""
    import mes_dashboard.workers.eap_alarm_worker as _w
    _reset_registry()
    importlib.reload(_w)


def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


# ---------------------------------------------------------------------------
# TestEapAlarmSpoolTrigger — POST /spool → 202, job_id returned
# ---------------------------------------------------------------------------

class TestEapAlarmSpoolTrigger:
    """AC-2: POST /api/eap-alarm/spool → 202 + job_id when spool is cold."""

    def test_enqueue_to_eap_alarm_queue(self, monkeypatch):
        """enqueue_job is called with correct queue_name and prefix."""
        import mes_dashboard.workers.eap_alarm_worker as _w  # noqa: F401
        from mes_dashboard.services.job_registry import get_job_type_config

        config = get_job_type_config("eap-alarm")
        assert config is not None, (
            '"eap-alarm" job type must be registered after importing eap_alarm_worker'
        )
        assert config.queue_name == "eap-alarm-query", (
            f"Expected queue_name='eap-alarm-query', got {config.queue_name!r}"
        )

        captured: Dict[str, Any] = {}

        def _mock_enqueue(**kwargs):
            captured.update(kwargs)
            return ("eap-alarm-test-001", None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_job",
            _mock_enqueue,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
            lambda key: None,  # cold spool
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
                    "eqp_types": ["GDBA", "GCBA"],
                },
                content_type="application/json",
            )

        # We expect 202 but the enqueue mock returns success
        data = resp.get_json()
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {data}"
        assert data["success"] is True
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]
        assert "query_id" in data["data"]

        assert captured.get("queue_name") == "eap-alarm-query", (
            f"Expected queue_name='eap-alarm-query', got {captured.get('queue_name')!r}"
        )
        assert captured.get("prefix") == "eap-alarm", (
            f"Expected prefix='eap-alarm', got {captured.get('prefix')!r}"
        )

    def test_post_spool_missing_date_returns_400(self, monkeypatch):
        """Missing date_from → 400 VALIDATION_ERROR (EA-03)."""
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/eap-alarm/spool",
                json={
                    "date_to": "2025-01-07",
                    "eqp_types": ["GDBA"],
                },
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_post_spool_invalid_eqp_type_returns_400(self, monkeypatch):
        """Invalid eqp_type → 400 VALIDATION_ERROR (EA-07)."""
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/eap-alarm/spool",
                json={
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-07",
                    "eqp_types": ["INVALID_TYPE"],
                },
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_post_spool_empty_eqp_types_returns_400(self, monkeypatch):
        """Empty eqp_types → 400 VALIDATION_ERROR (EA-07)."""
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/eap-alarm/spool",
                json={
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-07",
                    "eqp_types": [],
                },
                content_type="application/json",
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestEapAlarmWorkerFn — mock Oracle + parquet write
# ---------------------------------------------------------------------------

class TestEapAlarmWorkerFn:
    """AC-2/AC-3: Worker fn runs Oracle JOIN, decodes AlarmCategory, writes parquet."""

    def _build_mock_df(self) -> pd.DataFrame:
        """Build a synthetic Oracle result for the main query."""
        import pandas as pd
        from datetime import datetime
        return pd.DataFrame({
            "EVENT_ID": ["AAABBB000001", "AAABBB000002"],
            "EQP_ID": ["GDBA-001", "GCBA-002"],
            "EQP_TYPE": ["GDBA", "GCBA"],
            "LOT_ID": ["LOT001", None],
            "ALARM_TEXT": ["Motor Overheat", "Pressure Low"],
            "ALARM_CATEGORY_CODE": [1, 99],
            "ALARM_TIME": [datetime(2025, 1, 3, 10, 0, 0), datetime(2025, 1, 4, 12, 30, 0)],
        })

    def test_worker_fn_writes_parquet_with_correct_columns(self, tmp_path, monkeypatch):
        """Worker fn writes parquet with all 10 §3.17 columns."""
        mock_df = self._build_mock_df()
        mock_detail_df = pd.DataFrame({"EVENT_ID": [], "PARAM_NAME": [], "PARAM_VALUE": []})

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            lambda sql, params=None, timeout_seconds=None, caller="unknown": (
                mock_df if "AlarmText" not in sql else mock_detail_df
            ),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR",
            str(tmp_path),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_TTL",
            3600,
        )
        monkeypatch.setattr(
            "mes_dashboard.rq_worker_preload.ensure_rq_logging",
            lambda: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda prefix, job_id, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.complete_job",
            lambda prefix, job_id, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            lambda ns, qid, path, row_count, ttl_seconds=None: True,
        )

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        job_id = f"test-{uuid.uuid4().hex[:8]}"
        run_eap_alarm_query_job(
            job_id=job_id,
            date_from="2025-01-01",
            date_to="2025-01-07",
            eqp_types=["GDBA", "GCBA"],
        )

        # Find the parquet file
        parquet_files = list(tmp_path.glob("*.parquet"))
        assert len(parquet_files) == 1, f"Expected 1 parquet file, found: {parquet_files}"

        import pyarrow.parquet as pq
        table = pq.read_table(str(parquet_files[0]))
        cols = set(table.schema.names)

        expected_cols = {
            "EVENT_ID", "EQP_ID", "EQP_TYPE", "LOT_ID",
            "ALARM_TEXT", "ALARM_CATEGORY_CODE", "ALARM_CATEGORY",
            "ALARM_TIME", "DETAIL_PARAMS", "eqp_types_filter",
        }
        assert expected_cols == cols, f"Column mismatch: {cols} vs {expected_cols}"

    def test_worker_fn_decodes_alarm_category(self, tmp_path, monkeypatch):
        """AlarmCategory code 1 → '設備'; code 99 → '未知'."""
        mock_df = self._build_mock_df()
        mock_detail_df = pd.DataFrame({"EVENT_ID": [], "PARAM_NAME": [], "PARAM_VALUE": []})

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            lambda sql, params=None, timeout_seconds=None, caller="unknown": (
                mock_df if "AlarmText" not in sql else mock_detail_df
            ),
        )
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job("test-decode", "2025-01-01", "2025-01-07", ["GDBA", "GCBA"])

        import pyarrow.parquet as pq
        table = pq.read_table(str(list(tmp_path.glob("*.parquet"))[0]))
        df = table.to_pandas()
        cats = dict(zip(df["ALARM_CATEGORY_CODE"].tolist(), df["ALARM_CATEGORY"].tolist()))
        assert cats.get(1.0) == "設備" or cats.get(1) == "設備", f"Code 1 should decode to '設備', got {cats}"
        # 99 is unknown
        assert cats.get(99.0) == "未知" or cats.get(99) == "未知", f"Code 99 should decode to '未知', got {cats}"

    def test_worker_fn_progress_milestones(self, tmp_path, monkeypatch):
        """Progress milestones 5 → 15 → 90 → 100 must fire in order (coarse bracket)."""
        mock_df = self._build_mock_df()
        mock_detail_df = pd.DataFrame({"EVENT_ID": [], "PARAM_NAME": [], "PARAM_VALUE": []})

        progress_calls = []

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            lambda sql, params=None, timeout_seconds=None, caller="unknown": (
                mock_df if "AlarmText" not in sql else mock_detail_df
            ),
        )
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda prefix, job_id, **kw: progress_calls.append(kw.get("pct")),
        )
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job("test-milestone", "2025-01-01", "2025-01-07", ["GDBA"])

        # Must include milestones 5, 15, 90, 100 (order matters — never decreasing)
        pct_values = [int(p) for p in progress_calls if p is not None]
        for milestone in [5, 15, 90, 100]:
            assert milestone in pct_values, (
                f"Progress milestone {milestone}% missing from {pct_values}"
            )
        # Must be non-decreasing
        for i in range(len(pct_values) - 1):
            assert pct_values[i] <= pct_values[i + 1], (
                f"Progress must not decrease: {pct_values}"
            )

    def test_worker_fn_oracle_sql_contains_last_update_time_predicate(self, tmp_path, monkeypatch):
        """Oracle SQL must contain LAST_UPDATE_TIME BETWEEN predicate (EA-03)."""
        captured_sql = []
        mock_df = self._build_mock_df()

        def mock_read_sql(sql, params=None, timeout_seconds=None, caller="unknown"):
            captured_sql.append(sql)
            if "AlarmText" in sql:
                return pd.DataFrame({"EVENT_ID": [], "PARAM_NAME": [], "PARAM_VALUE": []})
            return mock_df

        monkeypatch.setattr("mes_dashboard.core.database.read_sql_df_slow", mock_read_sql)
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job("test-sql", "2025-01-01", "2025-01-07", ["GDBA"])

        assert any("LAST_UPDATE_TIME" in sql and "BETWEEN" in sql for sql in captured_sql), (
            f"Oracle SQL must contain LAST_UPDATE_TIME BETWEEN predicate (EA-03). "
            f"Captured SQL: {captured_sql}"
        )


# ---------------------------------------------------------------------------
# TestEapAlarmSpoolCacheHit — second POST returns 200 (spool hit)
# ---------------------------------------------------------------------------

class TestEapAlarmSpoolCacheHit:
    """AC-2: Second POST with same coarse params → 200 spool-hit response."""

    def test_spool_cache_hit_returns_200(self, monkeypatch):
        """When spool exists, POST /spool returns 200 (not 202)."""
        monkeypatch.setattr(
            "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
            lambda key: "/tmp/fake_spool.parquet",  # simulate spool hit
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/eap-alarm/spool",
                json={
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-07",
                    "eqp_types": ["GDBA"],
                },
                content_type="application/json",
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["async"] is False
        assert "query_id" in data["data"]


# ---------------------------------------------------------------------------
# test_spool_miss_returns_410
# ---------------------------------------------------------------------------

def test_spool_miss_returns_410(monkeypatch):
    """GET /filter-options with unknown query_id → 410 CACHE_EXPIRED."""
    monkeypatch.setattr(
        "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
        lambda key: None,
    )

    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/api/eap-alarm/filter-options?query_id=nonexistent_key_xyz")

    assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert data["success"] is False


# ---------------------------------------------------------------------------
# test_detail_no_extra_oracle_query — EA-04
# ---------------------------------------------------------------------------

def test_detail_no_extra_oracle_query(tmp_path, monkeypatch):
    """GET /detail reads DETAIL_PARAMS from spool only; no Oracle call (EA-04)."""
    # Create a minimal synthetic parquet spool
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datetime import datetime

    table = pa.table({
        "EVENT_ID": pa.array(["ROW001"], type=pa.string()),
        "EQP_ID": pa.array(["GDBA-001"], type=pa.string()),
        "EQP_TYPE": pa.array(["GDBA"], type=pa.string()),
        "LOT_ID": pa.array(["LOT001"], type=pa.string()),
        "ALARM_TEXT": pa.array(["Test Alarm"], type=pa.string()),
        "ALARM_CATEGORY_CODE": pa.array([1.0], type=pa.float64()),
        "ALARM_CATEGORY": pa.array(["設備"], type=pa.string()),
        "ALARM_TIME": pa.array([datetime(2025, 1, 3, 10, 0, 0)], type=pa.timestamp("us")),
        "DETAIL_PARAMS": pa.array(['{"extra_param": "value1"}'], type=pa.string()),
        "eqp_types_filter": pa.array(["abc12345"], type=pa.string()),
    })
    spool_file = tmp_path / "test_spool.parquet"
    pq.write_table(table, str(spool_file))

    monkeypatch.setattr(
        "mes_dashboard.routes.eap_alarm_routes._get_spool_path",
        lambda key: str(spool_file),
    )

    oracle_call_count = [0]

    def mock_oracle(*args, **kwargs):
        oracle_call_count[0] += 1
        return pd.DataFrame()

    monkeypatch.setattr("mes_dashboard.core.database.read_sql_df_slow", mock_oracle)
    monkeypatch.setattr("mes_dashboard.core.database.read_sql_df", mock_oracle)

    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/api/eap-alarm/detail?query_id=test_spool_key&page=1&per_page=50")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]["rows"]) == 1
    assert data["data"]["rows"][0]["detail_params"] == {"extra_param": "value1"}

    assert oracle_call_count[0] == 0, (
        f"GET /detail must not trigger any Oracle query (EA-04); "
        f"got {oracle_call_count[0]} calls"
    )
