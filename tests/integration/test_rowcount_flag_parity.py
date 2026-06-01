# -*- coding: utf-8 -*-
"""
Tier 1 parity tests for batch-rowcount-unification.

NOT marked integration_real — all Oracle calls are mocked at the service boundary.
Run without special flags:

    conda run -n mes-dashboard pytest \
        tests/integration/test_rowcount_flag_parity.py -v --tb=short

Test classes:
  TestFlagFalseRegression  — flag=false (default) must call date-range chunks (AC-2)
  TestFlagTrueParity       — flag=true must call paged (start_row/end_row) chunks (AC-3)
  TestSpoolSchemaParity    — paged vs date-range chunk key schemas are disjoint (AC-5)
  TestSpoolLifecycle       — cache_prefix passed to execute_plan is unchanged (AC-7)
"""

from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_count_df(row_count: int = 120000) -> pd.DataFrame:
    """Minimal COUNT(*) result as batch_query_engine services expect."""
    return pd.DataFrame([{"ROW_COUNT": row_count}])


def _make_chunk_df(n: int = 5) -> pd.DataFrame:
    """Stub data chunk — columns don't matter for chunk-dispatch tests."""
    return pd.DataFrame({"col_a": range(n), "col_b": ["x"] * n})


def _extract_chunks_from_execute_plan_call(mock_execute_plan) -> list:
    """Return the chunks list passed as the first positional arg to execute_plan."""
    call_args = mock_execute_plan.call_args
    if call_args is None:
        return []
    # chunks is always the first positional argument
    if call_args.args:
        return call_args.args[0]
    return []


def _chunk_key_sets(mock_execute_plan) -> list[set]:
    """Return the set of keys in each chunk dict passed to execute_plan."""
    return [set(c.keys()) for c in _extract_chunks_from_execute_plan_call(mock_execute_plan)]


# ===========================================================================
# 1. TestFlagFalseRegression
# ===========================================================================

