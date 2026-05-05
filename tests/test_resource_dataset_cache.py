# -*- coding: utf-8 -*-
"""Unit tests for resource_dataset_cache — engine integration and DuckDB paths."""

from __future__ import annotations

import importlib
import pandas as pd
from unittest.mock import MagicMock

from mes_dashboard.services import resource_dataset_cache as cache_svc


class TestResourceEngineDecomposition:
    """resource-history with long date range triggers engine."""

    def test_long_range_triggers_engine(self, monkeypatch):
        """90-day range → engine decomposition activated."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        engine_calls = {"execute": 0, "merge": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 3  # 90 days / 31 = 3 chunks
            return kwargs.get("query_hash", "fake_hash")

        def fake_merge_chunks_to_spool(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return ("/tmp/fake_spool.parquet", 2)

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_store_oee_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1", "RESOURCENAME": "Machine-1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (SELECT HISTORYID FROM RESOURCEHISTORY)",
            ),
        )
        monkeypatch.setattr(
            cache_svc,
            "register_spool_file",
            lambda *a, **kw: "/tmp/fake_spool.parquet",
        )
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

        result = cache_svc.execute_primary_query(
            start_date="2025-01-01",
            end_date="2025-03-31",
            workcenter_groups=["WB"],
        )

        assert engine_calls["execute"] == 2  # base + oee
        assert engine_calls["merge"] == 2  # base + oee
        assert result["query_id"] is not None

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        engine_calls = {"execute": 0}

        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "read_sql_df",
            lambda sql, params, caller=None: pd.DataFrame({"HISTORYID": [1]}),
        )
        monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_store_oee_df", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (SELECT HISTORYID FROM RESOURCEHISTORY)",
            ),
        )
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

        result = cache_svc.execute_primary_query(
            start_date="2025-06-01",
            end_date="2025-06-30",
            workcenter_groups=["WB"],
        )

        assert engine_calls["execute"] == 0  # Engine NOT used


class TestResourceStoreDf:
    """_store_df writes to spool and sets L1 marker."""

    def test_store_df_calls_store_spooled_df(self, monkeypatch):
        """_store_df calls store_spooled_df (spool-first, no redis large df)."""
        spool_calls = []

        monkeypatch.setattr(
            cache_svc,
            "store_spooled_df",
            lambda ns, qid, df, **kw: spool_calls.append((ns, qid)),
        )
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        df = pd.DataFrame({"HISTORYID": [1]})
        cache_svc._store_df("qid-resource-spool", df)

        assert len(spool_calls) == 1
        assert spool_calls[0] == (cache_svc._REDIS_NAMESPACE, "qid-resource-spool")


class TestResourceApplyView:
    """Phase 3: apply_view uses DuckDB SQL runtime as the sole compute path."""

    def test_apply_view_sql_result_none_returns_none(self, monkeypatch):
        """apply_view returns None when DuckDB runtime returns no result (spool miss)."""
        from mes_dashboard.services import resource_history_sql_runtime

        monkeypatch.setattr(
            resource_history_sql_runtime,
            "try_compute_view_from_spool",
            lambda **_kwargs: (None, {"view_sql_fallback_reason": "spool_miss"}),
        )

        result = cache_svc.apply_view(query_id="res-none-qid")
        assert result is None


class TestResourceBootstrapFailureSemantics:
    """Task 2.3: execute_primary_query must fail loudly when spool exists but apply_view returns None."""

    def _make_resource_env(self, monkeypatch, *, spool_created: bool, apply_view_result):
        """Patch execute_primary_query environment for short direct path."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        # Force direct path regardless of BATCH_QUERY_TIME_THRESHOLD_DAYS env setting
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (SELECT HISTORYID FROM RESOURCEHISTORY)",
            ),
        )
        if spool_created:
            monkeypatch.setattr(
                cache_svc,
                "read_sql_df",
                lambda sql, params, caller=None: pd.DataFrame({"HISTORYID": [1]}),
            )
            monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
            monkeypatch.setattr(cache_svc, "_store_oee_df", lambda *a, **kw: None)
        else:
            monkeypatch.setattr(
                cache_svc,
                "read_sql_df",
                lambda sql, params, caller=None: pd.DataFrame(),
            )
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: apply_view_result,
        )

    def test_spool_created_apply_view_none_raises(self, monkeypatch):
        """When Oracle produces data (spool created) but apply_view fails → RuntimeError."""
        self._make_resource_env(monkeypatch, spool_created=True, apply_view_result=None)
        import pytest
        with pytest.raises(RuntimeError, match="bootstrap render failure"):
            cache_svc.execute_primary_query(
                start_date="2025-06-01",
                end_date="2025-06-30",
            )

    def test_no_spool_apply_view_none_returns_empty(self, monkeypatch):
        """When Oracle returns empty data (no spool) and apply_view fails → empty result, no raise."""
        self._make_resource_env(monkeypatch, spool_created=False, apply_view_result=None)
        result = cache_svc.execute_primary_query(
            start_date="2025-06-01",
            end_date="2025-06-30",
        )
        assert result["query_id"] is not None
        assert result["summary"]["kpi"]["machine_count"] == 0
        assert result["detail"]["total"] == 0

    def test_cache_hit_apply_view_none_raises(self, monkeypatch):
        """When spool exists (cache hit) but apply_view fails → RuntimeError."""
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: True)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: True)
        monkeypatch.setattr(cache_svc, "apply_view", lambda **kw: None)
        import pytest
        with pytest.raises(RuntimeError, match="bootstrap render failure"):
            cache_svc.execute_primary_query(
                start_date="2025-06-01",
                end_date="2025-06-30",
            )


