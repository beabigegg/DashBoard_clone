# -*- coding: utf-8 -*-
"""Unit tests for query_tool_service — slow-query migration + caching (tasks 10.1-10.5)."""

from __future__ import annotations


import pandas as pd

from mes_dashboard.services import query_tool_service as qt_svc


class TestSlowQueryMigration:
    """10.2 — verify high-risk read_sql_df paths migrated to read_sql_df_slow."""

    def test_resolve_by_lot_id_uses_slow(self, monkeypatch):
        """_resolve_by_lot_id should call read_sql_df_slow, not read_sql_df."""
        calls = {"slow": 0, "fast": 0}

        def fake_slow(sql, params=None, **kw):
            calls["slow"] += 1
            return pd.DataFrame({"CONTAINERID": ["C1"], "CONTAINERNAME": ["LOT-1"]})

        def fake_fast(sql, params=None):
            calls["fast"] += 1
            return pd.DataFrame()

        monkeypatch.setattr(qt_svc, "read_sql_df_slow", fake_slow)
        monkeypatch.setattr(qt_svc, "read_sql_df", fake_fast)
        monkeypatch.setattr(qt_svc, "SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )

        result = qt_svc._resolve_by_lot_id(["LOT-1"])

        assert calls["slow"] == 1
        assert calls["fast"] == 0

    def test_resolve_by_work_order_uses_slow(self, monkeypatch):
        """_resolve_by_work_order should call read_sql_df_slow."""
        calls = {"slow": 0, "fast": 0}

        def fake_slow(sql, params=None, **kw):
            calls["slow"] += 1
            return pd.DataFrame({
                "CONTAINERID": ["C1"],
                "CONTAINERNAME": ["LOT-1"],
                "MFGORDERNAME": ["GA25010101"],
            })

        def fake_fast(sql, params=None):
            calls["fast"] += 1
            return pd.DataFrame()

        monkeypatch.setattr(qt_svc, "read_sql_df_slow", fake_slow)
        monkeypatch.setattr(qt_svc, "read_sql_df", fake_fast)
        monkeypatch.setattr(qt_svc, "SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )

        result = qt_svc._resolve_by_work_order(["GA25010101"])

        assert calls["slow"] >= 1
        assert calls["fast"] == 0

    def test_equipment_status_hours_uses_slow(self, monkeypatch):
        """get_equipment_status_hours should call read_sql_df_slow."""
        import mes_dashboard.core.redis_df_store as rds

        calls = {"slow": 0, "fast": 0}

        def fake_slow(sql, params=None, **kw):
            calls["slow"] += 1
            return pd.DataFrame({
                "RESOURCEID": ["EQ1"],
                "PRD_HOURS": [100.0],
                "SBY_HOURS": [20.0],
                "UDT_HOURS": [10.0],
                "SDT_HOURS": [5.0],
                "EGT_HOURS": [3.0],
                "NST_HOURS": [2.0],
                "TOTAL_HOURS": [140.0],
            })

        def fake_fast(sql, params=None):
            calls["fast"] += 1
            return pd.DataFrame()

        monkeypatch.setattr(qt_svc, "read_sql_df_slow", fake_slow)
        monkeypatch.setattr(qt_svc, "read_sql_df", fake_fast)
        monkeypatch.setattr(rds, "redis_load_df", lambda key: None)
        monkeypatch.setattr(rds, "redis_store_df", lambda key, df, ttl=None: None)
        monkeypatch.setattr(qt_svc, "SQLLoader",
            type("FakeLoader", (), {
                "load_with_params": staticmethod(lambda name, **kw: "SELECT 1 FROM dual"),
            }),
        )

        result = qt_svc.get_equipment_status_hours(
            equipment_ids=["EQ1"],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        assert calls["slow"] == 1
        assert calls["fast"] == 0
        assert "error" not in result
        assert result["totals"]["PRD_HOURS"] == 100.0


class TestEquipmentCaching:
    """10.4/10.5 — equipment query caching via Redis."""

    def test_equipment_status_cache_hit(self, monkeypatch):
        """Spool cache hit → returns cached result without Oracle query."""
        import mes_dashboard.core.query_spool_store as spool_store

        calls = {"sql": 0}

        cached_df = pd.DataFrame({
            "RESOURCEID": ["EQ-CACHED"],
            "PRD_HOURS": [50.0],
            "SBY_HOURS": [10.0],
            "UDT_HOURS": [5.0],
            "SDT_HOURS": [2.0],
            "EGT_HOURS": [1.0],
            "NST_HOURS": [0.0],
            "TOTAL_HOURS": [68.0],
        })

        monkeypatch.setattr(spool_store, "load_spooled_df", lambda ns, key: cached_df)

        def fail_sql(*args, **kwargs):
            calls["sql"] += 1
            raise RuntimeError("Should not reach Oracle")

        monkeypatch.setattr(qt_svc, "read_sql_df_slow", fail_sql)
        monkeypatch.setattr(qt_svc, "read_sql_df", fail_sql)

        result = qt_svc.get_equipment_status_hours(
            equipment_ids=["EQ1"],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        assert calls["sql"] == 0  # Oracle NOT called
        assert result["data"][0]["RESOURCEID"] == "EQ-CACHED"