class TestFlagFalseRegression:
    """flag=false (default) path must call execute_plan with date-range chunks.

    Regression guard: existing behavior must be byte-for-byte unchanged (AC-2,
    BQE-04).  Key assertion: all chunk dicts contain chunk_start / chunk_end
    and do NOT contain start_row / end_row.
    """

    def test_production_history_flag_false_uses_date_chunks(self, monkeypatch):
        """_run_oracle_to_spool must decompose via date-range when flag=false."""
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service._USE_ROW_COUNT_CHUNKING",
            False,
        )
        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.execute_plan", mock_ep
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.merge_chunks_to_spool", mock_mc
        )

        from mes_dashboard.services.production_history_service import _run_oracle_to_spool

        params = {
            "pj_types": ["A"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "end_date_exclusive": "2025-01-01",
            "lot_ids": [], "work_orders": [], "packages": [],
            "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
            "equipment_ids": [], "pj_packages": [], "pj_bops": [], "pj_functions": [],
            "mfg_orders_tokens": [], "wafer_lots_tokens": [], "lot_ids_tokens": [],
        }
        _run_oracle_to_spool(params, "ph-test001")

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0, "execute_plan must receive at least one chunk"
        for keys in key_sets:
            assert "chunk_start" in keys, f"Expected chunk_start in date-range chunk, got {keys}"
            assert "chunk_end" in keys, f"Expected chunk_end in date-range chunk, got {keys}"
            assert "start_row" not in keys, "start_row must NOT appear in flag=false chunks"
            assert "end_row" not in keys, "end_row must NOT appear in flag=false chunks"

    def test_hold_dataset_flag_false_uses_date_chunks(self, monkeypatch):
        """hold_dataset_cache.execute_primary_query must use date-range chunks when flag=false."""
        from mes_dashboard.services import hold_dataset_cache as hdc

        # Simulate cache miss
        monkeypatch.setattr(hdc, "_dataset_cache", MagicMock(get=MagicMock(return_value=None)))
        monkeypatch.setattr(hdc, "get_spool_file_path", MagicMock(return_value=None))

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", False), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            hdc.execute_primary_query(start_date="2024-01-01", end_date="2024-12-31")

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "chunk_start" in keys, f"Expected date-range chunks, got {keys}"
            assert "start_row" not in keys

    def test_reject_dataset_flag_false_uses_date_chunks(self, monkeypatch):
        """reject_dataset_cache._execute_and_spool must use date-range chunks when flag=false."""
        from mes_dashboard.services import reject_dataset_cache as rdc

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", False), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            rdc._execute_and_spool(
                query_id="rq-test001",
                mode="date_range",
                base_params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
                base_where="1=1",
                container_ids=None,
                progress_callback=None,
            )

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "chunk_start" in keys, f"Expected date-range chunk_start, got {keys}"
            assert "start_row" not in keys

    def test_resource_dataset_flag_false_uses_date_chunks(self, monkeypatch):
        """resource_dataset_cache.execute_primary_query must use date-range chunks when flag=false."""
        from mes_dashboard.services import resource_dataset_cache as rdc

        monkeypatch.setattr(rdc, "_has_cached_df", MagicMock(return_value=False))
        monkeypatch.setattr(rdc, "_has_cached_oee_df", MagicMock(return_value=False))
        monkeypatch.setattr(
            rdc, "_get_filtered_resources_and_lookup",
            MagicMock(return_value=(
                [{"RESOURCEID": "EQ001", "RESOURCENAME": "EQ001"}],
                {"EQ001": "EQ001"},
                "HISTORYID IN (:hid0)",
            ))
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_history_duckdb_cache.should_use_duckdb",
            MagicMock(return_value=False),
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", False), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            rdc.execute_primary_query(start_date="2024-01-01", end_date="2024-12-31")

        assert mock_ep.call_count >= 1, "execute_plan must be called at least once (base)"
        # Resource cache calls execute_plan twice: base then OEE. Use first call for base.
        base_chunks = mock_ep.call_args_list[0].args[0]
        for chunk in base_chunks:
            assert "chunk_start" in chunk, f"Expected date-range chunk, got {chunk}"
            assert "start_row" not in chunk

    def test_job_query_flag_false_uses_date_chunks(self, monkeypatch):
        """job_query_service.get_jobs_by_resources must use date-range chunks when flag=false."""
        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))
        mock_spool_records = MagicMock(return_value=None)

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", False), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0), \
             patch("mes_dashboard.core.query_spool_store.read_spool_records", mock_spool_records):
            from mes_dashboard.services.job_query_service import get_jobs_by_resources
            get_jobs_by_resources(
                resource_ids=["EQ001"],
                start_date="2024-01-01",
                end_date="2024-12-31",
            )

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "chunk_start" in keys, f"Expected date-range chunks, got {keys}"
            assert "start_row" not in keys

    def test_mid_section_defect_flag_false_uses_date_chunks(self, monkeypatch):
        """mid_section_defect_service._fetch_station_detection_data must use date-range chunks."""
        from mes_dashboard.services import mid_section_defect_service as msd

        monkeypatch.setattr(msd, "cache_get", MagicMock(return_value=None))

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", False), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0), \
             patch("mes_dashboard.core.query_spool_store.load_spooled_df", MagicMock(return_value=None)):
            msd._fetch_station_detection_data(
                start_date="2024-01-01",
                end_date="2024-12-31",
                station="測試",
            )

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "chunk_start" in keys, f"Expected date-range chunks, got {keys}"
            assert "start_row" not in keys

    def test_downtime_analysis_flag_false_uses_execute_plan(self, monkeypatch):
        """downtime_analysis_service must always call execute_plan (ADR-0003).

        Downtime uses whole-dataset single chunk — no USE_ROW_COUNT_CHUNKING flag.
        The chunk dict must contain start_date/end_date (not start_row/end_row).
        """
        from mes_dashboard.services import downtime_analysis_service as das

        # has_downtime_events/store_downtime_events are imported locally inside
        # query_downtime_dataset — patch at the source module level.
        # _read_sql_df is also imported locally; patch at core.database level.
        monkeypatch.setattr(das, "_build_response", MagicMock(return_value={}))
        monkeypatch.setattr(das, "_merge_cross_shift_events", MagicMock(return_value=pd.DataFrame()))
        monkeypatch.setattr(das, "_bridge_jobid", MagicMock(return_value=pd.DataFrame()))
        monkeypatch.setattr(das, "_enrich_events_df", MagicMock(return_value=pd.DataFrame()))

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.downtime_analysis_cache.has_downtime_events",
                   MagicMock(return_value=False)), \
             patch("mes_dashboard.services.downtime_analysis_cache.store_downtime_events",
                   MagicMock()), \
             patch("mes_dashboard.core.database.read_sql_df_slow",
                   MagicMock(return_value=pd.DataFrame())):
            das.query_downtime_dataset(
                start_date="2024-01-01",
                end_date="2024-03-31",
            )

        mock_ep.assert_called_once()
        # Downtime uses whole-dataset chunk: {start_date, end_date}
        chunks = _extract_chunks_from_execute_plan_call(mock_ep)
        assert len(chunks) == 1, f"Downtime must use single whole-dataset chunk, got {len(chunks)}"
        chunk_keys = set(chunks[0].keys())
        assert "start_date" in chunk_keys, f"Expected start_date in downtime chunk, got {chunk_keys}"
        assert "start_row" not in chunk_keys, "Downtime must never use row-count chunks (ADR-0003)"


