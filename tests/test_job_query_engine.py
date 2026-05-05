# -*- coding: utf-8 -*-
"""Unit tests for job_query_service — engine integration (spool migration)."""

from __future__ import annotations


import pandas as pd

from mes_dashboard.services import job_query_service as job_svc


class TestJobQueryEngineDecomposition:
    """Engine decomposition with spool-based merge."""

    def test_long_range_triggers_engine_spool(self, monkeypatch, tmp_path):
        """90-day range → engine decomposition → merge_chunks_to_spool → spool records."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_mod

        engine_calls = {"execute": 0, "merge_to_spool": 0, "register": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 3  # 90 days / 31 = 3 chunks
            assert kwargs.get("cache_prefix") == "job"
            return kwargs.get("query_hash", "fake_hash")

        spool_file = tmp_path / "test_spool.parquet"
        result_df = pd.DataFrame({
            "JOBID": ["J1", "J2"],
            "RESOURCEID": ["R1", "R2"],
        })
        result_df.to_parquet(spool_file, engine="pyarrow", index=False)

        def fake_merge_chunks_to_spool(prefix, qhash, spool_dir, **kwargs):
            engine_calls["merge_to_spool"] += 1
            return (spool_file, 2)

        def fake_register_spool_file(ns, qid, src, row_count, **kwargs):
            engine_calls["register"] += 1
            assert ns == "job_query"
            assert row_count == 2
            return True

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(spool_mod, "register_spool_file", fake_register_spool_file)
        # First read_spool_records call (cache check) returns None, second returns records
        read_calls = {"count": 0}

        def fake_read_spool_records(ns, qid):
            read_calls["count"] += 1
            if read_calls["count"] == 1:
                return None  # cache miss
            return [
                {"JOBID": "J1", "RESOURCEID": "R1"},
                {"JOBID": "J2", "RESOURCEID": "R2"},
            ]

        monkeypatch.setattr(spool_mod, "read_spool_records", fake_read_spool_records)
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
        assert engine_calls["merge_to_spool"] == 1
        assert engine_calls["register"] == 1
        assert result["total"] == 2
        assert "error" not in result

    def test_spool_cache_hit_skips_engine(self, monkeypatch):
        """Spool cache hit → returns cached records without Oracle query."""
        import mes_dashboard.core.query_spool_store as spool_mod

        cached_records = [
            {"JOBID": "J-CACHED", "RESOURCEID": "R1"},
        ]
        monkeypatch.setattr(spool_mod, "read_spool_records", lambda ns, qid: cached_records)

        query_calls = {"sql": 0}

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

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        import mes_dashboard.core.query_spool_store as spool_mod

        monkeypatch.setattr(spool_mod, "read_spool_records", lambda ns, qid: None)
        monkeypatch.setattr(spool_mod, "store_spooled_df", lambda ns, qid, df, **kw: True)
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

        assert result["total"] == 1

    def test_engine_result_format_preserved(self, monkeypatch):
        """Engine path records preserve datetime formatting and None handling."""
        import mes_dashboard.core.query_spool_store as spool_mod

        records = [
            {"JOBID": "J1", "CREATEDATE": "2025-01-15 10:30:00", "COMMENTS": None},
        ]
        monkeypatch.setattr(spool_mod, "read_spool_records", lambda ns, qid: records)

        result = job_svc.get_jobs_by_resources(
            resource_ids=["R1"],
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        assert result["data"][0]["CREATEDATE"] == "2025-01-15 10:30:00"
        assert result["data"][0]["COMMENTS"] is None
