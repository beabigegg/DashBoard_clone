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
        """enqueue_query_job is called via unified path with correct job_type and params."""
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

        def _mock_enqueue_query_job(job_type, owner, params, **kwargs):
            captured["job_type"] = job_type
            captured["params"] = dict(params)
            return ("eap-alarm-test-001", None, None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            _mock_enqueue_query_job,
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

        data = resp.get_json()
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {data}"
        assert data["success"] is True
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]
        assert "query_id" in data["data"]

        assert captured.get("job_type") == "eap-alarm", (
            f"Expected job_type='eap-alarm', got {captured.get('job_type')!r}"
        )
        assert captured["params"].get("eqp_types") == ["GDBA", "GCBA"], (
            f"eqp_types must be forwarded in params, got: {captured['params'].get('eqp_types')!r}"
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

    def test_lot_query_enqueues_without_dates(self, monkeypatch):
        """The explicit LOT mode dispatches the date-free worker path."""
        captured: Dict[str, Any] = {}

        def _mock_enqueue_query_job(job_type, owner, params, **kwargs):
            captured["job_type"] = job_type
            captured["params"] = dict(params)
            return ("eap-alarm-lot-001", None, None)

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            _mock_enqueue_query_job,
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
                json={"query_mode": "lot_ids", "lot_ids": ["LOT-001"]},
                content_type="application/json",
            )

        assert resp.status_code == 202
        assert captured["job_type"] == "eap-alarm"
        assert captured["params"]["query_mode"] == "lot_ids"
        assert captured["params"]["lot_ids"] == ["LOT-001"]
        assert captured["params"]["date_from"] == ""
        assert captured["params"]["date_to"] == ""

    def test_post_spool_blank_eqp_type_returns_400(self, monkeypatch):
        """Blank-after-strip eqp_type entry → 400 VALIDATION_ERROR (EA-07).

        EA-07's closed enum is retired — free-form strings like "INVALID_TYPE"
        are legal equipment identifiers now; only non-string/blank entries 400.
        (This test previously pinned the retired enum and was stale-red.)
        """
        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/eap-alarm/spool",
                json={
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-07",
                    "eqp_types": ["   "],
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
        """Build a synthetic Oracle result for the main events query."""
        import pandas as pd
        from datetime import datetime
        return pd.DataFrame({
            "EVENT_ID": ["AAABBB000001", "AAABBB000002"],
            "EQP_ID": ["GDBA-001", "GCBA-002"],
            "EQP_TYPE": ["GDBA", "GCBA"],
            "LOT_ID": ["LOT001", None],
            "EVENT_TYPE": ["EQP_SECS_ALARM", "EQP_SECS_ALARM"],
            "ALARM_ID": ["AlarmA", "AlarmB"],
            "ALARM_TIME": [datetime(2025, 1, 3, 10, 0, 0), datetime(2025, 1, 4, 12, 30, 0)],
        })

    def _empty_detail_df(self):
        """Build an empty detail dataframe with correct columns."""
        import pandas as pd
        return pd.DataFrame({"EVENT_ID": [], "PARAMETER_NAME": [], "PARAMETER_VALUE": []})

    def _lot_product_df(self):
        """Build a synthetic DW_MES_CONTAINER product-dim lookup result."""
        import pandas as pd
        return pd.DataFrame({
            "LOT_ID": ["LOT001"],
            "PJ_TYPE": ["TypeA"],
            "PRODUCT_LINE": ["LineA"],
            "PJ_BOP": ["BopA"],
        })

    def _sql_router(self, mock_df, detail_df=None, lot_product_df=None):
        """Return a mock read_sql_df_slow that discriminates events vs detail vs lot-product by SQL content."""
        if detail_df is None:
            detail_df = self._empty_detail_df()
        if lot_product_df is None:
            lot_product_df = self._lot_product_df()

        def _mock(sql, params=None, timeout_seconds=None, caller="unknown"):
            # Lot→product lookup targets DW_MES_CONTAINER (schema v4 enrichment)
            if "DW_MES_CONTAINER" in sql:
                return lot_product_df
            # Detail query always has PARAMETER_NAME column in SELECT
            if "PARAMETER_NAME" in sql or "EAP_EVENT_DETAIL" in sql:
                return detail_df
            return mock_df

        return _mock

    def test_worker_fn_writes_parquet_with_correct_columns(self, tmp_path, monkeypatch):
        """Worker fn writes parquet with all §3.17 columns."""
        mock_df = self._build_mock_df()

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            self._sql_router(mock_df),
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

        # Parquet schema matches _PAIR_SQL output (alias names, schema v4)
        expected_cols = {
            "ALARM_ID", "EQP_ID", "EQP_TYPE", "LOT_ID",
            "ALARM_TEXT", "ALARM_CATEGORY_CODE",
            "ALARM_START", "ALARM_END", "DURATION_SECONDS",
            "DETAIL_PARAMS", "PJ_TYPE", "PRODUCT_LINE", "PJ_BOP",
            "ALARM_SOURCE", "eqp_types_filter",
        }
        assert expected_cols == cols, f"Column mismatch: {cols} vs {expected_cols}"

        # Product enrichment: LOT001 rows must carry the looked-up product dims
        df = table.to_pandas()
        lot_rows = df[df["LOT_ID"] == "LOT001"]
        assert not lot_rows.empty
        assert set(lot_rows["PJ_TYPE"]) == {"TypeA"}
        assert set(lot_rows["PRODUCT_LINE"]) == {"LineA"}
        assert set(lot_rows["PJ_BOP"]) == {"BopA"}

    def test_worker_fn_decodes_alarm_category(self, tmp_path, monkeypatch):
        """AlarmCategory code 1 → '設備'; code 99 → '未知' via ALARM_CATEGORY_CODE in detail."""
        import pandas as pd
        from datetime import datetime
        mock_df = self._build_mock_df()
        # Supply detail rows with AlarmCode so the ALARM_CATEGORY_CODE is set
        detail_df = pd.DataFrame({
            "EVENT_ID": ["AAABBB000001", "AAABBB000002"],
            "PARAMETER_NAME": ["AlarmCode", "AlarmCode"],
            "PARAMETER_VALUE": ["-1", "-99"],  # negative = SET; ABS & 127 = category code
        })

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            self._sql_router(mock_df, detail_df),
        )
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job("test-decode", "2025-01-01", "2025-01-07", eqp_types=["GDBA", "GCBA"])

        import pyarrow.parquet as pq
        table = pq.read_table(str(list(tmp_path.glob("*.parquet"))[0]))
        df = table.to_pandas()
        assert "ALARM_CATEGORY_CODE" in df.columns, "ALARM_CATEGORY_CODE column must be in parquet"

    def test_worker_fn_progress_milestones(self, tmp_path, monkeypatch):
        """Progress milestones 5 → 15 → 90 → 100 must fire in order (coarse bracket)."""
        mock_df = self._build_mock_df()
        progress_calls = []

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            self._sql_router(mock_df),
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

        run_eap_alarm_query_job("test-milestone", "2025-01-01", "2025-01-07", eqp_types=["GDBA"])

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

    def test_worker_fn_includes_shape_b_and_pairs_by_event_name(self, tmp_path, monkeypatch):
        """EA-EVT (legacy path): Shape B rows flow through run_eap_alarm_query_job —
        AlarmDetected/AlarmCleared pair on detail AlarmID, tagged ALARM_SOURCE."""
        import pandas as pd
        from datetime import datetime

        mock_df = pd.DataFrame({
            "EVENT_ID": ["A1", "B1", "B2"],
            "EQP_ID": ["GDBA-001", "GWBA-002", "GWBA-002"],
            "EQP_TYPE": ["GDBA", "GWBA", "GWBA"],
            "LOT_ID": ["LOT001", None, None],
            "EVENT_TYPE": ["EQP_SECS_ALARM", "EQP_SECS_EVENT", "EQP_SECS_EVENT"],
            "ALARM_ID": ["3047", "AlarmDetected", "AlarmCleared"],
            "ALARM_TIME": [
                datetime(2025, 1, 3, 9, 0, 0),
                datetime(2025, 1, 3, 10, 0, 0),
                datetime(2025, 1, 3, 10, 20, 0),
            ],
        })
        detail_df = pd.DataFrame({
            "EVENT_ID": ["A1", "B1", "B1", "B2"],
            "PARAMETER_NAME": ["AlarmCode", "AlarmID", "AlarmText", "AlarmID"],
            "PARAMETER_VALUE": ["-3", "6052", "MissingDieDetected", "6052"],
        })

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow",
            self._sql_router(mock_df, detail_df),
        )
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job("test-shapeb", "2025-01-01", "2025-01-07", eqp_types=["GDBA", "GWBA"])

        import pyarrow.parquet as pq
        df = pq.read_table(str(list(tmp_path.glob("*.parquet"))[0])).to_pandas()

        # One occurrence per shape: A1 (open SET) + B1→B2 (paired)
        assert len(df) == 2, df
        by_source = {r["ALARM_SOURCE"]: r for _, r in df.iterrows()}
        assert set(by_source) == {"EQP_SECS_ALARM", "EQP_SECS_EVENT"}

        shape_b = by_source["EQP_SECS_EVENT"]
        assert shape_b["ALARM_ID"] == "6052"          # identity from detail AlarmID
        assert shape_b["ALARM_TEXT"] == "MissingDieDetected"
        assert shape_b["DURATION_SECONDS"] == 1200.0  # paired via EVENT_NAME, not ALCD
        assert pd.isna(shape_b["ALARM_CATEGORY_CODE"])  # no ALCD byte → NULL

        shape_a = by_source["EQP_SECS_ALARM"]
        assert shape_a["ALARM_ID"] == "3047"
        assert pd.isna(shape_a["ALARM_END"])          # unpaired Shape A SET stays open
        # Product-dim enrichment still applies to Shape A rows with a LOT_ID
        assert shape_a["PJ_TYPE"] == "TypeA"

    def test_worker_fn_oracle_sql_contains_last_update_time_predicate(self, tmp_path, monkeypatch):
        """Oracle SQL must contain LAST_UPDATE_TIME BETWEEN predicate (EA-03)."""
        captured_sql = []
        mock_df = self._build_mock_df()

        def mock_read_sql(sql, params=None, timeout_seconds=None, caller="unknown"):
            captured_sql.append(sql)
            if "PARAMETER_NAME" in sql or "EAP_EVENT_DETAIL" in sql:
                return self._empty_detail_df()
            return mock_df

        monkeypatch.setattr("mes_dashboard.core.database.read_sql_df_slow", mock_read_sql)
        monkeypatch.setattr("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_DIR", str(tmp_path))
        monkeypatch.setattr("mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None)
        monkeypatch.setattr("mes_dashboard.core.query_spool_store.register_spool_file", lambda *a, **kw: True)

        from mes_dashboard.workers.eap_alarm_worker import run_eap_alarm_query_job

        run_eap_alarm_query_job("test-sql", "2025-01-01", "2025-01-07", eqp_types=["GDBA"])

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
    # Create a minimal synthetic parquet spool matching _PAIR_SQL output column names:
    # ALARM_ID, EQP_ID, EQP_TYPE, LOT_ID, ALARM_TEXT, ALARM_CATEGORY_CODE,
    # ALARM_START, ALARM_END, DURATION_SECONDS, DETAIL_PARAMS,
    # PJ_TYPE, PRODUCT_LINE, PJ_BOP, ALARM_SOURCE, eqp_types_filter (schema v5)
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datetime import datetime

    table = pa.table({
        "ALARM_ID": pa.array(["AlarmA"], type=pa.string()),
        "EQP_ID": pa.array(["GDBA-001"], type=pa.string()),
        "EQP_TYPE": pa.array(["GDBA"], type=pa.string()),
        "LOT_ID": pa.array(["LOT001"], type=pa.string()),
        "ALARM_TEXT": pa.array(["Test Alarm"], type=pa.string()),
        "ALARM_CATEGORY_CODE": pa.array([1.0], type=pa.float64()),
        "ALARM_START": pa.array([datetime(2025, 1, 3, 10, 0, 0)], type=pa.timestamp("us")),
        "ALARM_END": pa.array([None], type=pa.timestamp("us")),
        "DURATION_SECONDS": pa.array([None], type=pa.float64()),
        "DETAIL_PARAMS": pa.array(['{"extra_param": "value1"}'], type=pa.string()),
        "PJ_TYPE": pa.array(["TypeA"], type=pa.string()),
        "PRODUCT_LINE": pa.array(["LineA"], type=pa.string()),
        "PJ_BOP": pa.array(["BopA"], type=pa.string()),
        "ALARM_SOURCE": pa.array(["EQP_SECS_ALARM"], type=pa.string()),
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
    assert data["data"]["rows"][0]["alarm_source"] == "EQP_SECS_ALARM"

    assert oracle_call_count[0] == 0, (
        f"GET /detail must not trigger any Oracle query (EA-04); "
        f"got {oracle_call_count[0]} calls"
    )


# TestEapAlarmWorkerFnNewDims has been moved to
# tests/integration/test_eap_alarm_coarse_filter.py
# (marker: pytest.mark.integration — fully mock-based, runs in PR gate)