# ===========================================================================
# 2. TestFlagTrueParity
# ===========================================================================

class TestFlagTrueParity:
    """flag=true path must call execute_plan with paged chunks (start_row/end_row).

    AC-3, BQE-02.
    """

    def test_production_history_flag_true_calls_paged_chunks(self, monkeypatch):
        """_run_oracle_to_spool with flag=true must pass start_row/end_row chunks."""
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service._USE_ROW_COUNT_CHUNKING",
            True,
        )
        # COUNT(*) returns 120000 → 3 chunks of 50000 (default rows_per_chunk)
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.query_row_count",
            MagicMock(return_value=120000),
        )
        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.execute_plan", mock_ep
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.merge_chunks_to_spool", mock_mc
        )

        from mes_dashboard.services.production_history_service import _run_oracle_to_spool
        params = {
            "pj_types": ["A"], "start_date": "2024-01-01", "end_date": "2024-12-31",
            "end_date_exclusive": "2025-01-01",
            "lot_ids": [], "work_orders": [], "packages": [],
            "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
            "equipment_ids": [], "pj_packages": [], "pj_bops": [], "pj_functions": [],
            "mfg_orders_tokens": [], "wafer_lots_tokens": [], "lot_ids_tokens": [],
        }
        _run_oracle_to_spool(params, "ph-test002")

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) == 3, f"Expected 3 chunks for 120000 rows, got {len(key_sets)}"
        for keys in key_sets:
            assert "start_row" in keys, f"Expected start_row in paged chunks, got {keys}"
            assert "end_row" in keys, f"Expected end_row in paged chunks, got {keys}"
            assert "chunk_start" not in keys, "chunk_start must NOT appear in flag=true chunks"

    def test_hold_dataset_flag_true_calls_paged_chunks(self, monkeypatch):
        """hold_dataset_cache.execute_primary_query must use paged chunks when flag=true."""
        from mes_dashboard.services import hold_dataset_cache as hdc

        monkeypatch.setattr(hdc, "_dataset_cache", MagicMock(get=MagicMock(return_value=None)))
        monkeypatch.setattr(hdc, "get_spool_file_path", MagicMock(return_value=None))
        # COUNT query stub — hold service uses read_sql_df (re-aliased from read_sql_df_slow)
        monkeypatch.setattr(
            hdc, "read_sql_df",
            MagicMock(return_value=_make_count_df(75000)),
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", True), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            hdc.execute_primary_query(start_date="2024-01-01", end_date="2024-12-31")

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "start_row" in keys, f"Expected paged chunks, got {keys}"
            assert "chunk_start" not in keys

    def test_reject_dataset_flag_true_calls_paged_chunks(self, monkeypatch):
        """reject_dataset_cache._execute_and_spool must use paged chunks when flag=true."""
        from mes_dashboard.services import reject_dataset_cache as rdc

        # Stub _read_sql_with_caller at module level so the count query returns a value
        monkeypatch.setattr(
            rdc, "_read_sql_with_caller",
            MagicMock(return_value=_make_count_df(60000)),
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", True), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            rdc._execute_and_spool(
                query_id="rq-test002",
                mode="date_range",
                base_params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
                base_where="1=1",
                container_ids=None,
                progress_callback=None,
            )

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "start_row" in keys, f"Expected paged chunks, got {keys}"
            assert "chunk_start" not in keys

    def test_resource_dataset_flag_true_calls_paged_chunks(self, monkeypatch):
        """resource_dataset_cache.execute_primary_query must use paged chunks when flag=true."""
        from mes_dashboard.services import resource_dataset_cache as rdc

        monkeypatch.setattr(rdc, "_has_cached_df", MagicMock(return_value=False))
        monkeypatch.setattr(rdc, "_has_cached_oee_df", MagicMock(return_value=False))
        monkeypatch.setattr(
            rdc, "_get_filtered_resources_and_lookup",
            MagicMock(return_value=(
                [{"RESOURCEID": "EQ001"}],
                {"EQ001": "EQ001"},
                "HISTORYID IN (:hid0)",
            ))
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_history_duckdb_cache.should_use_duckdb",
            MagicMock(return_value=False),
        )
        monkeypatch.setattr(
            rdc, "read_sql_df",
            MagicMock(return_value=_make_count_df(80000)),
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", True), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            rdc.execute_primary_query(start_date="2024-01-01", end_date="2024-12-31")

        assert mock_ep.call_count >= 1
        # Resource cache calls execute_plan twice: once for base (paged), once for OEE
        # (always date-range). Check the FIRST call for base path.
        base_chunks = mock_ep.call_args_list[0].args[0]
        for chunk in base_chunks:
            assert "start_row" in chunk, f"Expected paged chunk for base, got {chunk}"
            assert "chunk_start" not in chunk

    def test_job_query_flag_true_calls_paged_chunks(self, monkeypatch):
        """job_query_service.get_jobs_by_resources must use paged chunks when flag=true."""
        from mes_dashboard.services import job_query_service as jqs

        # Stub read_sql_df at module level to return the count result
        monkeypatch.setattr(
            jqs, "read_sql_df",
            MagicMock(return_value=_make_count_df(55000)),
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", True), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0), \
             patch("mes_dashboard.core.query_spool_store.read_spool_records", MagicMock(return_value=None)):
            jqs.get_jobs_by_resources(
                resource_ids=["EQ001"],
                start_date="2024-01-01",
                end_date="2024-12-31",
            )

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "start_row" in keys, f"Expected paged chunks, got {keys}"
            assert "chunk_start" not in keys

    def test_mid_section_defect_flag_true_calls_paged_chunks(self, monkeypatch):
        """mid_section_defect_service._fetch_station_detection_data must use paged chunks."""
        from mes_dashboard.services import mid_section_defect_service as msd

        monkeypatch.setattr(msd, "cache_get", MagicMock(return_value=None))
        monkeypatch.setattr(
            msd, "read_sql_df",
            MagicMock(return_value=_make_count_df(70000)),
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", True), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0), \
             patch("mes_dashboard.core.query_spool_store.load_spooled_df", MagicMock(return_value=None)):
            msd._fetch_station_detection_data(
                start_date="2024-01-01",
                end_date="2024-12-31",
                station="測試",
            )

        mock_ep.assert_called_once()
        key_sets = _chunk_key_sets(mock_ep)
        assert len(key_sets) > 0
        for keys in key_sets:
            assert "start_row" in keys, f"Expected paged chunks, got {keys}"
            assert "chunk_start" not in keys


# ===========================================================================
# 3. TestSpoolSchemaParity
# ===========================================================================

class TestSpoolSchemaParity:
    """decompose_by_row_count produces {start_row, end_row} dicts; date-range produces
    {chunk_start, chunk_end}. Verify structural contract for both decomposers.
    """

    def test_row_count_chunks_have_start_row_end_row_only(self):
        """decompose_by_row_count must return dicts with exactly start_row and end_row."""
        from mes_dashboard.services.batch_query_engine import decompose_by_row_count
        chunks = decompose_by_row_count(total_rows=120000, rows_per_chunk=50000)
        assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
        for chunk in chunks:
            assert set(chunk.keys()) == {"start_row", "end_row"}, (
                f"Unexpected keys in paged chunk: {set(chunk.keys())}"
            )

    def test_date_range_chunks_have_chunk_start_chunk_end_only(self):
        """decompose_by_time_range must return dicts with chunk_start and chunk_end."""
        from mes_dashboard.services.batch_query_engine import decompose_by_time_range
        chunks = decompose_by_time_range("2024-01-01", "2024-06-30")
        assert len(chunks) >= 1
        for chunk in chunks:
            assert "chunk_start" in chunk, f"Missing chunk_start in {chunk}"
            assert "chunk_end" in chunk, f"Missing chunk_end in {chunk}"
            assert "start_row" not in chunk
            assert "end_row" not in chunk

    def test_paged_chunks_are_1_based_inclusive_no_gap_no_overlap(self):
        """decompose_by_row_count chunks must be 1-based, contiguous, and cover total_rows."""
        from mes_dashboard.services.batch_query_engine import decompose_by_row_count
        total = 130000
        chunks = decompose_by_row_count(total_rows=total, rows_per_chunk=50000)
        assert chunks[0]["start_row"] == 1, "First chunk must start at row 1 (1-based)"
        prev_end = 0
        for chunk in chunks:
            assert chunk["start_row"] == prev_end + 1, (
                f"Gap detected: prev_end={prev_end}, start_row={chunk['start_row']}"
            )
            assert chunk["end_row"] >= chunk["start_row"]
            prev_end = chunk["end_row"]
        assert prev_end == total, f"Final end_row {prev_end} != total_rows {total}"

    def test_paged_and_date_range_chunk_keys_are_disjoint(self):
        """The key sets of paged vs date-range chunks must not overlap (AC-5 schema separation)."""
        from mes_dashboard.services.batch_query_engine import (
            decompose_by_row_count,
            decompose_by_time_range,
        )
        paged_keys = set(decompose_by_row_count(100000)[0].keys())
        date_keys = set(decompose_by_time_range("2024-01-01", "2024-06-30")[0].keys())
        overlap = paged_keys & date_keys
        assert not overlap, (
            f"Chunk key overlap between paged and date-range decomposers: {overlap}"
        )


# ===========================================================================
# 4. TestSpoolLifecycle
# ===========================================================================

class TestSpoolLifecycle:
    """cache_prefix and parallel passed to execute_plan must be unchanged under flag=true.

    AC-7: spool TTL/namespace invariance.
    """

    def test_production_history_cache_prefix_is_prod_hist_flag_true(self, monkeypatch):
        """cache_prefix='prod_hist' must be forwarded regardless of flag value."""
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service._USE_ROW_COUNT_CHUNKING", True
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.query_row_count",
            MagicMock(return_value=50000),
        )
        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.execute_plan", mock_ep
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.merge_chunks_to_spool", mock_mc
        )

        from mes_dashboard.services.production_history_service import _run_oracle_to_spool
        params = {
            "pj_types": ["A"], "start_date": "2024-01-01", "end_date": "2024-03-31",
            "end_date_exclusive": "2024-04-01",
            "lot_ids": [], "work_orders": [], "packages": [],
            "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
            "equipment_ids": [], "pj_packages": [], "pj_bops": [], "pj_functions": [],
            "mfg_orders_tokens": [], "wafer_lots_tokens": [], "lot_ids_tokens": [],
        }
        _run_oracle_to_spool(params, "ph-test003")

        mock_ep.assert_called_once()
        cache_prefix = mock_ep.call_args.kwargs.get("cache_prefix")
        assert cache_prefix == "prod_hist", (
            f"cache_prefix must be 'prod_hist' (unchanged), got {cache_prefix!r}"
        )

    def test_downtime_cache_prefix_is_downtime_analysis(self, monkeypatch):
        """downtime execute_plan must always use cache_prefix='downtime_analysis'."""
        from mes_dashboard.services import downtime_analysis_service as das

        monkeypatch.setattr(das, "_build_response", MagicMock(return_value={}))
        monkeypatch.setattr(das, "_merge_cross_shift_events", MagicMock(return_value=pd.DataFrame()))
        monkeypatch.setattr(das, "_bridge_jobid", MagicMock(return_value=pd.DataFrame()))
        monkeypatch.setattr(das, "_enrich_events_df", MagicMock(return_value=pd.DataFrame()))

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.downtime_analysis_cache.has_downtime_events",
                   MagicMock(return_value=False)), \
             patch("mes_dashboard.services.downtime_analysis_cache.store_downtime_events",
                   MagicMock()), \
             patch("mes_dashboard.core.database.read_sql_df_slow",
                   MagicMock(return_value=pd.DataFrame())):
            das.query_downtime_dataset(start_date="2024-01-01", end_date="2024-01-31")

        mock_ep.assert_called_once()
        cache_prefix = mock_ep.call_args.kwargs.get("cache_prefix")
        assert cache_prefix == "downtime_analysis", (
            f"downtime cache_prefix must be 'downtime_analysis', got {cache_prefix!r}"
        )

    def test_hold_cache_prefix_is_hold_flag_false(self, monkeypatch):
        """hold_dataset_cache execute_plan must use cache_prefix='hold'."""
        from mes_dashboard.services import hold_dataset_cache as hdc

        monkeypatch.setattr(hdc, "_dataset_cache", MagicMock(get=MagicMock(return_value=None)))
        monkeypatch.setattr(hdc, "get_spool_file_path", MagicMock(return_value=None))

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine._USE_ROW_COUNT_CHUNKING", False), \
             patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.batch_query_engine.BATCH_QUERY_TIME_THRESHOLD_DAYS", 0):
            hdc.execute_primary_query(start_date="2024-01-01", end_date="2024-12-31")

        mock_ep.assert_called_once()
        cache_prefix = mock_ep.call_args.kwargs.get("cache_prefix")
        assert cache_prefix == "hold", (
            f"hold cache_prefix must be 'hold', got {cache_prefix!r}"
        )

    def test_downtime_parallel_is_1_whole_dataset(self, monkeypatch):
        """downtime execute_plan must always use parallel=1 (ADR-0003)."""
        from mes_dashboard.services import downtime_analysis_service as das

        monkeypatch.setattr(das, "_build_response", MagicMock(return_value={}))
        monkeypatch.setattr(das, "_merge_cross_shift_events", MagicMock(return_value=pd.DataFrame()))
        monkeypatch.setattr(das, "_bridge_jobid", MagicMock(return_value=pd.DataFrame()))
        monkeypatch.setattr(das, "_enrich_events_df", MagicMock(return_value=pd.DataFrame()))

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))

        with patch("mes_dashboard.services.batch_query_engine.execute_plan", mock_ep), \
             patch("mes_dashboard.services.batch_query_engine.merge_chunks_to_spool", mock_mc), \
             patch("mes_dashboard.services.downtime_analysis_cache.has_downtime_events",
                   MagicMock(return_value=False)), \
             patch("mes_dashboard.services.downtime_analysis_cache.store_downtime_events",
                   MagicMock()), \
             patch("mes_dashboard.core.database.read_sql_df_slow",
                   MagicMock(return_value=pd.DataFrame())):
            das.query_downtime_dataset(start_date="2024-01-01", end_date="2024-01-31")

        mock_ep.assert_called_once()
        parallel = mock_ep.call_args.kwargs.get("parallel")
        assert parallel == 1, (
            f"downtime parallel must be 1 per ADR-0003, got {parallel}"
        )


