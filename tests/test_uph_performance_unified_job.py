# -*- coding: utf-8 -*-
"""Unit tests for UphPerformanceJob (add-uph-performance-page).

Mirrors tests/test_eap_alarm_unified_job.py / tests/test_production_achievement_unified_job.py
shapes: pre_query chunk-window assertions, build_chunk_sql SQL/binds shape,
and post_aggregate parquet-writing + enrichment-bridge behavior with mocked
Oracle reads (no real DB/Redis required).
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


class TestUphPerformanceJobPreQuery:
    """AC-2: pre_query builds <=6h TIME chunks and resolves the spool key."""

    def test_pre_query_builds_time_chunks(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("test-job-1", params={
            "date_from": "2026-01-01",
            "date_to": "2026-01-01",
            "families": ["GDBA"],
        })
        job.pre_query()

        # a single day is split into 4 chunks of 6h each (00-06, 06-12, 12-18, 18-24)
        assert len(job._chunks) == 4
        assert job._chunks[0]["chunk_start"] == "2026-01-01 00:00:00"
        assert job._chunks[0]["chunk_end"] == "2026-01-01 06:00:00"
        assert job._chunks[-1]["chunk_end"] == "2026-01-02 00:00:00"
        assert job._spool_key.startswith("uph_performance_2026-01-01_2026-01-01_")

    def test_pre_query_family_filter_scoped_to_selected_family(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("test-job-2", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01", "families": ["GWBA"],
        })
        job.pre_query()
        assert job._family_filter == "e.EQUIPMENT_ID LIKE 'GWBA%'"


class TestUphPerformanceJobBuildChunkSql:
    """AC-3: build_chunk_sql returns the shared template with bound chunk window."""

    def test_build_chunk_sql_contains_family_conditional_join(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01", "equipment_ids": ["GDBA-01"],
        })
        job.pre_query()
        sql, binds = job.build_chunk_sql(job._chunks[0])

        assert "EAP_EVENT_DETAIL" in sql
        assert "LEFT JOIN" in sql
        assert "chunk_start" in binds and "chunk_end" in binds
        assert any(k.startswith("eqid_") for k in binds)


class TestUphPerformanceJobPostAggregate:
    """AC-4: post_aggregate concats chunk parquets and bridges product/workcenter dims."""

    def _make_events_table(self):
        return pa.table({
            "LOT_ID": ["LOT001", "LOT002"],
            "EQUIPMENT_ID": ["GDBA-01", "GWBA-02"],
            "EQUIPMENT_FAMILY": ["GDBA", "GWBA"],
            "EVENT_TIME": pd.to_datetime(["2026-01-01 01:00:00", "2026-01-01 02:00:00"]),
            "PARAMETER_NAME": ["BondUPH", "fHCM_UPH"],
            "UPH_VALUE_RAW": ["120.5", "88.2"],
        })

    def test_post_aggregate_writes_parquet_with_correct_columns(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid-agg", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01",
        })
        job.pre_query()
        job._spool_path = str(tmp_path / "spool.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        pq.write_table(self._make_events_table(), chunk_dir / "chunk-0000-0000.parquet")

        empty_product = pd.DataFrame(
            columns=["LOT_ID", "PACKAGE", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION", "PRODUCTNAME"]
        )
        empty_workcenter = pd.DataFrame(columns=["EQUIPMENT_ID", "WORKCENTERNAME", "MODEL", "DB_WB_LABEL"])

        with patch(
            "mes_dashboard.workers.uph_performance_worker._safe_lot_product_df",
            return_value=empty_product,
        ), patch(
            "mes_dashboard.workers.uph_performance_worker._safe_workcenter_df",
            return_value=empty_workcenter,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            return_value=True,
        ):
            spool_path = job.post_aggregate(None)

        assert spool_path == job._spool_path
        table = pq.read_table(spool_path)
        columns = set(table.column_names)
        expected = {
            "LOT_ID", "EQUIPMENT_ID", "EQUIPMENT_FAMILY", "EVENT_TIME",
            "PARAMETER_NAME", "UPH_VALUE", "WORKCENTERNAME", "MODEL", "DB_WB_LABEL",
            "PACKAGE", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION", "coarse_filter_hash",
        }
        assert expected.issubset(columns)
        assert table.num_rows == 2

        df = table.to_pandas()
        assert df["UPH_VALUE"].tolist() == pytest.approx([120.5, 88.2])

    def test_post_aggregate_empty_chunk_dir_writes_empty_parquet(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid-empty", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01",
        })
        job.pre_query()
        job._spool_path = str(tmp_path / "empty_spool.parquet")
        job._make_chunk_parquet_dir(job.job_id)  # create empty dir, no chunk files

        with patch(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            return_value=True,
        ):
            spool_path = job.post_aggregate(None)

        table = pq.read_table(spool_path)
        assert table.num_rows == 0

    def test_post_aggregate_bridges_die_wire_counts_via_mes_product(self, tmp_path, monkeypatch):
        """PRODUCTNAME -> DWH.MES_PRODUCT bridge: DIE_COUNT/WIRE_COUNT populate
        correctly in the final joined output when the chained Oracle lookup
        succeeds (mirrors the Package/Type/workcenter bridge assertions above)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid-mesprod-happy", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01",
        })
        job.pre_query()
        job._spool_path = str(tmp_path / "spool.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        pq.write_table(self._make_events_table(), chunk_dir / "chunk-0000-0000.parquet")

        lot_product_df = pd.DataFrame({
            "LOT_ID": ["LOT001", "LOT002"],
            "PACKAGE": ["PKG-A", "PKG-B"],
            "PJ_TYPE": ["TYPE-A", "TYPE-B"],
            "PJ_BOP": ["BOP-A", "BOP-B"],
            "PJ_FUNCTION": ["FUNC-A", "FUNC-B"],
            "PRODUCTNAME": ["PROD-A", "PROD-B"],
        })
        empty_workcenter = pd.DataFrame(columns=["EQUIPMENT_ID", "WORKCENTERNAME", "MODEL", "DB_WB_LABEL"])

        def _fake_read_sql_df_slow(sql, params=None, timeout_seconds=None, caller="unknown"):
            return pd.DataFrame({
                "PRODUCTNAME": ["PROD-A", "PROD-B"],
                "DIE_COUNT": [12, 24],
                "WIRE_COUNT": [4, 8],
            })

        with patch(
            "mes_dashboard.workers.uph_performance_worker._safe_lot_product_df",
            return_value=lot_product_df,
        ), patch(
            "mes_dashboard.workers.uph_performance_worker._safe_workcenter_df",
            return_value=empty_workcenter,
        ), patch(
            "mes_dashboard.core.database.read_sql_df_slow",
            side_effect=_fake_read_sql_df_slow,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            return_value=True,
        ):
            spool_path = job.post_aggregate(None)

        df = pq.read_table(spool_path).to_pandas().sort_values("LOT_ID").reset_index(drop=True)
        assert df.loc[0, "DIE_COUNT"] == "12"
        assert df.loc[0, "WIRE_COUNT"] == "4"
        assert df.loc[1, "DIE_COUNT"] == "24"
        assert df.loc[1, "WIRE_COUNT"] == "8"

    def test_post_aggregate_mes_product_degrade_path_never_raises_and_is_null(
        self, tmp_path, monkeypatch,
    ):
        """Oracle fetch raises -> empty frame; DIE_COUNT/WIRE_COUNT come out NULL
        in the final joined output, and the job does NOT raise."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob

        job = UphPerformanceJob("jid-mesprod-degrade", params={
            "date_from": "2026-01-01", "date_to": "2026-01-01",
        })
        job.pre_query()
        job._spool_path = str(tmp_path / "spool.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        pq.write_table(self._make_events_table(), chunk_dir / "chunk-0000-0000.parquet")

        lot_product_df = pd.DataFrame({
            "LOT_ID": ["LOT001", "LOT002"],
            "PACKAGE": ["PKG-A", "PKG-B"],
            "PJ_TYPE": ["TYPE-A", "TYPE-B"],
            "PJ_BOP": ["BOP-A", "BOP-B"],
            "PJ_FUNCTION": ["FUNC-A", "FUNC-B"],
            "PRODUCTNAME": ["PROD-A", "PROD-B"],
        })
        empty_workcenter = pd.DataFrame(columns=["EQUIPMENT_ID", "WORKCENTERNAME", "MODEL", "DB_WB_LABEL"])

        def _raise(*args, **kwargs):
            raise RuntimeError("ORA-12541: TNS:no listener")

        with patch(
            "mes_dashboard.workers.uph_performance_worker._safe_lot_product_df",
            return_value=lot_product_df,
        ), patch(
            "mes_dashboard.workers.uph_performance_worker._safe_workcenter_df",
            return_value=empty_workcenter,
        ), patch(
            "mes_dashboard.core.database.read_sql_df_slow",
            side_effect=_raise,
        ), patch(
            "mes_dashboard.core.query_spool_store.register_spool_file",
            return_value=True,
        ):
            spool_path = job.post_aggregate(None)  # must not raise

        df = pq.read_table(spool_path).to_pandas()
        assert df["DIE_COUNT"].isna().all()
        assert df["WIRE_COUNT"].isna().all()


class TestSafeMesProductDf:
    """PRODUCTNAME -> DWH.MES_PRODUCT (DIE_COUNT/WIRE_COUNT) bridge, isolated
    from the rest of post_aggregate -- mirrors _safe_lot_product_df/
    _safe_workcenter_df's best-effort degrade contract (never raises)."""

    def test_happy_path_resolves_die_wire_counts(self, monkeypatch):
        from mes_dashboard.workers import uph_performance_worker as uph_mod

        lot_product_df = pd.DataFrame({
            "LOT_ID": ["LOT001"],
            "PACKAGE": ["PKG-A"],
            "PJ_TYPE": ["TYPE-A"],
            "PJ_BOP": ["BOP-A"],
            "PJ_FUNCTION": ["FUNC-A"],
            "PRODUCTNAME": ["PROD-A"],
        })

        def _fake_read_sql_df_slow(sql, params=None, timeout_seconds=None, caller="unknown"):
            return pd.DataFrame({
                "PRODUCTNAME": ["PROD-A"],
                "DIE_COUNT": [12],
                "WIRE_COUNT": [4],
            })

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow", _fake_read_sql_df_slow,
        )

        result = uph_mod._safe_mes_product_df(lot_product_df, timeout_seconds=30)

        assert list(result.columns) == uph_mod._MES_PRODUCT_COLUMNS
        assert result.loc[0, "PRODUCTNAME"] == "PROD-A"
        assert result.loc[0, "DIE_COUNT"] == 12
        assert result.loc[0, "WIRE_COUNT"] == 4

    def test_degrade_path_oracle_failure_returns_empty_frame_without_raising(self, monkeypatch):
        from mes_dashboard.workers import uph_performance_worker as uph_mod

        lot_product_df = pd.DataFrame({
            "LOT_ID": ["LOT001"], "PRODUCTNAME": ["PROD-A"],
        })

        def _raise(*args, **kwargs):
            raise RuntimeError("ORA-12541: TNS:no listener")

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow", _raise,
        )

        result = uph_mod._safe_mes_product_df(lot_product_df, timeout_seconds=30)

        assert result.empty
        assert list(result.columns) == uph_mod._MES_PRODUCT_COLUMNS

    def test_missing_lot_product_frame_degrades_without_oracle_call(self, monkeypatch):
        """No LOT_ID->PRODUCTNAME resolved yet (empty lot_product_df) -> empty
        frame without ever touching Oracle."""
        from mes_dashboard.workers import uph_performance_worker as uph_mod

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("Oracle must not be called when lot_product_df is empty")

        monkeypatch.setattr(
            "mes_dashboard.core.database.read_sql_df_slow", _fail_if_called,
        )

        empty_lot_product = pd.DataFrame(
            columns=["LOT_ID", "PACKAGE", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION", "PRODUCTNAME"]
        )
        result = uph_mod._safe_mes_product_df(empty_lot_product, timeout_seconds=30)

        assert result.empty
        assert list(result.columns) == uph_mod._MES_PRODUCT_COLUMNS