# ============================================================
# Task 8: TTL env var tests
# ============================================================

class TestCacheTTLEnvVar:
    """CACHE_TTL_DATASET_SECONDS env var controls _CACHE_TTL."""

    def test_default_ttl_is_7200(self):
        """Without CACHE_TTL_DATASET_SECONDS → constants.CACHE_TTL_DATASET == 7200."""
        import mes_dashboard.config.constants as constants_mod
        # Re-check the current value (env not set in test environment)
        import importlib
        import os
        # Ensure env not set, then reload
        saved = os.environ.pop("CACHE_TTL_DATASET_SECONDS", None)
        try:
            importlib.reload(constants_mod)
            assert constants_mod.CACHE_TTL_DATASET == 7200
        finally:
            if saved is not None:
                os.environ["CACHE_TTL_DATASET_SECONDS"] = saved
            importlib.reload(constants_mod)

    def test_env_var_overrides_ttl(self, monkeypatch):
        """CACHE_TTL_DATASET_SECONDS=1800 + reload → _CACHE_TTL == 1800."""
        import mes_dashboard.config.constants as constants_mod
        monkeypatch.setenv("CACHE_TTL_DATASET_SECONDS", "1800")
        importlib.reload(constants_mod)
        assert constants_mod.CACHE_TTL_DATASET == 1800
        # Reload to clean up
        monkeypatch.delenv("CACHE_TTL_DATASET_SECONDS", raising=False)
        importlib.reload(constants_mod)

    def test_execute_primary_query_uses_cache_ttl(self, monkeypatch):
        """execute_primary_query → store_spooled_df is called with ttl_seconds == _CACHE_TTL."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        ttl_calls = []

        def fake_store_spooled_df(ns, qid, df, **kw):
            ttl_calls.append(kw.get("ttl_seconds"))

        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (1)",
            ),
        )
        monkeypatch.setattr(
            cache_svc,
            "read_sql_df",
            lambda sql, params, caller=None: pd.DataFrame({"HISTORYID": [1]}),
        )
        monkeypatch.setattr(cache_svc, "store_spooled_df", fake_store_spooled_df)
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

        cache_svc.execute_primary_query(start_date="2025-06-01", end_date="2025-06-30")

        assert len(ttl_calls) >= 1
        for ttl in ttl_calls:
            assert ttl == cache_svc._CACHE_TTL


# ============================================================
# Task 9.1: Resource engine parallel env var tests
# ============================================================

class TestResourceEngineParallel:
    """RESOURCE_ENGINE_PARALLEL env var controls execute_plan parallel for resource cache."""

    def _make_engine_env(self, monkeypatch, *, engine_calls):
        """Setup monkeypatches for engine path (long date range)."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls.append(kwargs.get("parallel"))
            return kwargs.get("query_hash", "fake_hash")

        def fake_merge(prefix, qhash, **kwargs):
            return ("/tmp/fake.parquet", 2)

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge)
        monkeypatch.setattr(engine_mod, "get_batch_progress", lambda *a: {})
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (1)",
            ),
        )
        monkeypatch.setattr(cache_svc, "register_spool_file", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

    def test_default_parallel_is_1(self, monkeypatch):
        """Without RESOURCE_ENGINE_PARALLEL → both execute_plan calls get parallel=1."""
        engine_calls = []
        monkeypatch.delenv("RESOURCE_ENGINE_PARALLEL", raising=False)
        monkeypatch.setattr(cache_svc, "_RESOURCE_ENGINE_PARALLEL", 1)
        self._make_engine_env(monkeypatch, engine_calls=engine_calls)

        cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert len(engine_calls) == 2  # base + oee
        assert all(p == 1 for p in engine_calls)

    def test_parallel_2_passed_to_both_execute_plans(self, monkeypatch):
        """RESOURCE_ENGINE_PARALLEL=2 → both execute_plan calls get parallel=2."""
        engine_calls = []
        monkeypatch.setattr(cache_svc, "_RESOURCE_ENGINE_PARALLEL", 2)
        self._make_engine_env(monkeypatch, engine_calls=engine_calls)

        cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert len(engine_calls) == 2  # base + oee
        assert all(p == 2 for p in engine_calls)


# ============================================================
# Task 10.1-10.5: Resource partial failure propagation tests
# ============================================================

class TestResourcePartialFailure:
    """execute_plan partial failure propagates to result['_meta']['partial_failure']."""

    def _make_engine_env(self, monkeypatch, *, base_progress=None, oee_progress=None):
        """Setup for engine path with configurable batch progress responses."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        def fake_execute_plan(chunks, query_fn, **kwargs):
            return kwargs.get("query_hash", "fake_hash")

        def fake_get_batch_progress(prefix, query_hash):
            if prefix == "resource":
                return base_progress or {}
            if prefix == "resource_oee":
                return oee_progress or {}
            return {}

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 2))
        monkeypatch.setattr(engine_mod, "get_batch_progress", fake_get_batch_progress)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (1)",
            ),
        )
        monkeypatch.setattr(cache_svc, "register_spool_file", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

    def test_base_partial_failure_in_meta(self, monkeypatch):
        """Base chunk partial failure → result._meta.partial_failure.has_partial_failure == True."""
        self._make_engine_env(
            monkeypatch,
            base_progress={"has_partial_failure": "True", "failed_chunk_count": "1", "failed_ranges": "2025-01-01~2025-01-31"},
        )

        result = cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert result["_meta"]["partial_failure"]["has_partial_failure"] is True
        assert result["_meta"]["partial_failure"]["failed_ranges"] is not None

    def test_oee_partial_failure_in_meta(self, monkeypatch):
        """OEE chunk partial failure → _meta.partial_failure contains OEE failure info."""
        self._make_engine_env(
            monkeypatch,
            oee_progress={"has_partial_failure": "True", "failed_chunk_count": "1", "failed_ranges": "2025-02-01~2025-02-28"},
        )

        result = cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert result["_meta"]["partial_failure"]["has_partial_failure"] is True

    def test_no_partial_failure_no_meta_key(self, monkeypatch):
        """All chunks succeed → result._meta has no partial_failure key."""
        self._make_engine_env(monkeypatch)

        result = cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert "partial_failure" not in result.get("_meta", {})

    def test_partial_failure_warning_logged(self, monkeypatch, caplog):
        """Partial failure → logger.warning is emitted."""
        import logging
        self._make_engine_env(
            monkeypatch,
            base_progress={"has_partial_failure": "True", "failed_chunk_count": "1", "failed_ranges": "2025-01-01~2025-01-31"},
        )

        with caplog.at_level(logging.WARNING, logger="mes_dashboard.resource_dataset_cache"):
            cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert any("partial failure" in r.message.lower() for r in caplog.records)
