# -*- coding: utf-8 -*-
"""Unit tests for mid_section_defect_service — engine integration (spool migration)."""

from __future__ import annotations


import pandas as pd

from mes_dashboard.services import mid_section_defect_service as msd_svc


class TestDetectionEngineDecomposition:
    """CONTAINERID-first two-step pipeline (Step A time-chunked CIDs → Step B IN-batch enrich)."""

    def test_long_range_triggers_two_step_spool(self, monkeypatch):
        """90-day range → Step A (time-chunked CIDs) → Step B (IN-batch enrich) → spool."""
        import mes_dashboard.core.query_spool_store as spool_mod

        calls = {"stepA": 0, "stepB": 0, "store": 0}

        def fake_read_sql(sql, params=None, **kwargs):
            if "SELECT DISTINCT" in sql.upper():
                calls["stepA"] += 1
                return pd.DataFrame({"CONTAINERID": ["C1", "C2"]})
            calls["stepB"] += 1
            return pd.DataFrame({
                "CONTAINERID": ["C1", "C2"],
                "WORKCENTERNAME": ["TEST-WC-A", "TEST-WC-B"],
                "REJECTQTY": [0, 0],
            })

        def fake_store_spooled_df(ns, qid, df, ttl_seconds=None):
            calls["store"] += 1
            assert ns == "msd_detect"
            assert len(df) == 2
            return True

        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda ns, qid: None)
        monkeypatch.setattr(spool_mod, "store_spooled_df", fake_store_spooled_df)
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.read_sql_df", fake_read_sql,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get", lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_set",
            lambda key, val, ttl=None: None,
        )

        df, _pf = msd_svc._fetch_station_detection_data(
            start_date="2025-01-01",
            end_date="2025-03-31",
            station="測試",
        )

        assert calls["stepA"] >= 1   # time-chunked CID resolution ran
        assert calls["stepB"] >= 1   # IN-batch enrichment ran
        assert calls["store"] == 1   # long range spools the merged result
        assert df is not None
        assert len(df) == 2
        assert "WORKCENTERNAME" in df.columns

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

    def test_two_step_path_returns_dataframe(self, monkeypatch):
        """Two-step path returns the enriched DataFrame (Step B columns preserved)."""
        import mes_dashboard.core.query_spool_store as spool_mod

        def fake_read_sql(sql, params=None, **kwargs):
            if "SELECT DISTINCT" in sql.upper():
                return pd.DataFrame({"CONTAINERID": ["C1"]})
            return pd.DataFrame({
                "CONTAINERID": ["C1"],
                "WORKCENTERNAME": ["WC"],
                "REJECTQTY": [100],
            })

        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda ns, qid: None)
        monkeypatch.setattr(spool_mod, "store_spooled_df", lambda *a, **kw: True)
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.read_sql_df", fake_read_sql,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_get", lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.mid_section_defect_service.cache_set", lambda key, val, ttl=None: None,
        )

        df, _pf = msd_svc._fetch_station_detection_data(
            start_date="2025-01-01",
            end_date="2025-03-31",
            station="測試",
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "WORKCENTERNAME" in df.columns
        assert int(df.iloc[0]["REJECTQTY"]) == 100


class TestMaskSemantics:
    """package/type as population masks; loss_reason masks numerator only (denominator
    preserved) — the read-time DuckDB layer that replaced seed-level filtering."""

    def _make_runtime(self, tmp_path):
        """Build a runtime over a synthetic detection + minimal events spool.

        Population (PJ_TYPE / PRODUCTLINENAME):
          X: input 100, reason A=10   (TYPE-A / PKG-A)
          Y: input 100, reason B=5    (TYPE-A / PKG-A)
          Z: input 100, no defect     (TYPE-A / PKG-A)
          W: input 100, reason B=5    (TYPE-B / PKG-B)
        """
        from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

        det = pd.DataFrame([
            ("X", "LOT-X", "TYPE-A", "PKG-A", 100, "A", 10),
            ("Y", "LOT-Y", "TYPE-A", "PKG-A", 100, "B", 5),
            ("Z", "LOT-Z", "TYPE-A", "PKG-A", 100, None, 0),
            ("W", "LOT-W", "TYPE-B", "PKG-B", 100, "B", 5),
        ], columns=["CONTAINERID", "CONTAINERNAME", "PJ_TYPE", "PRODUCTLINENAME",
                    "TRACKINQTY", "LOSSREASONNAME", "REJECTQTY"])
        det["TRACKINTIMESTAMP"] = "2025-01-10 10:00:00"
        det_path = tmp_path / "detection.parquet"
        det.to_parquet(det_path, index=False)

        events = pd.DataFrame([("X", "WC", 100)], columns=["CONTAINERID", "WORKCENTER_GROUP", "TRACKINQTY"])
        ev_path = tmp_path / "events.parquet"
        events.to_parquet(ev_path, index=False)

        rt = MsdDuckdbRuntime("tqid-mask-test")
        rt._events_path = str(ev_path)
        rt._lineage_path = None
        rt._detection_path = str(det_path)
        rt._resolved = True
        return rt, str(det_path)

    def test_loss_reason_does_not_shrink_denominator(self, tmp_path):
        """Filtering loss_reason=B keeps the full population in the denominator so the
        rate is NOT inflated by dropping lots that only had other-reason defects."""
        rt, det_path = self._make_runtime(tmp_path)
        summary = rt.get_summary_with_detection(det_path, loss_reasons=["B"])
        assert summary is not None
        kpi = summary["kpi"]
        # Denominator = full population (X+Y+Z+W) = 400, NOT 300 (X must stay in)
        assert kpi["total_input"] == 400
        assert kpi["lot_count"] == 4
        # Numerator = only reason B defects = Y(5) + W(5) = 10
        assert kpi["total_defect_qty"] == 10
        assert abs(kpi["total_defect_rate"] - 2.5) < 0.001

    def test_pj_type_mask_restricts_population(self, tmp_path):
        """pj_types=['TYPE-A'] restricts both numerator AND denominator to TYPE-A lots."""
        rt, det_path = self._make_runtime(tmp_path)
        summary = rt.get_summary_with_detection(det_path, pj_types=["TYPE-A"])
        assert summary is not None
        kpi = summary["kpi"]
        # Population = X,Y,Z (TYPE-A); W (TYPE-B) excluded
        assert kpi["total_input"] == 300
        assert kpi["lot_count"] == 3
        assert kpi["total_defect_qty"] == 15  # X's A(10) + Y's B(5)

    def test_pj_type_and_loss_reason_combined(self, tmp_path):
        """pj_types=['TYPE-A'] (population) + loss_reasons=['B'] (numerator)."""
        rt, det_path = self._make_runtime(tmp_path)
        summary = rt.get_summary_with_detection(det_path, pj_types=["TYPE-A"], loss_reasons=["B"])
        assert summary is not None
        kpi = summary["kpi"]
        assert kpi["total_input"] == 300        # TYPE-A population denominator
        assert kpi["total_defect_qty"] == 5     # only Y's B within TYPE-A


class TestApplyPopulationMask:
    """Phase 1: _apply_population_mask is the in-memory (forward + backward-fallback)
    equivalent of the DuckDB detection_raw pj_type/package population mask."""

    def _df(self):
        return pd.DataFrame([
            ("X", "TYPE-A", "PKG-A"),
            ("Y", "TYPE-A", "PKG-B"),
            ("W", "TYPE-B", "PKG-B"),
        ], columns=["CONTAINERID", "PJ_TYPE", "PRODUCTLINENAME"])

    def test_pj_type_mask(self):
        out = msd_svc._apply_population_mask(self._df(), pj_types=["TYPE-A"])
        assert set(out["CONTAINERID"]) == {"X", "Y"}

    def test_package_mask(self):
        out = msd_svc._apply_population_mask(self._df(), packages=["PKG-B"])
        assert set(out["CONTAINERID"]) == {"Y", "W"}

    def test_combined_mask_is_intersection(self):
        out = msd_svc._apply_population_mask(self._df(), pj_types=["TYPE-A"], packages=["PKG-B"])
        assert set(out["CONTAINERID"]) == {"Y"}

    def test_none_masks_are_noop(self):
        out = msd_svc._apply_population_mask(self._df())
        assert len(out) == 3

    def test_mask_trims_whitespace(self):
        df = pd.DataFrame([("X", " TYPE-A ", "PKG-A")],
                          columns=["CONTAINERID", "PJ_TYPE", "PRODUCTLINENAME"])
        out = msd_svc._apply_population_mask(df, pj_types=["TYPE-A"])
        assert set(out["CONTAINERID"]) == {"X"}