# ===========================================================================
# 5. TestPartialChunkFailure
# ===========================================================================

class TestPartialChunkFailure:
    """Partial Oracle error during chunked execution must not write a partial spool.

    Invariant: if execute_plan raises then merge_chunks_to_spool must NOT be
    called.  If merge_chunks_to_spool returns (None, 0) then register_spool_file
    must NOT be called (no orphan parquet written).

    These are mock-based tests — no real Oracle or Redis required.
    """

    def test_execute_plan_raises_skips_merge_chunks_to_spool(self, monkeypatch):
        """When execute_plan raises, merge_chunks_to_spool must not be called.

        Uses _run_oracle_to_spool as the probe because it is the thinnest
        wrapper around execute_plan / merge_chunks_to_spool.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service._USE_ROW_COUNT_CHUNKING",
            False,
        )

        def _ep_raises(*args, **kwargs):
            raise RuntimeError("Oracle error injected on 2nd chunk")

        mock_mc = MagicMock(return_value=(None, 0))

        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.execute_plan",
            _ep_raises,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.merge_chunks_to_spool",
            mock_mc,
        )

        from mes_dashboard.services.production_history_service import _run_oracle_to_spool

        params = {
            "pj_types": ["A"], "start_date": "2024-01-01", "end_date": "2024-12-31",
            "end_date_exclusive": "2025-01-01",
            "lot_ids": [], "work_orders": [], "packages": [],
            "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
            "equipment_ids": [], "pj_packages": [], "pj_bops": [], "pj_functions": [],
            "mfg_orders_tokens": [], "wafer_lots_tokens": [], "lot_ids_tokens": [],
        }
        with pytest.raises(RuntimeError, match="Oracle error injected"):
            _run_oracle_to_spool(params, "ph-partial-err")

        mock_mc.assert_not_called()

    def test_merge_chunks_returning_none_prevents_spool_registration(self, monkeypatch):
        """When merge_chunks_to_spool returns (None, 0), register_spool_file is not called.

        Covers the case where all chunks fail with partial failure — 0 rows merged.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service._USE_ROW_COUNT_CHUNKING",
            False,
        )

        mock_ep = MagicMock(return_value=None)
        mock_mc = MagicMock(return_value=(None, 0))
        mock_reg = MagicMock()

        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.execute_plan", mock_ep
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.merge_chunks_to_spool", mock_mc
        )
        monkeypatch.setattr(
            "mes_dashboard.services.production_history_service.register_spool_file", mock_reg
        )

        from mes_dashboard.services.production_history_service import _run_oracle_to_spool

        params = {
            "pj_types": ["A"], "start_date": "2024-01-01", "end_date": "2024-12-31",
            "end_date_exclusive": "2025-01-01",
            "lot_ids": [], "work_orders": [], "packages": [],
            "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
            "equipment_ids": [], "pj_packages": [], "pj_bops": [], "pj_functions": [],
            "mfg_orders_tokens": [], "wafer_lots_tokens": [], "lot_ids_tokens": [],
        }
        _run_oracle_to_spool(params, "ph-partial-none")

        mock_mc.assert_called_once()
        mock_reg.assert_not_called()
