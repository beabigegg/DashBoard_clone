# -*- coding: utf-8 -*-
"""Unit tests for job_query_service — engine integration (tasks 9.1-9.4)."""

from __future__ import annotations

import pandas as pd

from mes_dashboard.services import job_query_service as job_svc


class TestJobQueryEngineDecomposition:
    """9.4 — full-year query with many resources → engine decomposition."""

    def test_long_range_triggers_engine(self, monkeypatch):
        """90-day range → engine decomposition for job query."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.redis_df_store as rds

        engine_calls = {"execute": 0, "merge": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 3  # 90 days / 31 = 3 chunks
            assert kwargs.get("cache_prefix") == "job"
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({
            "JOBID": ["J1", "J2"],
            "RESOURCEID": ["R1", "R2"],
        })

        def fake_merge_chunks(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return result_df

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks", fake_merge_chunks)
        monkeypatch.setattr(rds, "redis_load_df", lambda key: None)
        monkeypatch.setattr(rds, "redis_store_df", lambda key, df, ttl=None: None)
        monkeypatch.setattr(
            "mes_dashboard.services.job_query_service.SQLLoader",
            type("FakeLoader", (), {
                "load": staticmethod(lambda name: "SELECT 1 FROM dual WHERE {{ RESOURCE_FILTER }}"),
            }),
        )

        result = job_svc.get_jobs_by_resources(
            resource_ids=["R1", "R2", "R3"],
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1
        assert result["total"] == 2
        assert "error" not in result

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        import mes_dashboard.core.redis_df_store as rds

        engine_calls = {"execute": 0}

        monkeypatch.setattr(rds, "redis_load_df", lambda key: None)
        monkeypatch.setattr(rds, "redis_store_df", lambda key, df, ttl=None: None)
        monkeypatch.setattr(
            "mes_dashboard.services.job_query_service.SQLLoader",
            type("FakeLoader", (), {
                "load": staticmethod(lambda name: "SELECT 1 FROM dual WHERE {{ RESOURCE_FILTER }}"),
            }),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.job_query_service.read_sql_df",
            lambda sql, params: pd.DataFrame({"JOBID": ["J1"]}),
        )

        result = job_svc.get_jobs_by_resources(
            resource_ids=["R1"],
            start_date="2025-06-01",
            end_date="2025-06-05",
        )

        assert engine_calls["execute"] == 0  # Engine NOT used
        assert result["total"] == 1

    def test_redis_cache_hit_skips_query(self, monkeypatch):
        """Redis cache hit → returns cached DataFrame without Oracle query."""
        import mes_dashboard.core.redis_df_store as rds

        query_calls = {"sql": 0}

        cached_df = pd.DataFrame({
            "JOBID": ["J-CACHED"],
            "RESOURCEID": ["R1"],
        })

        monkeypatch.setattr(rds, "redis_load_df", lambda key: cached_df)

        def fail_sql(*args, **kwargs):
            query_calls["sql"] += 1
            raise RuntimeError("Should not reach Oracle")

        monkeypatch.setattr(
            "mes_dashboard.services.job_query_service.read_sql_df",
            fail_sql,
        )

        result = job_svc.get_jobs_by_resources(
            resource_ids=["R1"],
            start_date="2025-06-01",
            end_date="2025-06-30",
        )

        assert query_calls["sql"] == 0  # Oracle NOT called
        assert result["total"] == 1
        assert result["data"][0]["JOBID"] == "J-CACHED"
