# -*- coding: utf-8 -*-
"""Unit tests for resource_dataset_cache — engine integration (task 7.4)."""

from __future__ import annotations

import pandas as pd
from unittest.mock import MagicMock

from mes_dashboard.services import resource_dataset_cache as cache_svc


class TestResourceEngineDecomposition:
    """7.4 — resource-history with long date range triggers engine."""

    def test_long_range_triggers_engine(self, monkeypatch):
        """90-day range → engine decomposition activated."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        engine_calls = {"execute": 0, "merge": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 3  # 90 days / 31 = 3 chunks
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({
            "HISTORYID": [1, 2],
            "RESOURCEID": ["R1", "R2"],
        })

        def fake_merge_chunks_to_spool(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return ("/tmp/fake_spool.parquet", 2)

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_cached_df",
            lambda _: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._store_df",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._load_sql",
            lambda name: "SELECT 1 FROM dual",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1", "RESOURCENAME": "Machine-1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (SELECT HISTORYID FROM RESOURCEHISTORY)",
            ),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_resource_lookup",
            lambda: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_workcenter_mapping",
            lambda: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._derive_summary",
            lambda df, rl, wc, gran: {"total_hours": 100},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._derive_detail",
            lambda df, rl, wc: {"items": [], "pagination": {"total": 2}},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache.register_spool_file",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache.load_spooled_df",
            lambda *a, **kw: result_df,
        )

        result = cache_svc.execute_primary_query(
            start_date="2025-01-01",
            end_date="2025-03-31",
            workcenter_groups=["WB"],
        )

        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1
        assert result["query_id"] is not None

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        engine_calls = {"execute": 0}

        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_cached_df",
            lambda _: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._load_sql",
            lambda name: "SELECT 1 FROM dual",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache.read_sql_df",
            lambda sql, params: pd.DataFrame({"HISTORYID": [1]}),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._store_df",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_filtered_resources_and_lookup",
            lambda **kw: (
                [{"RESOURCEID": "R1"}],
                {"R1": {"RESOURCENAME": "Machine-1"}},
                "h.HISTORYID IN (SELECT HISTORYID FROM RESOURCEHISTORY)",
            ),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_resource_lookup",
            lambda: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._get_workcenter_mapping",
            lambda: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._derive_summary",
            lambda df, rl, wc, gran: {},
        )
        monkeypatch.setattr(
            "mes_dashboard.services.resource_dataset_cache._derive_detail",
            lambda df, rl, wc: {"items": [], "pagination": {"total": 1}},
        )

        result = cache_svc.execute_primary_query(
            start_date="2025-06-01",
            end_date="2025-06-30",
            workcenter_groups=["WB"],
        )

        assert engine_calls["execute"] == 0  # Engine NOT used


# ============================================================
# Phase 2: metadata-only Redis (PHASE2_METADATA_ONLY)
# ============================================================


class TestPhase2ResourceStoreDF:
    """5.3 — _store_df uses store_spooled_df when PHASE2_METADATA_ONLY=1."""

    def test_phase2_store_df_calls_store_spooled_df_not_redis(self, monkeypatch):
        """PHASE2_METADATA_ONLY=1: store_spooled_df called, _redis_store_df not called."""
        monkeypatch.setattr(cache_svc, "_PHASE2_METADATA_ONLY", True)

        spool_calls = []
        redis_calls = []

        monkeypatch.setattr(cache_svc, "store_spooled_df", lambda ns, qid, df, **kw: spool_calls.append((ns, qid)))
        monkeypatch.setattr(cache_svc, "_redis_store_df", lambda qid, df: redis_calls.append(qid))
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        df = pd.DataFrame({"HISTORYID": [1]})
        cache_svc._store_df("qid-resource-phase2", df)

        assert len(spool_calls) == 1
        assert spool_calls[0] == (cache_svc._REDIS_NAMESPACE, "qid-resource-phase2")
        assert len(redis_calls) == 0

    def test_phase2_disabled_store_df_calls_redis(self, monkeypatch):
        """PHASE2_METADATA_ONLY=0: _redis_store_df called, store_spooled_df not called."""
        monkeypatch.setattr(cache_svc, "_PHASE2_METADATA_ONLY", False)

        spool_calls = []
        redis_calls = []

        monkeypatch.setattr(cache_svc, "store_spooled_df", lambda ns, qid, df, **kw: spool_calls.append((ns, qid)))
        monkeypatch.setattr(cache_svc, "_redis_store_df", lambda qid, df: redis_calls.append(qid))
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        df = pd.DataFrame({"HISTORYID": [1]})
        cache_svc._store_df("qid-resource-phase1", df)

        assert len(redis_calls) == 1
        assert redis_calls[0] == "qid-resource-phase1"
        assert len(spool_calls) == 0

    def test_phase2_get_cached_df_spool_miss_falls_back_to_redis(self, monkeypatch):
        """Spool miss → redis_load_df attempted as fallback (Phase 2 enabled)."""
        monkeypatch.setattr(cache_svc, "_PHASE2_METADATA_ONLY", True)

        expected_df = pd.DataFrame({"HISTORYID": [99]})
        spool_calls = []
        redis_calls = []

        monkeypatch.setattr(cache_svc, "load_spooled_df", lambda ns, qid: (spool_calls.append(qid) or None))
        monkeypatch.setattr(cache_svc, "_redis_load_df", lambda qid: (redis_calls.append(qid) or expected_df))

        result = cache_svc._get_cached_df("qid-resource-spool-miss")

        assert len(spool_calls) == 1
        assert len(redis_calls) == 1
        assert result is expected_df


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
