# -*- coding: utf-8 -*-
"""Unit tests for container_filter_cache service."""

from __future__ import annotations

import pytest
import pandas as pd
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cache state before each test."""
    import mes_dashboard.services.container_filter_cache as cache_mod
    cache_mod._CACHE["packages"] = None
    cache_mod._CACHE["pj_types"] = None
    cache_mod._CACHE["loaded"] = False
    cache_mod._CACHE["updated_at"] = None
    yield
    cache_mod._CACHE["packages"] = None
    cache_mod._CACHE["pj_types"] = None
    cache_mod._CACHE["loaded"] = False
    cache_mod._CACHE["updated_at"] = None


class TestInit:
    def test_init_calls_load(self):
        """init() triggers Oracle query when Redis miss."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        sample_df = pd.DataFrame({
            "KIND": ["PACKAGE", "PACKAGE", "PJ_TYPE", "PJ_TYPE"],
            "VALUE": ["PKG_A", "PKG_B", "TYPE_X", "TYPE_Y"],
        })

        with patch.object(cache_mod, "_read_from_redis", return_value=None):
            with patch("mes_dashboard.services.container_filter_cache.read_sql_df", return_value=sample_df):
                cache_mod.init()

        assert cache_mod._CACHE["loaded"] is True
        assert sorted(cache_mod._CACHE["packages"]) == ["PKG_A", "PKG_B"]
        assert sorted(cache_mod._CACHE["pj_types"]) == ["TYPE_X", "TYPE_Y"]


class TestGetPackages:
    def test_returns_cached_packages(self):
        """get_packages() returns L1 cache without Oracle call."""
        import mes_dashboard.services.container_filter_cache as cache_mod
        cache_mod._CACHE["packages"] = ["PKG_A", "PKG_B"]
        cache_mod._CACHE["loaded"] = True

        with patch("mes_dashboard.services.container_filter_cache.read_sql_df") as mock_sql:
            result = cache_mod.get_packages()

        mock_sql.assert_not_called()
        assert result == ["PKG_A", "PKG_B"]

    def test_returns_list_copy(self):
        """get_packages() returns a copy, not the internal reference."""
        import mes_dashboard.services.container_filter_cache as cache_mod
        cache_mod._CACHE["packages"] = ["PKG_A"]
        cache_mod._CACHE["loaded"] = True

        result = cache_mod.get_packages()
        result.append("EXTRA")
        assert cache_mod._CACHE["packages"] == ["PKG_A"]


class TestGetPjTypes:
    def test_returns_cached_pj_types(self):
        """get_pj_types() returns L1 cache without Oracle call."""
        import mes_dashboard.services.container_filter_cache as cache_mod
        cache_mod._CACHE["pj_types"] = ["TYPE_X"]
        cache_mod._CACHE["loaded"] = True

        with patch("mes_dashboard.services.container_filter_cache.read_sql_df") as mock_sql:
            result = cache_mod.get_pj_types()

        mock_sql.assert_not_called()
        assert result == ["TYPE_X"]


class TestRefresh:
    def test_refresh_queries_oracle_and_updates_l1(self):
        """refresh() forces Oracle re-query and updates L1 cache."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        # Pre-load old values
        cache_mod._CACHE["packages"] = ["OLD_PKG"]
        cache_mod._CACHE["pj_types"] = ["OLD_TYPE"]
        cache_mod._CACHE["loaded"] = True

        sample_df = pd.DataFrame({
            "KIND": ["PACKAGE", "PJ_TYPE"],
            "VALUE": ["NEW_PKG", "NEW_TYPE"],
        })

        with patch("mes_dashboard.services.container_filter_cache.read_sql_df", return_value=sample_df):
            with patch.object(cache_mod, "_write_to_redis"):
                result = cache_mod.refresh()

        assert result is True
        assert cache_mod._CACHE["packages"] == ["NEW_PKG"]
        assert cache_mod._CACHE["pj_types"] == ["NEW_TYPE"]

    def test_refresh_fail_open_preserves_old_values(self):
        """refresh() fails open: on Oracle error, previous values are retained."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        old_packages = ["OLD_PKG"]
        old_pj_types = ["OLD_TYPE"]
        cache_mod._CACHE["packages"] = old_packages[:]
        cache_mod._CACHE["pj_types"] = old_pj_types[:]
        cache_mod._CACHE["loaded"] = True

        with patch("mes_dashboard.services.container_filter_cache.read_sql_df", side_effect=Exception("Oracle down")):
            result = cache_mod.refresh()

        assert result is False
        # Old values preserved (fail-open)
        assert cache_mod._CACHE["packages"] == old_packages

    def test_redis_l2_hit_skips_oracle(self):
        """When Redis has data, Oracle is not queried."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        redis_data = {
            "packages": ["R_PKG"],
            "pj_types": ["R_TYPE"],
            "updated_at": "2026-01-01T00:00:00",
        }

        with patch.object(cache_mod, "_read_from_redis", return_value=redis_data):
            with patch("mes_dashboard.services.container_filter_cache.read_sql_df") as mock_sql:
                cache_mod.init()

        mock_sql.assert_not_called()
        assert cache_mod._CACHE["packages"] == ["R_PKG"]
        assert cache_mod._CACHE["pj_types"] == ["R_TYPE"]
