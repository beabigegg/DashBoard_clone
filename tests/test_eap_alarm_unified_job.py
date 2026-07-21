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

    def test_explicit_lot_query_uses_one_unbounded_chunk_pair(self, tmp_path, monkeypatch):
        """A specified LOT query must not manufacture a date range."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob

        job = EapAlarmJob("test-lot-001", params={
            "query_mode": "lot_ids",
            "lot_ids": ["LOT-001"],
        })
        with patch("mes_dashboard.services.eap_alarm_cache.make_eap_alarm_spool_key", return_value="lot-key"), \
             patch("mes_dashboard.services.eap_alarm_cache.get_eap_alarm_spool_path", return_value=str(tmp_path / "lot.parquet")):
            job.pre_query()

        assert [chunk["kind"] for chunk in job._chunks] == ["events", "detail"]
        assert "date_from" not in job._chunks[0]["base_params"]

        sql, params = job.build_chunk_sql(job._chunks[0])
        assert "LAST_UPDATE_TIME BETWEEN" not in sql
        assert "LOT_ID IN" in sql
        assert params["lot_0"] == "LOT-001"

    def test_work_orders_produces_exists_clause_in_chunk_sql(self, tmp_path, monkeypatch):
        """EA-11: work_orders flows through pre_query → build_chunk_sql as an
        EXISTS clause on MFGORDERNAME (mirrors the lot_ids IN-clause coverage above)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob

        job = EapAlarmJob("test-wo-001", params={
            "date_from": "2025-01-01",
            "date_to": "2025-01-01",
            "eqp_types": ["EQP001"],
            "work_orders": ["WO-001"],
        })
        with patch("mes_dashboard.services.eap_alarm_cache.make_eap_alarm_spool_key", return_value="wo-key"), \
             patch("mes_dashboard.services.eap_alarm_cache.get_eap_alarm_spool_path", return_value=str(tmp_path / "wo.parquet")):
            job.pre_query()

        sql, params = job.build_chunk_sql(job._chunks[0])
        assert "EXISTS" in sql
        assert "MFGORDERNAME" in sql
        assert params["wo_0"] == "WO-001"


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
            "EVENT_TYPE": ["EQP_SECS_ALARM", "EQP_SECS_ALARM"],
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
            "EVENT_TYPE": pa.array([], type=pa.string()),
            "ALARM_ID": pa.array([], type=pa.string()),
            "ALARM_TIME": pa.array([], type=pa.string()),
        })
        pq.write_table(empty_events, chunk_dir / "chunk-0000-0000.parquet")

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"), \
             patch("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_TTL", 3600):
            result = job.post_aggregate(None)

        assert Path(result).exists()


def _run_shapeb_post_aggregate(tmp_path, monkeypatch, events_by_chunk, detail_rows):
    """Write per-chunk events parquets + one detail parquet, run post_aggregate.

    Shared by TestEapAlarmShapeBPairing / TestEapAlarmCrossChannelDedup —
    runs the real _PAIR_SQL (pairing + EA-EVT dedup) in DuckDB.
    """
    from mes_dashboard.workers.eap_alarm_worker import EapAlarmJob
    monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))

    job = EapAlarmJob("test-shapeb-001", params={
        "date_from": "2025-01-01", "date_to": "2025-01-02",
    })
    chunks = []
    for i in range(len(events_by_chunk)):
        chunks.append({"kind": "events", "base_params": {}})
    chunks.append({"kind": "detail", "base_params": {}})
    job._chunks = chunks
    job._spool_key = "shapebkey"
    job._spool_path = str(tmp_path / "shapeb.parquet")
    job._machines_hash = "beefcafe"

    chunk_dir = job._make_chunk_parquet_dir("test-shapeb-001")
    for i, tbl in enumerate(events_by_chunk):
        pq.write_table(tbl, chunk_dir / f"chunk-{i:04d}-0000.parquet")
    detail_tbl = pa.table({
        "EVENT_ID": [r[0] for r in detail_rows],
        "PARAMETER_NAME": [r[1] for r in detail_rows],
        "PARAMETER_VALUE": [r[2] for r in detail_rows],
    })
    pq.write_table(detail_tbl, chunk_dir / f"chunk-{len(events_by_chunk):04d}-0000.parquet")

    with patch("mes_dashboard.core.query_spool_store.register_spool_file"), \
         patch("mes_dashboard.services.eap_alarm_cache.EAP_ALARM_SPOOL_TTL", 3600):
        result = job.post_aggregate(None)

    import duckdb
    return duckdb.execute(
        f"SELECT * FROM read_parquet('{result}') ORDER BY ALARM_START"
    ).fetchdf()


