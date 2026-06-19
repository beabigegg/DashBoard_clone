# -*- coding: utf-8 -*-
"""Unit tests for EapAlarmJob (IP-5) — eap-alarm-unified-job-poc."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


class TestEapAlarmJobPreQuery:
    """AC-2: pre_query emits daily chunk pairs."""

    def test_pre_query_emits_daily_pairs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
        job = EapAlarmJob("test-job-123", params={
            "date_from": "2025-01-01",
            "date_to": "2025-01-03",
            "machines": ["EQP001", "EQP002"],
        })
        # mock spool key functions
        with patch("mes_dashboard.services.eap_alarm_cache.make_eap_alarm_spool_key", return_value="key123"), \
             patch("mes_dashboard.services.eap_alarm_cache.get_eap_alarm_spool_path", return_value=str(tmp_path / "spool.parquet")):
            job.pre_query()

        # 3 days × 2 chunks (events + detail) = 6
        assert len(job._chunks) == 6
        kinds = [c["kind"] for c in job._chunks]
        assert kinds == ["events", "detail", "events", "detail", "events", "detail"]

    def test_pre_query_single_day(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
        job = EapAlarmJob("test-job-456", params={
            "date_from": "2025-05-01",
            "date_to": "2025-05-01",
            "machines": ["EQP001"],
        })
        with patch("mes_dashboard.services.eap_alarm_cache.make_eap_alarm_spool_key", return_value="k"), \
             patch("mes_dashboard.services.eap_alarm_cache.get_eap_alarm_spool_path", return_value=str(tmp_path / "s.parquet")):
            job.pre_query()
        assert len(job._chunks) == 2
        assert job._chunks[0]["kind"] == "events"
        assert job._chunks[1]["kind"] == "detail"


class TestEapAlarmJobBuildChunkSql:
    """AC-3: build_chunk_sql returns correct SQL per kind."""

    def _make_job(self, tmp_path):
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
        job = EapAlarmJob("jid", params={
            "date_from": "2025-01-01", "date_to": "2025-01-01", "machines": ["E001"],
        })
        job._equipment_filter = "e.EQUIPMENT_ID IN (:r0)"
        job._eqp_params = {"r0": "E001"}
        return job

    def test_events_sql(self, tmp_path):
        job = self._make_job(tmp_path)
        sql, params = job.build_chunk_sql({
            "kind": "events",
            "base_params": {"date_from": "2025-01-01", "date_to": "2025-01-02", "r0": "E001"},
        })
        assert "EAP_EVENT" in sql
        assert "EAP_EVENT_DETAIL" not in sql
        assert "date_from" in params

    def test_detail_sql(self, tmp_path):
        job = self._make_job(tmp_path)
        sql, params = job.build_chunk_sql({
            "kind": "detail",
            "base_params": {"date_from": "2025-01-01", "date_to": "2025-01-02", "r0": "E001"},
        })
        assert "EAP_EVENT_DETAIL" in sql
        assert "date_from" in params


class TestEapAlarmJobPostAggregate:
    """AC-1 / AC-5: post_aggregate reads chunk parquets, runs pairing, writes spool."""

    def _make_events_table(self):
        return pa.table({
            "EVENT_ID": ["E1", "E2"],
            "EQP_ID": ["EQP001", "EQP001"],
            "EQP_TYPE": ["EQP0", "EQP0"],
            "LOT_ID": ["L1", "L1"],
            "ALARM_ID": ["A1", "A1"],
            "ALARM_TIME": ["2025-01-01 10:00:00", "2025-01-01 10:01:00"],
        })

    def _make_detail_table(self):
        return pa.table({
            "EVENT_ID": ["E1", "E1", "E2"],
            "PARAMETER_NAME": ["AlarmCode", "AlarmText", "AlarmCode"],
            "PARAMETER_VALUE": ["-10", "高溫警報", "5"],
        })

    def test_post_aggregate_pairs_set_clear(self, tmp_path, monkeypatch):
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))

        spool_path = str(tmp_path / "out.parquet")
        job = EapAlarmJob("test-post-001", params={
            "date_from": "2025-01-01", "date_to": "2025-01-01",
            "machines": ["EQP001"],
        })
        # Set up state that pre_query would set
        job._chunks = [
            {"kind": "events", "date_from": "2025-01-01", "date_to": "2025-01-02", "base_params": {}},
            {"kind": "detail", "date_from": "2025-01-01", "date_to": "2025-01-02", "base_params": {}},
        ]
        job._spool_key = "testkey"
        job._spool_path = spool_path
        job._machines_hash = "abcd1234"

        # Write chunk parquets manually
        chunk_dir = job._make_chunk_parquet_dir("test-post-001")
        pq.write_table(self._make_events_table(), chunk_dir / "chunk-0000-0000.parquet")
        pq.write_table(self._make_detail_table(), chunk_dir / "chunk-0001-0000.parquet")

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"), \
             patch("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_TTL", 3600):
            result = job.post_aggregate(None)

        assert Path(result).exists()
        import duckdb
        rows = duckdb.execute(f"SELECT * FROM read_parquet('{result}')").fetchall()
        # E1 is SET (AlarmCode=-10), E2 is CLEAR (AlarmCode=5) → should pair
        assert len(rows) >= 1

    def test_post_aggregate_empty_events(self, tmp_path, monkeypatch):
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))

        spool_path = str(tmp_path / "empty.parquet")
        job = EapAlarmJob("test-empty-001", params={
            "date_from": "2025-01-01", "date_to": "2025-01-01",
            "machines": ["EQP001"],
        })
        job._chunks = [
            {"kind": "events", "base_params": {}},
            {"kind": "detail", "base_params": {}},
        ]
        job._spool_key = "emptykey"
        job._spool_path = spool_path
        job._machines_hash = "00000000"

        # Create chunk dir but write empty parquets
        chunk_dir = job._make_chunk_parquet_dir("test-empty-001")
        empty_events = pa.table({
            "EVENT_ID": pa.array([], type=pa.string()),
            "EQP_ID": pa.array([], type=pa.string()),
            "EQP_TYPE": pa.array([], type=pa.string()),
            "LOT_ID": pa.array([], type=pa.string()),
            "ALARM_ID": pa.array([], type=pa.string()),
            "ALARM_TIME": pa.array([], type=pa.string()),
        })
        pq.write_table(empty_events, chunk_dir / "chunk-0000-0000.parquet")

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"), \
             patch("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_TTL", 3600):
            result = job.post_aggregate(None)

        assert Path(result).exists()


class TestEapAlarmRouteFlag:
    """AC-6 (flag-OFF zero regression) / AC-7 (env var gating) tests."""

    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("EAP_ALARM_USE_UNIFIED_JOB", raising=False)
        import importlib
        import mes_dashboard.routes.eap_alarm_routes as rt
        importlib.reload(rt)
        assert rt._EAP_ALARM_USE_UNIFIED_JOB is False

    def test_flag_on_via_env(self, monkeypatch):
        monkeypatch.setenv("EAP_ALARM_USE_UNIFIED_JOB", "on")
        import importlib
        import mes_dashboard.routes.eap_alarm_routes as rt
        importlib.reload(rt)
        assert rt._EAP_ALARM_USE_UNIFIED_JOB is True

    def test_flag_true_string(self, monkeypatch):
        monkeypatch.setenv("EAP_ALARM_USE_UNIFIED_JOB", "true")
        import importlib
        import mes_dashboard.routes.eap_alarm_routes as rt
        importlib.reload(rt)
        assert rt._EAP_ALARM_USE_UNIFIED_JOB is True


class TestEapAlarmJobProgressReport:
    """AC-5: progress_report calls update_job_progress with correct prefix."""

    def test_progress_report_uses_eap_alarm_prefix(self, monkeypatch):
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
        calls = []
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda prefix, job_id, **kw: calls.append((prefix, job_id, kw)),
        )
        job = EapAlarmJob("test-pct-001", params={"date_from": "2025-01-01", "date_to": "2025-01-01", "machines": []})
        job.progress_report(15)
        assert calls[0][0] == "eap-alarm"
        assert calls[0][2].get("pct") == "15"
