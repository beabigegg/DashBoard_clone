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

    def _reset() -> None:
        cache_mod._CACHE["schema_version"] = None
        cache_mod._CACHE["tuples"] = None
        cache_mod._CACHE["indices"] = None
        cache_mod._CACHE["updated_at"] = None
        cache_mod._CACHE["packages"] = None
        cache_mod._CACHE["pj_types"] = None
        cache_mod._CACHE["loaded"] = False

    _reset()
    # Also drop any stale lock file from a previous failed test.
    try:
        cache_mod._LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    yield
    _reset()
    try:
        cache_mod._LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _sample_tuple_df() -> pd.DataFrame:
    return pd.DataFrame({
        "PJ_TYPE":        ["TYPE_X", "TYPE_X", "TYPE_Y", "TYPE_Y"],
        "PRODUCTLINENAME": ["PKG_A", "PKG_B", "PKG_A", "PKG_B"],
        "PJ_BOP":         ["BOP_1", "BOP_2", "BOP_1", "BOP_3"],
        "PJ_FUNCTION":    ["FN_1",  "FN_2",  None,    "FN_2"],
    })


class TestInit:
    def test_init_calls_load(self):
        """init() triggers Oracle query when Redis miss."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        with patch.object(cache_mod, "_read_from_redis", return_value=None):
            with patch(
                "mes_dashboard.services.container_filter_cache.read_sql_df",
                return_value=_sample_tuple_df(),
            ):
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

        cache_mod._CACHE["packages"] = ["OLD_PKG"]
        cache_mod._CACHE["pj_types"] = ["OLD_TYPE"]
        cache_mod._CACHE["loaded"] = True

        new_df = pd.DataFrame({
            "PJ_TYPE": ["NEW_TYPE"],
            "PRODUCTLINENAME": ["NEW_PKG"],
            "PJ_BOP": ["NEW_BOP"],
            "PJ_FUNCTION": ["NEW_FN"],
        })

        with patch("mes_dashboard.services.container_filter_cache.read_sql_df", return_value=new_df):
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
        assert cache_mod._CACHE["packages"] == old_packages

    def test_redis_l2_hit_skips_oracle(self):
        """When Redis has v2 payload, Oracle is not queried."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        redis_data = {
            "schema_version": 2,
            "tuples": [["TYPE_R", "R_PKG", "R_BOP", "R_FN"]],
            "indices": {
                "pj_types": ["TYPE_R"],
                "packages": ["R_PKG"],
                "bops": ["R_BOP"],
                "pj_functions": ["R_FN"],
            },
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

        with patch.object(cache_mod, "_read_from_redis", return_value=redis_data):
            with patch("mes_dashboard.services.container_filter_cache.read_sql_df") as mock_sql:
                cache_mod.init()

        mock_sql.assert_not_called()
        assert cache_mod._CACHE["packages"] == ["R_PKG"]
        assert cache_mod._CACHE["pj_types"] == ["TYPE_R"]


# ============================================================
# Change: prod-history-first-tier-cache-filters
# Schema v2, cross-filter, schema-version mismatch, lock
# ============================================================

class TestSchemaV2Payload:
    """4-tuple payload v2 round-trip + indices derivation."""

    def test_4tuple_payload_v2_round_trip(self):
        """AC-1 — empty selection returns full distinct sets from cache."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        with patch.object(cache_mod, "_read_from_redis", return_value=None):
            with patch(
                "mes_dashboard.services.container_filter_cache.read_sql_df",
                return_value=_sample_tuple_df(),
            ):
                with patch.object(cache_mod, "_write_to_redis"):
                    cache_mod.init()

        opts = cache_mod.get_filter_options(None)
        assert sorted(opts["pj_types"]) == ["TYPE_X", "TYPE_Y"]
        assert sorted(opts["packages"]) == ["PKG_A", "PKG_B"]
        assert sorted(opts["bops"]) == ["BOP_1", "BOP_2", "BOP_3"]
        # NULL PJ_FUNCTION suppressed (data-boundary)
        assert sorted(opts["pj_functions"]) == ["FN_1", "FN_2"]
        assert opts["schema_version"] == 2

    def test_cross_filter_narrows_by_selected_package(self):
        """AC-2 — selecting a package narrows bops + types to co-occurrences."""
        import mes_dashboard.services.container_filter_cache as cache_mod

        with patch.object(cache_mod, "_read_from_redis", return_value=None):
            with patch(
                "mes_dashboard.services.container_filter_cache.read_sql_df",
                return_value=_sample_tuple_df(),
            ):
                with patch.object(cache_mod, "_write_to_redis"):
                    cache_mod.init()

        # PKG_A co-occurs with: TYPE_X+BOP_1+FN_1, TYPE_Y+BOP_1+(null)
        opts = cache_mod.get_filter_options({"packages": ["PKG_A"]})
        assert sorted(opts["bops"]) == ["BOP_1"]
        assert sorted(opts["pj_types"]) == ["TYPE_X", "TYPE_Y"]
        assert sorted(opts["pj_functions"]) == ["FN_1"]


class TestSchemaVersionMismatch:
    """AC-8 — stale/legacy payload triggers rebuild."""

    def test_schema_version_mismatch_triggers_rebuild(self):
        import mes_dashboard.services.container_filter_cache as cache_mod

        # Legacy v1-shaped payload (no schema_version)
        legacy = {
            "packages": ["OLD_PKG"],
            "pj_types": ["OLD_TYPE"],
            "updated_at": "2025-01-01T00:00:00",
        }

        # Simulate a Redis client returning legacy JSON.
        class _FakeRedis:
            def get(self, _key):
                import json
                return json.dumps(legacy)
            def set(self, *a, **kw):
                pass

        with patch.object(cache_mod, "get_redis_client", return_value=_FakeRedis()):
            with patch.object(cache_mod, "REDIS_ENABLED", True):
                # _read_from_redis should return None on schema mismatch.
                result = cache_mod._read_from_redis()
                assert result is None


class TestMultiWorkerLock:
    """PHF-05 — file-based exclusive lock for the rebuild path."""

    def test_lock_acquired_when_no_file_exists(self):
        import mes_dashboard.services.container_filter_cache as cache_mod
        cache_mod._LOCK_PATH.unlink(missing_ok=True)

        got = cache_mod._try_lock()
        try:
            assert got is True
            assert cache_mod._LOCK_PATH.exists()
        finally:
            cache_mod._release_lock()

    def test_lock_denied_when_file_exists(self):
        import mes_dashboard.services.container_filter_cache as cache_mod
        cache_mod._LOCK_PATH.unlink(missing_ok=True)

        # First acquisition wins.
        first = cache_mod._try_lock()
        try:
            assert first is True
            second = cache_mod._try_lock()
            assert second is False, "Second acquire must fail while lock held"
        finally:
            cache_mod._release_lock()
        # And cleanup removes the file.
        assert not cache_mod._LOCK_PATH.exists()
