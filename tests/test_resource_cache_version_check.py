# -*- coding: utf-8 -*-
"""AC-7 — resource_cache.refresh_cache() version-bypass regression tests.

Symptom: refresh_cache(force=True) re-queries Oracle even when Redis already
holds data at the same version, causing every gunicorn worker startup to hit
Oracle independently.

Root cause: the version-equality guard is short-circuited by `force=True`,
so the `_load_from_oracle()` call runs even when it is unnecessary.

Fix contract:
  - If `redis_version == oracle_version` AND Redis already has the data key,
    skip `_load_from_oracle()` even when force=True.
  - If `redis_version == oracle_version` but Redis is EMPTY, run _load_from_oracle
    (this is the normal initial load path).
  - If versions differ, always run _load_from_oracle regardless of force.

Tests here follow the TDD discipline: they are written BEFORE the fix is
applied, so they FAIL first and PASS after the fix.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_df():
    """Minimal non-empty DataFrame to stand in for Oracle data."""
    import pandas as pd
    return pd.DataFrame({"RESOURCEID": ["R001"], "RESOURCENAME": ["Test"]})


# ---------------------------------------------------------------------------
# AC-7.1 — identical version + Redis already populated -> no Oracle fetch
# ---------------------------------------------------------------------------

class TestRefreshCacheForceTrue:
    """refresh_cache(force=True) must not call _load_from_oracle when Redis
    already has up-to-date data."""

    def test_refresh_cache_force_true_no_oracle_if_version_unchanged(self, monkeypatch):
        """AC-7.1: Same oracle_version == redis_version AND data key exists ->
        _load_from_oracle must NOT be called."""
        import mes_dashboard.services.resource_cache as rc

        common_version = "2026-06-05T16:39:39"

        monkeypatch.setattr(rc, "_get_version_from_oracle", lambda: common_version)
        monkeypatch.setattr(rc, "_get_version_from_redis", lambda: common_version)
        monkeypatch.setattr(rc, "_redis_data_available", lambda client=None: True)
        monkeypatch.setattr(rc, "redis_available", lambda: True)
        monkeypatch.setattr(rc, "REDIS_ENABLED", True)
        monkeypatch.setattr(rc, "RESOURCE_CACHE_ENABLED", True)

        oracle_calls = []

        def _mock_load_from_oracle():
            oracle_calls.append(1)
            return _make_mock_df()

        monkeypatch.setattr(rc, "_load_from_oracle", _mock_load_from_oracle)

        result = rc.refresh_cache(force=True)

        assert oracle_calls == [], (
            "refresh_cache(force=True) must NOT call _load_from_oracle when "
            "redis_version == oracle_version and Redis data already exists. "
            f"Got {len(oracle_calls)} call(s)."
        )
        # Should return False because no refresh was actually needed
        assert result is False, (
            "refresh_cache(force=True) should return False when skipping Oracle "
            f"(version already current). Got result={result!r}."
        )

    # -----------------------------------------------------------------------
    # AC-7.2 — identical version + Redis EMPTY -> Oracle fetch runs
    # -----------------------------------------------------------------------

    def test_refresh_cache_force_true_oracle_runs_when_redis_empty(self, monkeypatch):
        """AC-7.2: Same oracle_version == redis_version BUT Redis data is absent ->
        _load_from_oracle MUST be called (initial load path)."""
        import mes_dashboard.services.resource_cache as rc

        common_version = "2026-06-05T16:39:39"

        monkeypatch.setattr(rc, "_get_version_from_oracle", lambda: common_version)
        monkeypatch.setattr(rc, "_get_version_from_redis", lambda: common_version)
        monkeypatch.setattr(rc, "_redis_data_available", lambda client=None: False)
        monkeypatch.setattr(rc, "redis_available", lambda: True)
        monkeypatch.setattr(rc, "REDIS_ENABLED", True)
        monkeypatch.setattr(rc, "RESOURCE_CACHE_ENABLED", True)
        monkeypatch.setattr(rc, "_sync_to_redis", lambda df, version: True)

        oracle_calls = []

        def _mock_load_from_oracle():
            oracle_calls.append(1)
            return _make_mock_df()

        monkeypatch.setattr(rc, "_load_from_oracle", _mock_load_from_oracle)

        # Suppress the package-group TTL path
        import time
        monkeypatch.setattr(rc, "_package_group_refreshed_at", time.time())

        rc.refresh_cache(force=True)

        assert len(oracle_calls) == 1, (
            "refresh_cache(force=True) MUST call _load_from_oracle when Redis "
            f"has no data (initial load). Got {len(oracle_calls)} call(s)."
        )

    # -----------------------------------------------------------------------
    # AC-7.3 — different versions -> Oracle fetch always runs
    # -----------------------------------------------------------------------

    def test_refresh_cache_always_fetches_when_version_differs(self, monkeypatch):
        """AC-7.3: oracle_version != redis_version -> _load_from_oracle must run
        regardless of force flag or Redis data availability."""
        import mes_dashboard.services.resource_cache as rc

        monkeypatch.setattr(rc, "_get_version_from_oracle", lambda: "2026-06-05T17:00:00")
        monkeypatch.setattr(rc, "_get_version_from_redis", lambda: "2026-06-05T16:00:00")
        monkeypatch.setattr(rc, "_redis_data_available", lambda client=None: True)
        monkeypatch.setattr(rc, "redis_available", lambda: True)
        monkeypatch.setattr(rc, "REDIS_ENABLED", True)
        monkeypatch.setattr(rc, "RESOURCE_CACHE_ENABLED", True)
        monkeypatch.setattr(rc, "_sync_to_redis", lambda df, version: True)

        oracle_calls = []

        def _mock_load_from_oracle():
            oracle_calls.append(1)
            return _make_mock_df()

        monkeypatch.setattr(rc, "_load_from_oracle", _mock_load_from_oracle)

        import time
        monkeypatch.setattr(rc, "_package_group_refreshed_at", time.time())

        rc.refresh_cache(force=False)

        assert len(oracle_calls) == 1, (
            "refresh_cache() must call _load_from_oracle when versions differ. "
            f"Got {len(oracle_calls)} call(s)."
        )

    def test_refresh_cache_force_fetches_when_version_differs(self, monkeypatch):
        """AC-7.3b: With force=True and versions differing, Oracle still runs."""
        import mes_dashboard.services.resource_cache as rc

        monkeypatch.setattr(rc, "_get_version_from_oracle", lambda: "2026-06-05T17:00:00")
        monkeypatch.setattr(rc, "_get_version_from_redis", lambda: "2026-06-05T16:00:00")
        monkeypatch.setattr(rc, "_redis_data_available", lambda client=None: True)
        monkeypatch.setattr(rc, "redis_available", lambda: True)
        monkeypatch.setattr(rc, "REDIS_ENABLED", True)
        monkeypatch.setattr(rc, "RESOURCE_CACHE_ENABLED", True)
        monkeypatch.setattr(rc, "_sync_to_redis", lambda df, version: True)

        oracle_calls = []

        def _mock_load_from_oracle():
            oracle_calls.append(1)
            return _make_mock_df()

        monkeypatch.setattr(rc, "_load_from_oracle", _mock_load_from_oracle)

        import time
        monkeypatch.setattr(rc, "_package_group_refreshed_at", time.time())

        rc.refresh_cache(force=True)

        assert len(oracle_calls) == 1, (
            "refresh_cache(force=True) must call _load_from_oracle when versions differ. "
            f"Got {len(oracle_calls)} call(s)."
        )


# ---------------------------------------------------------------------------
# AC-7.4 — cache_updater initial forced check does not re-fetch if Redis populated
# ---------------------------------------------------------------------------

class TestCacheUpdaterInitialCheckNoDoubleFetch:
    """AC-7.4: _check_resource_update(force=True) must not cause Oracle fetch when
    Redis is already populated at the correct version."""

    def test_cache_updater_initial_check_no_double_fetch(self, monkeypatch):
        """When Redis is already populated with the current oracle version,
        the initial forced resource update must NOT trigger an Oracle load."""
        import mes_dashboard.services.resource_cache as rc
        import mes_dashboard.core.cache_updater as cu

        common_version = "2026-06-05T16:39:39"

        monkeypatch.setattr(rc, "_get_version_from_oracle", lambda: common_version)
        monkeypatch.setattr(rc, "_get_version_from_redis", lambda: common_version)
        monkeypatch.setattr(rc, "_redis_data_available", lambda client=None: True)
        monkeypatch.setattr(rc, "redis_available", lambda: True)
        monkeypatch.setattr(rc, "REDIS_ENABLED", True)
        monkeypatch.setattr(rc, "RESOURCE_CACHE_ENABLED", True)

        # Patch distributed lock so CacheUpdater can proceed
        monkeypatch.setattr(cu, "try_acquire_lock", lambda name, **kw: True)
        monkeypatch.setattr(cu, "release_lock", lambda name: None)

        oracle_calls = []

        def _mock_load_from_oracle():
            oracle_calls.append(1)
            return _make_mock_df()

        monkeypatch.setattr(rc, "_load_from_oracle", _mock_load_from_oracle)

        updater = cu.CacheUpdater()
        updater._check_resource_update(force=True)

        assert oracle_calls == [], (
            "CacheUpdater._check_resource_update(force=True) must NOT trigger "
            "an Oracle fetch when Redis already holds the current version. "
            f"Got {len(oracle_calls)} Oracle call(s)."
        )