def _shapeb_events_table(rows):
    """rows: (EVENT_ID, EQP_ID, EVENT_TYPE, ALARM_ID/EVENT_NAME, ALARM_TIME)."""
    return pa.table({
        "EVENT_ID": [r[0] for r in rows],
        "EQP_ID": [r[1] for r in rows],
        "EQP_TYPE": [r[1][:4] for r in rows],
        "LOT_ID": [None for _ in rows],
        "EVENT_TYPE": [r[2] for r in rows],
        "ALARM_ID": [r[3] for r in rows],
        "ALARM_TIME": [r[4] for r in rows],
    })


class TestEapAlarmShapeBPairing:
    """EA-EVT: Shape B (EQP_SECS_EVENT alarm-alias) pairing via post_aggregate.

    Runs the real _PAIR_SQL in DuckDB. Detected/Cleared chunks are written to
    DIFFERENT daily chunks so cross-seam pairing (ADR-0009) is exercised for
    Shape B too.
    """

    def _run_post_aggregate(self, tmp_path, monkeypatch, events_by_chunk, detail_rows):
        return _run_shapeb_post_aggregate(tmp_path, monkeypatch, events_by_chunk, detail_rows)

    def _events_table(self, rows):
        return _shapeb_events_table(rows)

    def test_shape_b_pairs_detected_cleared_by_alarm_id_across_chunks(self, tmp_path, monkeypatch):
        """AlarmDetected (day 1 chunk) pairs with AlarmCleared (day 2 chunk) on AlarmID."""
        day1 = self._events_table([
            ("B1", "GWBA-002", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 23:50:00"),
        ])
        day2 = self._events_table([
            ("B2", "GWBA-002", "EQP_SECS_EVENT", "AlarmCleared", "2025-01-02 00:10:00"),
        ])
        detail = [
            ("B1", "AlarmID", "6052"),
            ("B1", "AlarmText", "MissingDieDetected"),
            ("B2", "AlarmID", "6052"),
        ]
        df = self._run_post_aggregate(tmp_path, monkeypatch, [day1, day2], detail)

        assert len(df) == 1, df
        row = df.iloc[0]
        assert row["ALARM_ID"] == "6052"
        assert row["ALARM_SOURCE"] == "EQP_SECS_EVENT"
        assert row["ALARM_TEXT"] == "MissingDieDetected"
        assert pd.notna(row["ALARM_END"])
        assert row["DURATION_SECONDS"] == 1200.0
        # No ALCD byte on Shape B → category NULL (decodes "未知" per EA-05)
        assert pd.isna(row["ALARM_CATEGORY_CODE"])

    def test_shape_b_unpaired_detected_stays_open(self, tmp_path, monkeypatch):
        """AlarmDetected with no matching AlarmCleared → ALARM_END NULL."""
        day1 = self._events_table([
            ("B1", "GWBA-002", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:00"),
        ])
        detail = [("B1", "AlarmID", "99")]
        df = self._run_post_aggregate(tmp_path, monkeypatch, [day1], detail)

        assert len(df) == 1
        assert pd.isna(df.iloc[0]["ALARM_END"])
        # No AlarmText detail → falls back to AlarmID as display text
        assert df.iloc[0]["ALARM_TEXT"] == "99"

    def test_cross_shape_pairing_forbidden(self, tmp_path, monkeypatch):
        """A Shape A CLEAR must never close a Shape B SET with the same identity value."""
        day1 = self._events_table([
            # Shape B SET, identity AlarmID=6052
            ("S1", "GDBA-009", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:00"),
            # Shape A CLEAR, identity EVENT_NAME=6052 (AlarmCode >= 0)
            ("C1", "GDBA-009", "EQP_SECS_ALARM", "6052", "2025-01-01 10:05:00"),
        ])
        detail = [
            ("S1", "AlarmID", "6052"),
            ("C1", "AlarmCode", "1"),
        ]
        df = self._run_post_aggregate(tmp_path, monkeypatch, [day1], detail)

        # Only the Shape B occurrence survives (Shape A CLEAR without a SET is
        # dropped) and it must stay OPEN — the Shape A CLEAR may not close it.
        assert len(df) == 1, df
        row = df.iloc[0]
        assert row["ALARM_SOURCE"] == "EQP_SECS_EVENT"
        assert pd.isna(row["ALARM_END"])

    def test_both_shapes_coexist_with_alarm_source(self, tmp_path, monkeypatch):
        """Mixed-shape fixture → one occurrence per shape, tagged by ALARM_SOURCE."""
        day1 = self._events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "3047", "2025-01-01 09:00:00"),
            ("A2", "GDBA-001", "EQP_SECS_ALARM", "3047", "2025-01-01 09:30:00"),
            ("B1", "GCBA-005", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:00"),
            ("B2", "GCBA-005", "EQP_SECS_EVENT", "AlarmCleared", "2025-01-01 10:20:00"),
        ])
        detail = [
            ("A1", "AlarmCode", "-3"),
            ("A2", "AlarmCode", "3"),
            ("B1", "AlarmID", "77"),
            ("B2", "AlarmID", "77"),
        ]
        df = self._run_post_aggregate(tmp_path, monkeypatch, [day1], detail)

        assert len(df) == 2, df
        by_source = {r["ALARM_SOURCE"]: r for _, r in df.iterrows()}
        assert set(by_source) == {"EQP_SECS_ALARM", "EQP_SECS_EVENT"}
        assert by_source["EQP_SECS_ALARM"]["ALARM_ID"] == "3047"
        assert by_source["EQP_SECS_ALARM"]["DURATION_SECONDS"] == 1800.0
        assert by_source["EQP_SECS_ALARM"]["ALARM_CATEGORY_CODE"] == 3  # ABS(-3) & 127
        assert by_source["EQP_SECS_EVENT"]["ALARM_ID"] == "77"
        assert by_source["EQP_SECS_EVENT"]["DURATION_SECONDS"] == 1200.0


class TestEapAlarmCrossChannelDedup:
    """EA-EVT cross-channel dedup: Shape B occurrence dropped when a Shape A
    occurrence matches on (EQP_ID, ALARM_ID) within ±60s; Shape A wins.

    Rule shipped after production measurement (GDBA, 2-day window, 2026-07-07):
    70.43% of Shape B AlarmDetected had a Shape A counterpart within ±60s.
    """

    def _dual_channel_detail(self):
        return [
            ("A1", "AlarmCode", "-4"),
            ("A2", "AlarmCode", "4"),
            ("B1", "AlarmID", "6052"),
            ("B2", "AlarmID", "6052"),
        ]

    def test_duplicate_within_tolerance_dropped_shape_a_wins(self, tmp_path, monkeypatch):
        """Same (EQP_ID, ALARM_ID), B 30s after A → only the Shape A occurrence survives."""
        events = _shapeb_events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 10:00:00"),
            ("A2", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 10:05:00"),
            ("B1", "GDBA-001", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:30"),
            ("B2", "GDBA-001", "EQP_SECS_EVENT", "AlarmCleared", "2025-01-01 10:05:30"),
        ])
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], self._dual_channel_detail())

        assert len(df) == 1, df
        assert df.iloc[0]["ALARM_SOURCE"] == "EQP_SECS_ALARM"
        assert df.iloc[0]["DURATION_SECONDS"] == 300.0  # A's own pair, not B's

    def test_same_id_outside_tolerance_both_kept(self, tmp_path, monkeypatch):
        """B 61s after A → outside ±60s window → both occurrences kept."""
        events = _shapeb_events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 10:00:00"),
            ("B1", "GDBA-001", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:01:01"),
        ])
        detail = [("A1", "AlarmCode", "-4"), ("B1", "AlarmID", "6052")]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], detail)

        assert len(df) == 2, df
        assert set(df["ALARM_SOURCE"]) == {"EQP_SECS_ALARM", "EQP_SECS_EVENT"}

    def test_unmatched_alarm_id_on_dual_channel_kept(self, tmp_path, monkeypatch):
        """Dual-channel equipment, B carries a different AlarmID → kept (the ~30% share)."""
        events = _shapeb_events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 10:00:00"),
            ("B1", "GDBA-001", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:10"),
        ])
        detail = [("A1", "AlarmCode", "-4"), ("B1", "AlarmID", "9999")]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], detail)

        assert len(df) == 2, df

    def test_same_id_different_equipment_not_deduped(self, tmp_path, monkeypatch):
        """Same AlarmID and window but on another machine → not a duplicate."""
        events = _shapeb_events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 10:00:00"),
            ("B1", "GDBA-002", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:10"),
        ])
        detail = [("A1", "AlarmCode", "-4"), ("B1", "AlarmID", "6052")]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], detail)

        assert len(df) == 2, df

    def test_unpaired_shape_a_still_wins(self, tmp_path, monkeypatch):
        """A open (no CLEAR) + duplicated B pair → deterministic A-wins: the
        surviving row is the OPEN Shape A occurrence (B's duration is discarded)."""
        events = _shapeb_events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 10:00:00"),
            ("B1", "GDBA-001", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-01 10:00:05"),
            ("B2", "GDBA-001", "EQP_SECS_EVENT", "AlarmCleared", "2025-01-01 10:03:00"),
        ])
        detail = [
            ("A1", "AlarmCode", "-4"),
            ("B1", "AlarmID", "6052"),
            ("B2", "AlarmID", "6052"),
        ]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], detail)

        assert len(df) == 1, df
        assert df.iloc[0]["ALARM_SOURCE"] == "EQP_SECS_ALARM"
        assert pd.isna(df.iloc[0]["ALARM_END"])

    def test_dedup_applies_across_chunk_seam(self, tmp_path, monkeypatch):
        """A occurrence in day-1 chunk dedups a B occurrence at the day-2 seam
        edge — dedup runs in post_aggregate over ALL chunks (ADR-0009/ADR-0015)."""
        day1 = _shapeb_events_table([
            ("A1", "GDBA-001", "EQP_SECS_ALARM", "6052", "2025-01-01 23:59:40"),
        ])
        day2 = _shapeb_events_table([
            ("B1", "GDBA-001", "EQP_SECS_EVENT", "AlarmDetected", "2025-01-02 00:00:10"),
        ])
        detail = [("A1", "AlarmCode", "-4"), ("B1", "AlarmID", "6052")]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [day1, day2], detail)

        assert len(df) == 1, df
        assert df.iloc[0]["ALARM_SOURCE"] == "EQP_SECS_ALARM"

    def test_dedup_tolerance_constant_pinned(self):
        """±60s is the production-measured window — changing it needs a new
        measurement (EA-EVT), so pin it."""
        from mes_dashboard.workers.eap_alarm_worker import _SHAPE_B_DEDUP_TOLERANCE_SECONDS
        assert _SHAPE_B_DEDUP_TOLERANCE_SECONDS == 60


