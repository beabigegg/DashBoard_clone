# -*- coding: utf-8 -*-
"""Unit tests for mid_section_defect_service — engine integration (task 8.4)."""

from __future__ import annotations

import pandas as pd

from mes_dashboard.services import mid_section_defect_service as msd_svc


class TestDetectionEngineDecomposition:
    """8.4 — large date range + high-volume station → engine decomposition."""

    def test_long_range_triggers_engine(self, monkeypatch):
        """90-day range → engine decomposition for detection query."""
        import mes_dashboard.services.batch_query_engine as engine_mod

        engine_calls = {"execute": 0, "merge": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 3  # 90 days / 31 = 3 chunks
            assert kwargs.get("cache_prefix") == "msd_detect"
            return kwargs.get("query_hash", "fake_hash")

        result_df = pd.DataFrame({
            "CONTAINERID": ["C1", "C2"],
            "WORKCENTERNAME": ["TEST-WC-A", "TEST-WC-B"],
        })

        def fake_merge_chunks(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return result_df

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks", fake_merge_chunks)
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
        assert engine_calls["merge"] == 1
        assert df is not None
        assert len(df) == 2

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        engine_calls = {"execute": 0}

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

        df = msd_svc._fetch_station_detection_data(
            start_date="2025-06-01",
            end_date="2025-06-30",
            station="測試",
        )

        assert engine_calls["execute"] == 0  # Engine NOT used
        assert df is not None
        assert len(df) == 1
