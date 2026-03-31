# -*- coding: utf-8 -*-
"""Unit tests for mid_section_defect_service — engine integration (spool migration)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mes_dashboard.services import mid_section_defect_service as msd_svc


class TestDetectionEngineDecomposition:
    """Engine decomposition with spool-based merge."""

    def test_long_range_triggers_engine_spool(self, monkeypatch, tmp_path):
        """90-day range → engine decomposition → merge_chunks_to_spool → spool DataFrame."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_mod

        engine_calls = {"execute": 0, "merge_to_spool": 0, "register": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 3  # 90 days / 31 = 3 chunks
            assert kwargs.get("cache_prefix") == "msd_detect"
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({
            "CONTAINERID": ["C1", "C2"],
            "WORKCENTERNAME": ["TEST-WC-A", "TEST-WC-B"],
        })

        spool_file = tmp_path / "test_spool.parquet"
        result_df.to_parquet(spool_file, engine="pyarrow", index=False)

        def fake_merge_chunks_to_spool(prefix, qhash, spool_dir, **kwargs):
            engine_calls["merge_to_spool"] += 1
            return (spool_file, 2)

        def fake_register_spool_file(ns, qid, src, row_count, **kwargs):
            engine_calls["register"] += 1
            assert ns == "msd_detect"
            assert row_count == 2
            return True

        # load_spooled_df: first call (cache check) returns None, second returns df
        load_calls = {"count": 0}

        def fake_load_spooled_df(ns, qid):
            load_calls["count"] += 1
            if load_calls["count"] <= 1:
                return None  # cache miss
            return result_df

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(spool_mod, "register_spool_file", fake_register_spool_file)
        monkeypatch.setattr(spool_mod, "load_spooled_df", fake_load_spooled_df)
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_set",
            lambda key, val, ttl=None: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )

        df = msd_svc._fetch_station_detection_data(
            start_date="2025-01-01",
            end_date="2025-03-31",
            station="測試",
        )

        assert engine_calls["execute"] == 1
        assert engine_calls["merge_to_spool"] == 1
        assert engine_calls["register"] == 1
        assert df is not None
        assert len(df) == 2

    def test_spool_cache_hit_skips_engine(self, monkeypatch):
        """Spool cache hit → returns cached DataFrame without engine execution."""
        import mes_dashboard.core.query_spool_store as spool_mod

        cached_df = pd.DataFrame({
            "CONTAINERID": ["C-CACHED"],
            "WORKCENTERNAME": ["WC-1"],
        })

        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda ns, qid: cached_df)
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_set",
            lambda key, val, ttl=None: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )

        query_calls = {"sql": 0}

        def fail_sql(*args, **kwargs):
            query_calls["sql"] += 1
            raise RuntimeError("Should not reach Oracle")

        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.read_sql_df",
            fail_sql,
        )

        df, _pf = msd_svc._fetch_station_detection_data(
            start_date="2025-01-01",
            end_date="2025-03-31",
            station="測試",
        )

        assert query_calls["sql"] == 0
        assert df is not None
        assert len(df) == 1
        assert df.iloc[0]["CONTAINERID"] == "C-CACHED"

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        import mes_dashboard.core.query_spool_store as spool_mod

        spool_calls = []

        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_set",
            lambda key, val, ttl=None: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.read_sql_df",
            lambda sql, params: pd.DataFrame({"CONTAINERID": ["C1"]}),
        )
        monkeypatch.setattr(
            spool_mod,
            "store_spooled_df",
            lambda ns, qid, df, ttl_seconds=None: spool_calls.append((ns, qid, len(df))) or True,
        )

        df, _pf = msd_svc._fetch_station_detection_data(
            start_date="2025-06-01",
            end_date="2025-06-05",
            station="測試",
        )

        assert df is not None
        assert len(df) == 1
        assert spool_calls == [("msd_detect", msd_svc._make_detection_spool_query_id("2025-06-01", "2025-06-05", "測試"), 1)]

    def test_short_range_cached_records_restores_dataframe_without_engine(self, monkeypatch):
        """Redis cache hit on short range should still return the cached rows."""
        import mes_dashboard.core.query_spool_store as spool_mod

        spool_calls = []
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get",
            lambda key: [{"CONTAINERID": "C1", "CONTAINERNAME": "LOT-1"}],
        )
        monkeypatch.setattr(
            spool_mod,
            "store_spooled_df",
            lambda ns, qid, df, ttl_seconds=None: spool_calls.append((ns, qid, len(df))) or True,
        )

        df, _pf = msd_svc._fetch_station_detection_data(
            start_date="2025-06-01",
            end_date="2025-06-05",
            station="測試",
        )

        assert df is not None
        assert len(df) == 1
        assert df.iloc[0]["CONTAINERID"] == "C1"
        assert spool_calls == [("msd_detect", msd_svc._make_detection_spool_query_id("2025-06-01", "2025-06-05", "測試"), 1)]

    def test_engine_path_returns_dataframe(self, monkeypatch, tmp_path):
        """Engine path returns DataFrame (same interface as before migration)."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_mod

        result_df = pd.DataFrame({
            "CONTAINERID": ["C1"],
            "WORKCENTERNAME": ["WC"],
            "TOTAL_QTY": [100],
        })

        monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: None)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: (tmp_path / "x.parquet", 1))
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: True)
        # First load returns None (cache miss), second returns df
        loads = {"n": 0}

        def fake_load(ns, qid):
            loads["n"] += 1
            return None if loads["n"] <= 1 else result_df

        monkeypatch.setattr(spool_mod, "load_spooled_df", fake_load)
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get", lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_set", lambda key, val, ttl=None: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )

        df, _pf = msd_svc._fetch_station_detection_data(
            start_date="2025-01-01",
            end_date="2025-03-31",
            station="測試",
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "TOTAL_QTY" in df.columns