class TestEapAlarmFlappingPairingArtifact:
    """Regression coverage for the heavy-flapping mis-pairing artifact found in
    the 2026-07-07 full-week production measurement (ADR-0015 follow-up):
    GDBA-0121 AlarmID 3340 fired 3+ SETs in one window with no intervening
    CLEAR, and every one of those SETs paired to the SAME distant CLEAR
    (e.g. two real SETs at 07:51:58 and 07:55:20 both closed at 09:43:12,
    ~1.75h and ~1.63h later respectively) because `_PAIR_SQL`'s pairing join

        LEFT JOIN clear_events c ON ... c.CLEAR_TIME > s.ALARM_TIME
        GROUP BY ... -- MIN(c.CLEAR_TIME) per SET

    resolves each SET's end time independently: it is NOT a one-to-one
    greedy match that consumes a CLEAR once assigned. When N SETs for the
    same (EQP_ID, ALARM_ID) occur back-to-back with no CLEAR between them,
    the next available CLEAR is shared by all N of them, producing N output
    rows that each claim (wrongly, for N-1 of them) to have run until that
    same far-future CLEAR. This is accepted current behavior (not fixed
    here — the SQL is unchanged); this test exists to pin it so a future
    change to the pairing rule is a deliberate, measured decision rather
    than a silent side effect.
    """

    def test_multiple_sets_share_one_distant_clear(self, tmp_path, monkeypatch):
        """3 SETs with no CLEAR in between all pair to the same later CLEAR,
        producing 3 rows (not 1) with 3 different, all-inflated durations."""
        events = _shapeb_events_table([
            ("A1", "GDBA-0121", "EQP_SECS_ALARM", "3340", "2025-01-01 07:51:58"),
            ("A2", "GDBA-0121", "EQP_SECS_ALARM", "3340", "2025-01-01 07:55:20"),
            ("A3", "GDBA-0121", "EQP_SECS_ALARM", "3340", "2025-01-01 09:34:41"),
            ("A4", "GDBA-0121", "EQP_SECS_ALARM", "3340", "2025-01-01 09:43:12"),
        ])
        detail = [
            ("A1", "AlarmCode", "-4"),
            ("A2", "AlarmCode", "-4"),
            ("A3", "AlarmCode", "-4"),
            ("A4", "AlarmCode", "4"),  # the only CLEAR in the window
        ]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], detail)

        # All 3 SETs survive as separate rows — the pairing SQL does not
        # merge/consume them, so this is 3 rows, not 1.
        assert len(df) == 3, df
        ends = set(df["ALARM_END"])
        assert len(ends) == 1, "all three SETs should share the one available CLEAR"
        durations = sorted(df["DURATION_SECONDS"])
        # Same CLEAR, different SET times -> different (and for two of the
        # three, wrong) durations. Values below are exact for this fixture;
        # a change here signals the pairing rule itself changed.
        assert durations == [511.0, 6472.0, 6674.0], durations

    def test_set_immediately_followed_by_its_own_clear_is_unaffected(self, tmp_path, monkeypatch):
        """Sanity check: a clean SET/CLEAR pair with no flapping neighbors
        still pairs correctly — the artifact above is specific to repeated
        SETs sharing one CLEAR, not a general pairing regression."""
        events = _shapeb_events_table([
            ("A1", "GDBA-0121", "EQP_SECS_ALARM", "3340", "2025-01-01 07:51:58"),
            ("A2", "GDBA-0121", "EQP_SECS_ALARM", "3340", "2025-01-01 07:52:08"),
        ])
        detail = [("A1", "AlarmCode", "-4"), ("A2", "AlarmCode", "4")]
        df = _run_shapeb_post_aggregate(tmp_path, monkeypatch, [events], detail)

        assert len(df) == 1, df
        assert df.iloc[0]["DURATION_SECONDS"] == 10.0


