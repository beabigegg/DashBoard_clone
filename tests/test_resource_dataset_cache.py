# -*- coding: utf-8 -*-
"""Unit tests for resource_dataset_cache — engine integration and DuckDB paths."""

from __future__ import annotations

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
        monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
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

        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1
        assert result["query_id"] is not None

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        engine_calls = {"execute": 0}

        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "read_sql_df",
            lambda sql, params, caller=None: pd.DataFrame({"HISTORYID": [1]}),
        )
        monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
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
