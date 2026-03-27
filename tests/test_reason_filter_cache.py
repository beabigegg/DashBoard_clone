# -*- coding: utf-8 -*-
"""Unit tests for reason_filter_cache service."""

from __future__ import annotations

import pytest
import pandas as pd
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cache state before each test."""
    import mes_dashboard.services.reason_filter_cache as cache_mod
    cache_mod._CACHE["reject_reasons"] = None
    cache_mod._CACHE["loaded"] = False
    cache_mod._CACHE["updated_at"] = None
    yield
    cache_mod._CACHE["reject_reasons"] = None
    cache_mod._CACHE["loaded"] = False
    cache_mod._CACHE["updated_at"] = None


class TestInit:
    def test_init_loads_from_oracle_on_redis_miss(self):
        """init() queries Oracle when Redis has no data."""
        import mes_dashboard.services.reason_filter_cache as cache_mod

        sample_df = pd.DataFrame({"LOSSREASONNAME": ["001_CRACK", "002_BREAK"]})

        with patch.object(cache_mod, "_read_from_redis", return_value=None):
            with patch("mes_dashboard.services.reason_filter_cache.read_sql_df", return_value=sample_df):
                cache_mod.init()

        assert cache_mod._CACHE["loaded"] is True
        assert "001_CRACK" in cache_mod._CACHE["reject_reasons"]
        assert "002_BREAK" in cache_mod._CACHE["reject_reasons"]


class TestGetRejectReasons:
    def test_returns_cached_reasons(self):
        """get_reject_reasons() returns L1 cache without Oracle call."""
        import mes_dashboard.services.reason_filter_cache as cache_mod
        cache_mod._CACHE["reject_reasons"] = ["001_CRACK", "002_BREAK"]
        cache_mod._CACHE["loaded"] = True

        with patch("mes_dashboard.services.reason_filter_cache.read_sql_df") as mock_sql:
            result = cache_mod.get_reject_reasons()

        mock_sql.assert_not_called()
        assert result == ["001_CRACK", "002_BREAK"]

    def test_returns_list_copy(self):
        """get_reject_reasons() returns a copy of the cache list."""
        import mes_dashboard.services.reason_filter_cache as cache_mod
        cache_mod._CACHE["reject_reasons"] = ["001_CRACK"]
        cache_mod._CACHE["loaded"] = True

        result = cache_mod.get_reject_reasons()
        result.append("EXTRA")
        assert cache_mod._CACHE["reject_reasons"] == ["001_CRACK"]


class TestRefresh:
    def test_refresh_updates_cache(self):
        """refresh() queries Oracle and updates L1 + L2 cache."""
        import mes_dashboard.services.reason_filter_cache as cache_mod

        cache_mod._CACHE["reject_reasons"] = ["OLD"]
        cache_mod._CACHE["loaded"] = True

        sample_df = pd.DataFrame({"LOSSREASONNAME": ["NEW_001", "NEW_002"]})

        with patch("mes_dashboard.services.reason_filter_cache.read_sql_df", return_value=sample_df):
            with patch.object(cache_mod, "_write_to_redis"):
                result = cache_mod.refresh()

        assert result is True
        assert "NEW_001" in cache_mod._CACHE["reject_reasons"]
        assert "NEW_002" in cache_mod._CACHE["reject_reasons"]

    def test_refresh_fail_open_preserves_old_values(self):
        """On Oracle error during refresh, previous cached values are retained."""
        import mes_dashboard.services.reason_filter_cache as cache_mod

        cache_mod._CACHE["reject_reasons"] = ["OLD_REASON"]
        cache_mod._CACHE["loaded"] = True

        with patch("mes_dashboard.services.reason_filter_cache.read_sql_df", side_effect=Exception("DB down")):
            result = cache_mod.refresh()

        assert result is False
        assert cache_mod._CACHE["reject_reasons"] == ["OLD_REASON"]

    def test_init_fail_open_marks_loaded_with_empty(self):
        """On first-load failure, cache is marked loaded with empty list."""
        import mes_dashboard.services.reason_filter_cache as cache_mod

        with patch.object(cache_mod, "_read_from_redis", return_value=None):
            with patch("mes_dashboard.services.reason_filter_cache.read_sql_df", side_effect=Exception("DB down")):
                cache_mod.init()

        assert cache_mod._CACHE["loaded"] is True
        assert cache_mod._CACHE["reject_reasons"] == []

    def test_redis_l2_hit_skips_oracle(self):
        """When Redis has data, Oracle query is skipped."""
        import mes_dashboard.services.reason_filter_cache as cache_mod

        redis_data = {
            "reject_reasons": ["CACHED_001"],
            "updated_at": "2026-01-01T00:00:00",
        }

        with patch.object(cache_mod, "_read_from_redis", return_value=redis_data):
            with patch("mes_dashboard.services.reason_filter_cache.read_sql_df") as mock_sql:
                cache_mod.init()

        mock_sql.assert_not_called()
        assert cache_mod._CACHE["reject_reasons"] == ["CACHED_001"]