class TestAlarmEventSqlTemplates:
    """EA-EVT: Oracle templates include both shapes; non-alarm aliases stay excluded."""

    def test_both_templates_include_shape_b_aliases(self):
        from mes_dashboard.workers.eap_alarm_worker import (
            _EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE,
        )
        for sql in (_EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE):
            assert "EQP_SECS_ALARM" in sql
            assert "EQP_SECS_EVENT" in sql
            assert "'AlarmDetected'" in sql
            assert "'AlarmCleared'" in sql

    def test_non_alarm_aliases_excluded(self):
        """ProcessAlarm / MTBA-MTBF are NOT alarm occurrences (EA-EVT exclusion)."""
        from mes_dashboard.workers.eap_alarm_worker import (
            _EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE,
        )
        for sql in (_EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE):
            assert "ProcessAlarm" not in sql
            assert "AlarmNeedCount" not in sql

    def test_events_template_selects_event_type(self):
        """_PAIR_SQL shape dispatch needs EVENT_TYPE in the events SELECT list."""
        from mes_dashboard.workers.eap_alarm_worker import _EAP_EVENT_SQL_TEMPLATE
        assert "e.EVENT_TYPE," in _EAP_EVENT_SQL_TEMPLATE

    def test_last_update_time_predicate_retained(self):
        """EA-03: index-driving predicate must survive the shape-B widening."""
        from mes_dashboard.workers.eap_alarm_worker import (
            _EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE,
        )
        for sql in (_EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE):
            assert "LAST_UPDATE_TIME BETWEEN" in sql

    def test_templates_render_with_filters(self):
        """f-string conversion keeps {equipment_filter}/{extra_filters} slots working."""
        from mes_dashboard.workers.eap_alarm_worker import (
            _EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE,
        )
        for tpl in (_EAP_EVENT_SQL_TEMPLATE, _DETAIL_SQL_TEMPLATE):
            sql = tpl.format(equipment_filter="e.EQUIPMENT_ID IN (:r0)", extra_filters="\n  AND e.LOT_ID IN (:lot_0)")
            assert "e.EQUIPMENT_ID IN (:r0)" in sql
            assert "e.LOT_ID IN (:lot_0)" in sql
            assert "{" not in sql and "}" not in sql  # no unresolved format slots


