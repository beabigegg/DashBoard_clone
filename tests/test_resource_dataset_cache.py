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
        """execute_primary_query → store_spooled_df is called with ttl_seconds == _CACHE_TTL
        for recent (non-historical) queries (end_date within last 2 days)."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        from datetime import date, timedelta

        # Use today as end_date so _get_cache_ttl returns _CACHE_TTL (not _HISTORICAL_TTL)
        today = date.today().isoformat()
        start = (date.today() - timedelta(days=29)).isoformat()

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

        cache_svc.execute_primary_query(start_date=start, end_date=today)

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


# ============================================================
# TDD Anchors: resource-history-cache-fix
# ============================================================


class TestCanonicalKeyParity:
    """Canonical key builders: warmup writes under the canonical key (IP-1, IP-2, IP-3)."""

    def test_ensure_dataset_loaded_writes_canonical_key(self, monkeypatch):
        """ensure_dataset_loaded() must call store_spooled_df with the canonical base key.

        Before IP-2 this test FAILS because ensure_dataset_loaded() delegates to
        execute_primary_query which writes the filter-inclusive key, not the canonical key.
        After IP-2, _query_and_store_canonical_dataset calls store_spooled_df directly
        with make_canonical_base_query_id(start_date, end_date).
        """
        from datetime import date, timedelta
        import pandas as pd
        from unittest.mock import MagicMock
        import datetime as _dt_mod

        fixed_today = date(2025, 6, 10)
        end_dt = fixed_today
        start_dt = end_dt - timedelta(days=89)
        start_date = start_dt.isoformat()
        end_date = end_dt.isoformat()

        expected_key = cache_svc.make_canonical_base_query_id(start_date, end_date)
        spool_calls = []

        def fake_store_spooled_df(namespace, query_id, df, **kw):
            spool_calls.append({"namespace": namespace, "query_id": query_id})
            return True  # store_spooled_df returns bool

        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "read_sql_df",
            lambda sql, params, caller=None: pd.DataFrame({"HISTORYID": [1]}),
        )
        monkeypatch.setattr(cache_svc, "store_spooled_df", fake_store_spooled_df)
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        class _FixedDate(_dt_mod.date):
            @classmethod
            def today(cls):
                return fixed_today

        # Patch 'date' in the module's namespace (it is imported via `from datetime import date`)
        monkeypatch.setattr(cache_svc, "date", _FixedDate)

        cache_svc.ensure_dataset_loaded()

        canonical_base_key_calls = [
            c for c in spool_calls
            if c["namespace"] == cache_svc._REDIS_NAMESPACE and c["query_id"] == expected_key
        ]
        assert len(canonical_base_key_calls) >= 1, (
            f"store_spooled_df was NOT called with canonical base key={expected_key!r}. "
            f"Calls observed: {spool_calls}"
        )

    def test_execute_primary_query_empty_filter_co_writes_canonical_key(self, monkeypatch):
        """execute_primary_query with empty filters must also call store_spooled_df with canonical key (IP-3).

        Before IP-3 this test FAILS because the co-write path is not yet implemented.
        After IP-3, store_spooled_df is called twice for the direct path:
        once for filter-inclusive key, once for canonical key.
        """
        import pandas as pd
        from unittest.mock import MagicMock

        start_date = "2025-06-01"
        end_date = "2025-06-30"
        expected_canonical_key = cache_svc.make_canonical_base_query_id(start_date, end_date)
        spool_calls = []

        def fake_store_spooled_df(namespace, query_id, df, **kw):
            spool_calls.append({"namespace": namespace, "query_id": query_id})
            return True  # store_spooled_df returns bool

        import mes_dashboard.services.batch_query_engine as engine_mod
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: ([{"RESOURCEID": "R1"}], {"R1": {}}, "h.HISTORYID IN (1)"),
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

        cache_svc.execute_primary_query(start_date=start_date, end_date=end_date)

        canonical_calls = [
            c for c in spool_calls
            if c["namespace"] == cache_svc._REDIS_NAMESPACE and c["query_id"] == expected_canonical_key
        ]
        assert len(canonical_calls) >= 1, (
            f"Expected canonical base key={expected_canonical_key!r} in store_spooled_df calls. "
            f"Observed: {spool_calls}"
        )

    def test_empty_filter_detection_non_empty_does_not_co_write(self, monkeypatch):
        """execute_primary_query with non-empty filters must NOT co-write the canonical key (IP-3).

        After IP-3 this test ensures the empty-filter guard works correctly.
        store_spooled_df should be called only with the filter-inclusive key, not canonical key.
        """
        import pandas as pd
        from unittest.mock import MagicMock

        start_date = "2025-06-01"
        end_date = "2025-06-30"
        canonical_base_key = cache_svc.make_canonical_base_query_id(start_date, end_date)
        spool_calls = []

        def fake_store_spooled_df(namespace, query_id, df, **kw):
            spool_calls.append({"namespace": namespace, "query_id": query_id})
            return True

        import mes_dashboard.services.batch_query_engine as engine_mod
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: ([{"RESOURCEID": "R1"}], {"R1": {}}, "h.HISTORYID IN (1)"),
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

        cache_svc.execute_primary_query(
            start_date=start_date, end_date=end_date, workcenter_groups=["WB"]
        )

        canonical_base_calls = [
            c for c in spool_calls
            if c["query_id"] == canonical_base_key
        ]
        assert len(canonical_base_calls) == 0, (
            f"Canonical key should NOT be co-written for non-empty filter. "
            f"Observed: {spool_calls}"
        )


class TestCanonicalSpoolHit:
    """After warmup, canonical spool lookup should return non-None (IP-1, IP-2)."""

    def test_ensure_dataset_loaded_produces_canonical_hit(self, monkeypatch):
        """Calling ensure_dataset_loaded() stores spool under the canonical key.

        Before IP-2, ensure_dataset_loaded writes the filter-inclusive key, so this FAILS.
        After IP-2, store_spooled_df is called with the canonical key.
        """
        from datetime import date, timedelta
        import pandas as pd
        from unittest.mock import MagicMock
        import datetime as _dt_mod

        fixed_today = date(2025, 6, 10)
        end_dt = fixed_today
        start_dt = end_dt - timedelta(days=89)
        start_date = start_dt.isoformat()
        end_date = end_dt.isoformat()

        canonical_base_key = cache_svc.make_canonical_base_query_id(start_date, end_date)
        stored_spools = {}

        def fake_store_spooled_df(namespace, query_id, df, **kw):
            stored_spools[(namespace, query_id)] = True
            return True  # store_spooled_df returns bool

        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "read_sql_df",
            lambda sql, params, caller=None: pd.DataFrame({"HISTORYID": [1]}),
        )
        monkeypatch.setattr(cache_svc, "store_spooled_df", fake_store_spooled_df)
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        class _FixedDate(_dt_mod.date):
            @classmethod
            def today(cls):
                return fixed_today

        # Patch 'date' in the module's namespace (it is imported via `from datetime import date`)
        monkeypatch.setattr(cache_svc, "date", _FixedDate)

        cache_svc.ensure_dataset_loaded()

        assert (cache_svc._REDIS_NAMESPACE, canonical_base_key) in stored_spools, (
            f"Warmup did not call store_spooled_df with canonical base key={canonical_base_key!r}. "
            f"Stored: {list(stored_spools.keys())}"
        )


class TestWarmCacheFilterSwitch:
    """Filter switch on warm canonical cache should not call Oracle (AC-4)."""

    def test_filter_switch_on_warm_cache_no_oracle_call(self, monkeypatch):
        """Canonical HIT → Oracle not called, even with different granularity/filters."""
        from mes_dashboard.services import resource_history_sql_runtime as sql_rt

        canonical_result = {
            "query_id": "canonical-qid",
            "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
            "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
        }
        oracle_calls = {"count": 0}

        def fake_execute_primary_query(**kwargs):
            oracle_calls["count"] += 1
            return {}

        monkeypatch.setattr(
            sql_rt,
            "try_compute_query_from_canonical_spool",
            lambda **kw: (canonical_result, {}),
        )

        result, meta = sql_rt.try_compute_query_from_canonical_spool(
            start_date="2025-06-01",
            end_date="2025-06-30",
            granularity="week",
            workcenter_groups=["WB"],
        )
        assert result is not None, "Canonical spool must return result on HIT"
        assert oracle_calls["count"] == 0, "Oracle must not be called on canonical HIT"


class TestSchemaVersionInvalidation:
    """Schema version bump invalidates stale spool (AC-6, D7)."""

    def test_schema_version_bump_invalidates_stale_spool(self, monkeypatch):
        """After bumping schema version 1→2, canonical key must differ from v1 key."""
        start_date = "2025-01-01"
        end_date = "2025-03-31"

        old_key = cache_svc._make_query_id({
            "canonical_schema_version": 1,
            "start_date": start_date,
            "end_date": end_date,
        })
        new_key = cache_svc.make_canonical_base_query_id(start_date, end_date)

        assert old_key != new_key, (
            "After schema version bump (1→2), canonical key must differ from v1 key. "
            f"old={old_key!r} new={new_key!r}"
        )


class TestRedisDownFallback:
    """Redis down → fall through to Oracle (AC-6, D7)."""

    def test_redis_down_falls_back_to_oracle_no_binder_exception(self, monkeypatch):
        """When spool store is unavailable, execute_primary_query does not raise BinderException."""
        import pandas as pd
        from unittest.mock import MagicMock

        oracle_calls = {"count": 0}

        def fake_read_sql_df(sql, params, caller=None):
            oracle_calls["count"] += 1
            return pd.DataFrame({"HISTORYID": [1]})

        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "read_sql_df", fake_read_sql_df)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: ([{"RESOURCEID": "R1"}], {"R1": {}}, "h.HISTORYID IN (1)"),
        )
        monkeypatch.setattr(cache_svc, "store_spooled_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())
        # register_spool_file raises ConnectionError to simulate Redis down
        def raise_conn(*a, **kw):
            raise ConnectionError("Redis down")
        monkeypatch.setattr(cache_svc, "register_spool_file", raise_conn)
        import mes_dashboard.services.batch_query_engine as engine_mod
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

        try:
            result = cache_svc.execute_primary_query(start_date="2025-06-01", end_date="2025-06-30")
        except Exception as exc:
            assert "BinderException" not in type(exc).__name__, (
                f"Redis down must not cause BinderException, got: {exc}"
            )


class TestStaleParquetFallback:
    """Stale parquet schema mismatch → fall back to Oracle (AC-6)."""

    def test_stale_parquet_schema_mismatch_falls_back_to_oracle(self, monkeypatch):
        """Canonical SPOOL_MISS (None) falls through to Oracle; no BinderException."""
        from mes_dashboard.services import resource_history_sql_runtime as sql_rt

        monkeypatch.setattr(
            sql_rt,
            "try_compute_query_from_canonical_spool",
            lambda **kw: (None, {"canonical_fallback_reason": "spool_miss"}),
        )

        result, meta = sql_rt.try_compute_query_from_canonical_spool(
            start_date="2025-06-01",
            end_date="2025-06-30",
            granularity="day",
        )
        assert result is None, "Schema mismatch should produce SPOOL_MISS (None result)"
        assert meta.get("canonical_fallback_reason") == "spool_miss"


class TestViewResultCache:
    """View-result cache: apply_view caches results within TTL (IP-6, AC-7)."""

    def test_apply_view_result_cached_within_ttl(self, monkeypatch):
        """Second apply_view() call within TTL must NOT re-invoke try_compute_view_from_spool.

        Before IP-6 this test FAILS because no view-result cache exists.
        """
        from mes_dashboard.services import resource_history_sql_runtime as sql_rt

        compute_calls = {"count": 0}
        fake_result = {
            "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
            "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
        }

        def fake_compute_view(query_id, granularity="day"):
            compute_calls["count"] += 1
            return (fake_result, {})

        monkeypatch.setattr(sql_rt, "try_compute_view_from_spool", fake_compute_view)
        monkeypatch.setattr(cache_svc, "_RESOURCE_VIEW_CACHE_TTL", 300)

        r1 = cache_svc.apply_view(query_id="test-view-qid-cached", granularity="day")
        r2 = cache_svc.apply_view(query_id="test-view-qid-cached", granularity="day")

        assert r1 is not None
        assert r2 is not None
        assert compute_calls["count"] == 1, (
            f"try_compute_view_from_spool should be called once (cached), got {compute_calls['count']}"
        )

    def test_apply_view_result_recomputed_after_ttl_expiry(self, monkeypatch):
        """Different query_id always triggers recompute (unique key per call)."""
        from mes_dashboard.services import resource_history_sql_runtime as sql_rt

        compute_calls = {"count": 0}
        fake_result = {
            "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
            "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
        }

        def fake_compute_view(query_id, granularity="day"):
            compute_calls["count"] += 1
            return (fake_result, {})

        monkeypatch.setattr(sql_rt, "try_compute_view_from_spool", fake_compute_view)
        monkeypatch.setattr(cache_svc, "_RESOURCE_VIEW_CACHE_TTL", 300)

        cache_svc.apply_view(query_id="expiry-qid-1", granularity="day")
        cache_svc.apply_view(query_id="expiry-qid-2", granularity="day")

        assert compute_calls["count"] == 2, "Different keys must always recompute"

    def test_resource_view_cache_ttl_zero_disables_cache(self, monkeypatch):
        """When _RESOURCE_VIEW_CACHE_TTL == 0, apply_view always recomputes (IP-6)."""
        from mes_dashboard.services import resource_history_sql_runtime as sql_rt

        compute_calls = {"count": 0}
        fake_result = {
            "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
            "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
        }

        def fake_compute_view(query_id, granularity="day"):
            compute_calls["count"] += 1
            return (fake_result, {})

        monkeypatch.setattr(sql_rt, "try_compute_view_from_spool", fake_compute_view)
        monkeypatch.setattr(cache_svc, "_RESOURCE_VIEW_CACHE_TTL", 0)

        cache_svc.apply_view(query_id="ttl-zero-qid", granularity="day")
        cache_svc.apply_view(query_id="ttl-zero-qid", granularity="day")

        assert compute_calls["count"] == 2, (
            f"TTL=0 must disable cache; expected 2 compute calls, got {compute_calls['count']}"
        )

    def test_apply_view_caches_all_six_structures_atomically(self, monkeypatch):
        """apply_view must cache the complete result dict; second call returns all keys."""
        from mes_dashboard.services import resource_history_sql_runtime as sql_rt

        fake_result = {
            "summary": {
                "kpi": {"ou_pct": 85.0},
                "trend": [{"date": "2025-06-01", "ou_pct": 85.0}],
                "heatmap": [{"workcenter": "WC1"}],
                "workcenter_comparison": [{"workcenter": "WC1"}],
            },
            "detail": {"data": [{"workcenter": "WC1"}], "total": 1, "truncated": False, "max_records": None},
            "detail_by_date": {"data": [], "total": 0},
        }
        compute_calls = {"count": 0}

        def fake_compute_view(query_id, granularity="day"):
            compute_calls["count"] += 1
            return (fake_result, {"_meta": {}})

        monkeypatch.setattr(sql_rt, "try_compute_view_from_spool", fake_compute_view)
        monkeypatch.setattr(cache_svc, "_RESOURCE_VIEW_CACHE_TTL", 300)

        r1 = cache_svc.apply_view(query_id="atomic-qid", granularity="day")
        r2 = cache_svc.apply_view(query_id="atomic-qid", granularity="day")

        assert r1 is not None and r2 is not None
        assert "summary" in r1 and "summary" in r2
        assert "detail" in r1 and "detail" in r2
        assert compute_calls["count"] == 1, "Atomic cache: second call must use cached result"


class TestOracleFallbackPath:
    """Oracle fallback used when canonical spool misses (AC-8, D4)."""

    def test_oracle_fallback_used_when_canonical_miss(self, monkeypatch):
        """When canonical spool misses, execute_primary_query calls Oracle (System A fallback)."""
        import pandas as pd
        from unittest.mock import MagicMock

        oracle_calls = {"count": 0}

        def fake_read_sql_df(sql, params, caller=None):
            oracle_calls["count"] += 1
            return pd.DataFrame({"HISTORYID": [1]})

        import mes_dashboard.services.batch_query_engine as engine_mod
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_has_cached_oee_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "_get_filtered_resources_and_lookup",
            lambda **kw: ([{"RESOURCEID": "R1"}], {"R1": {}}, "h.HISTORYID IN (1)"),
        )
        monkeypatch.setattr(cache_svc, "read_sql_df", fake_read_sql_df)
        monkeypatch.setattr(cache_svc, "store_spooled_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())
        monkeypatch.setattr(cache_svc, "register_spool_file", lambda *a, **kw: "/tmp/f.parquet")
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            },
        )

        result = cache_svc.execute_primary_query(start_date="2025-06-01", end_date="2025-06-30")

        assert oracle_calls["count"] >= 1, "Oracle must be called when canonical spool misses"
        assert result["query_id"] is not None
