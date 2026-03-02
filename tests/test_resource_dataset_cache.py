# -*- coding: utf-8 -*-
"""Unit tests for resource_dataset_cache — engine integration (task 7.4)."""

from __future__ import annotations

import pandas as pd

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

        def fake_merge_chunks(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return result_df

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks", fake_merge_chunks)
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