class TestEapAlarmRouteFlag:
    """AC-7 (env var gating) / default-on tests."""

    def test_flag_on_by_default(self, monkeypatch):
        monkeypatch.delenv("EAP_ALARM_USE_UNIFIED_JOB", raising=False)
        import importlib
        import mes_dashboard.routes.eap_alarm_routes as rt
        importlib.reload(rt)
        assert rt._EAP_ALARM_USE_UNIFIED_JOB is True

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


class TestExecuteEapAlarmUnifiedJob:
    def test_forwards_query_mode_to_job(self, monkeypatch):
        from mes_dashboard.workers import eap_alarm_worker as worker

        captured = {}

        class FakeJob:
            def __init__(self, job_id, params):
                captured["job_id"] = job_id
                captured["params"] = params
                self._spool_key = "lot-key"

            def run(self):
                return "/tmp/lot.parquet"

        monkeypatch.setattr(worker, "EapAlarmJob", FakeJob)
        monkeypatch.setattr(
            "mes_dashboard.rq_worker_preload.ensure_rq_logging", lambda: None
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.complete_job", lambda *a, **kw: None
        )

        worker.execute_eap_alarm_unified_job(
            job_id="job-lot-001",
            date_from="",
            date_to="",
            lot_ids=["LOT-001"],
            query_mode="lot_ids",
        )

        assert captured["params"]["query_mode"] == "lot_ids"
        assert captured["params"]["lot_ids"] == ["LOT-001"]
