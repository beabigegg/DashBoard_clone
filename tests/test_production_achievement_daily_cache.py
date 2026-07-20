# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_daily_cache (warm-cache module,
production-achievement-overhaul Phase 5, PA-14).

Covers:
  - cache-hit short-circuits with zero .run()/Oracle calls
  - cache-miss triggers exactly one .run() with the correct job_id/params
  - flag-off no-ops WITHOUT importing the worker module (kill-switch must
    not be defeated by an unconditional lazy import)
  - the progress_report() override never calls update_job_progress()
    (Redis-orphan-key trap, design.md Key Decisions)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


class _FakeRedis:
    """Minimal in-memory stand-in for the query_spool_store's Redis client,
    matching tests/test_query_spool_store.py's FakeRedis (setex/get/delete
    only -- this module never calls scan_iter). Used by
    TestMultiCycleWarmupIntegration below to exercise the REAL
    register_spool_file/get_spool_metadata CAS + staleness code paths
    end-to-end (not mocked away), across two full simulated warmup cycles.
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._data[key] = value
        return True

    def get(self, key: str):
        return self._data.get(key)

    def delete(self, *keys) -> int:
        deleted = 0
        for key in keys:
            if key in self._data:
                deleted += 1
            self._data.pop(key, None)
        return deleted


class TestCacheHitShortCircuits:
    def test_cache_hit_returns_without_run_or_oracle_call(self, monkeypatch):
        """A pre-existing, still-FRESH spool must short-circuit BEFORE any
        job is built (proving zero .run()/Oracle calls -- building the job
        is the only path that could reach Oracle)."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/existing/spool/path.parquet",
        )
        # Today's freshness check only runs for ensure_today_loaded (yesterday
        # never calls it -- a closed day is fresh forever once cached).
        monkeypatch.setattr(cache_mod, "_is_today_spool_stale", lambda query_id: False)
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_job", mock_build)

        assert cache_mod.ensure_today_loaded() == "/existing/spool/path.parquet"
        assert cache_mod.ensure_yesterday_loaded() == "/existing/spool/path.parquet"
        mock_build.assert_not_called()


class TestCacheMissTriggersJobRun:
    def test_cache_miss_triggers_job_run_exactly_once(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fake/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        result = cache_mod.ensure_today_loaded()

        assert result == "/fake/spool/path.parquet"
        assert len(run_calls) == 1
        job_id, params = run_calls[0]
        today_str = date.today().strftime("%Y-%m-%d")
        assert job_id == f"warmup-pa-{today_str}"
        assert params == {"start_date": today_str, "end_date": today_str}

    def test_ensure_yesterday_loaded_uses_yesterday_date(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fake/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        cache_mod.ensure_yesterday_loaded()

        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert run_calls == [
            (f"warmup-pa-{yesterday_str}", {"start_date": yesterday_str, "end_date": yesterday_str})
        ]


class TestTodayStaleSpoolRebuilds:
    """Root-cause fix for blank 當日產出: an existing-but-stale spool for
    TODAY must be rebuilt (not short-circuited), while the identical
    existing-spool state for YESTERDAY still short-circuits untouched."""

    def test_stale_today_spool_triggers_rebuild(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/stale/spool/path.parquet",
        )
        monkeypatch.setattr(cache_mod, "_is_today_spool_stale", lambda query_id: True)

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fresh/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        result = cache_mod.ensure_today_loaded()

        assert result == "/fresh/spool/path.parquet"
        assert len(run_calls) == 1

    def test_stale_today_spool_with_flag_off_returns_existing_stale_path(self, monkeypatch):
        """Kill switch still wins: with the flag off, a stale-but-existing
        spool is served as-is (no rebuild capability) rather than losing the
        data entirely -- mirrors the pre-existing flag-off degrade behavior."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "off")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/stale/spool/path.parquet",
        )
        monkeypatch.setattr(cache_mod, "_is_today_spool_stale", lambda query_id: True)
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_job", mock_build)

        assert cache_mod.ensure_today_loaded() == "/stale/spool/path.parquet"
        mock_build.assert_not_called()

    def test_yesterday_never_consults_staleness_check(self, monkeypatch):
        """A closed day (yesterday) must short-circuit on ANY existing spool
        without ever calling the today-only staleness check."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/existing/spool/path.parquet",
        )
        mock_stale = MagicMock(return_value=True)
        monkeypatch.setattr(cache_mod, "_is_today_spool_stale", mock_stale)
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_job", mock_build)

        assert cache_mod.ensure_yesterday_loaded() == "/existing/spool/path.parquet"
        mock_stale.assert_not_called()
        mock_build.assert_not_called()


class TestIsTodaySpoolStale:
    def test_fresh_metadata_is_not_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("WARMUP_INTERVAL_SECONDS", "3600")
        monkeypatch.setattr(cache_mod.time, "time", lambda: 10_000.0)
        monkeypatch.setattr(
            cache_mod, "get_spool_metadata",
            lambda namespace, query_id: {"created_at": 10_000 - 60},  # 1 minute old
        )

        assert cache_mod._is_today_spool_stale("some-query-id") is False

    def test_old_metadata_is_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("WARMUP_INTERVAL_SECONDS", "3600")
        monkeypatch.setattr(cache_mod.time, "time", lambda: 10_000.0)
        monkeypatch.setattr(
            cache_mod, "get_spool_metadata",
            lambda namespace, query_id: {"created_at": 10_000 - 3601},  # just over 1h old
        )

        assert cache_mod._is_today_spool_stale("some-query-id") is True

    def test_missing_metadata_is_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(cache_mod, "get_spool_metadata", lambda namespace, query_id: None)

        assert cache_mod._is_today_spool_stale("some-query-id") is True

    def test_missing_created_at_is_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(cache_mod, "get_spool_metadata", lambda namespace, query_id: {})

        assert cache_mod._is_today_spool_stale("some-query-id") is True


class TestInflightStateDedup:
    """Race-condition fix companion (query_spool_store CAS write in
    workers/production_achievement_worker.py): a query_id already inflight
    (previous warmup cycle still running, OR a user-triggered force_refresh
    job) must never get a second, duplicate warmup job started."""

    def test_inflight_skips_build_warmup_job(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        monkeypatch.setattr(
            cache_mod, "get_inflight_state",
            lambda namespace, query_id: {"started_at": 123.0, "job_id": "warmup-pa-x"},
        )
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_job", mock_build)

        result = cache_mod.ensure_today_loaded()

        assert result is None  # mirrors get_spool_file_path's None return
        mock_build.assert_not_called()

    def test_inflight_skips_build_warmup_job_returns_existing_stale_path(self, monkeypatch):
        """When already-inflight AND an existing (stale) spool_path is
        present, the existing path is returned as-is -- no rebuild is
        triggered while a job for the same key is already running."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/stale/spool/path.parquet",
        )
        monkeypatch.setattr(cache_mod, "_is_today_spool_stale", lambda query_id: True)
        monkeypatch.setattr(
            cache_mod, "get_inflight_state",
            lambda namespace, query_id: {"started_at": 123.0, "job_id": "warmup-pa-x"},
        )
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_job", mock_build)

        result = cache_mod.ensure_today_loaded()

        assert result == "/stale/spool/path.parquet"
        mock_build.assert_not_called()

    def test_not_inflight_triggers_build_warmup_job_as_before(self, monkeypatch):
        """get_inflight_state returning None must not change pre-existing
        cache-miss behavior -- _build_warmup_job still runs exactly once."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        monkeypatch.setattr(
            cache_mod, "get_inflight_state", lambda namespace, query_id: None
        )

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fake/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        result = cache_mod.ensure_today_loaded()

        assert result == "/fake/spool/path.parquet"
        assert len(run_calls) == 1


class TestFlagOffKillSwitch:
    def test_flag_off_no_ops_without_importing_worker_module(self, monkeypatch):
        """Independent re-read of PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB
        BEFORE the lazy worker import: with the flag off, the worker module
        must NEVER be imported. Proven by sabotaging sys.modules so ANY
        import attempt raises ImportError immediately -- if the flag-off
        path incorrectly imported the worker anyway, this test would fail
        with an ImportError instead of passing cleanly."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "off")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        monkeypatch.setitem(
            sys.modules, "mes_dashboard.workers.production_achievement_worker", None
        )

        result = cache_mod.ensure_today_loaded()
        assert result is None

    def test_flag_off_never_calls_build_warmup_job(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "off")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_job", mock_build)

        assert cache_mod.ensure_today_loaded() is None
        assert cache_mod.ensure_yesterday_loaded() is None
        mock_build.assert_not_called()


class TestProgressReportOverride:
    def test_progress_report_override_never_calls_update_job_progress(self):
        """PA-14 Redis-orphan-key trap: ProductionAchievementJob.progress_report()
        (inherited) calls async_query_job_service.update_job_progress(), an
        UNCONDITIONAL Redis HSET with no TTL and no existence check. The
        warm-cache subclass's progress_report() override must be a complete
        no-op so calling .run() directly (bypassing enqueue_query_job's TTL
        registration) never leaks an orphaned, un-expiring Redis key."""
        from mes_dashboard.services.production_achievement_daily_cache import (
            _build_warmup_job,
        )
        from mes_dashboard.workers.production_achievement_worker import (
            ProductionAchievementJob,
        )

        job = _build_warmup_job(
            job_id="warmup-pa-2026-07-13",
            params={"start_date": "2026-07-13", "end_date": "2026-07-13"},
        )

        # Genuine subclass reusing ProductionAchievementJob -- not a
        # hand-written parallel Oracle path (design.md Key Decisions).
        assert isinstance(job, ProductionAchievementJob)
        assert type(job) is not ProductionAchievementJob

        with patch(
            "mes_dashboard.services.async_query_job_service.update_job_progress"
        ) as mock_update_progress:
            job.progress_report(50)

        mock_update_progress.assert_not_called()


# ---------------------------------------------------------------------------
# 轉出 (move-out) source -- mirrors every 產出 test class above 1:1, PA-18.
# ---------------------------------------------------------------------------


class TestMoveoutCacheHitShortCircuits:
    def test_cache_hit_returns_without_run_or_oracle_call(self, monkeypatch):
        """A pre-existing, still-FRESH moveout spool must short-circuit
        BEFORE any job is built (proving zero .run()/Oracle calls -- building
        the job is the only path that could reach Oracle)."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/existing/moveout/spool/path.parquet",
        )
        monkeypatch.setattr(cache_mod, "_is_moveout_today_spool_stale", lambda query_id: False)
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_moveout_job", mock_build)

        assert cache_mod.ensure_moveout_today_loaded() == "/existing/moveout/spool/path.parquet"
        assert cache_mod.ensure_moveout_yesterday_loaded() == "/existing/moveout/spool/path.parquet"
        mock_build.assert_not_called()


class TestMoveoutCacheMissTriggersJobRun:
    def test_cache_miss_triggers_job_run_exactly_once(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fake/moveout/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_moveout_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        result = cache_mod.ensure_moveout_today_loaded()

        assert result == "/fake/moveout/spool/path.parquet"
        assert len(run_calls) == 1
        job_id, params = run_calls[0]
        today_str = date.today().strftime("%Y-%m-%d")
        assert job_id == f"warmup-pa-moveout-{today_str}"
        assert params == {"start_date": today_str, "end_date": today_str}

    def test_ensure_moveout_yesterday_loaded_uses_yesterday_date(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fake/moveout/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_moveout_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        cache_mod.ensure_moveout_yesterday_loaded()

        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert run_calls == [
            (
                f"warmup-pa-moveout-{yesterday_str}",
                {"start_date": yesterday_str, "end_date": yesterday_str},
            )
        ]


class TestMoveoutTodayStaleSpoolRebuilds:
    """Same growing-window staleness fix as 產出, applied to 轉出: an
    existing-but-stale spool for TODAY must be rebuilt (not short-circuited),
    while the identical existing-spool state for YESTERDAY still
    short-circuits untouched."""

    def test_stale_today_spool_triggers_rebuild(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/stale/moveout/spool/path.parquet",
        )
        monkeypatch.setattr(cache_mod, "_is_moveout_today_spool_stale", lambda query_id: True)

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fresh/moveout/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_moveout_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        result = cache_mod.ensure_moveout_today_loaded()

        assert result == "/fresh/moveout/spool/path.parquet"
        assert len(run_calls) == 1

    def test_stale_today_spool_with_flag_off_returns_existing_stale_path(self, monkeypatch):
        """Kill switch still wins: with the flag off, a stale-but-existing
        moveout spool is served as-is (no rebuild capability) rather than
        losing the data entirely."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "off")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/stale/moveout/spool/path.parquet",
        )
        monkeypatch.setattr(cache_mod, "_is_moveout_today_spool_stale", lambda query_id: True)
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_moveout_job", mock_build)

        assert cache_mod.ensure_moveout_today_loaded() == "/stale/moveout/spool/path.parquet"
        mock_build.assert_not_called()

    def test_yesterday_never_consults_staleness_check(self, monkeypatch):
        """A closed moveout day (yesterday) must short-circuit on ANY
        existing spool without ever calling the today-only staleness
        check."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(
            cache_mod, "get_spool_file_path",
            lambda namespace, query_id: "/existing/moveout/spool/path.parquet",
        )
        mock_stale = MagicMock(return_value=True)
        monkeypatch.setattr(cache_mod, "_is_moveout_today_spool_stale", mock_stale)
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_moveout_job", mock_build)

        assert cache_mod.ensure_moveout_yesterday_loaded() == "/existing/moveout/spool/path.parquet"
        mock_stale.assert_not_called()
        mock_build.assert_not_called()


class TestIsMoveoutTodaySpoolStale:
    def test_fresh_metadata_is_not_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("WARMUP_INTERVAL_SECONDS", "3600")
        monkeypatch.setattr(cache_mod.time, "time", lambda: 10_000.0)
        monkeypatch.setattr(
            cache_mod, "get_spool_metadata",
            lambda namespace, query_id: {"created_at": 10_000 - 60},  # 1 minute old
        )

        assert cache_mod._is_moveout_today_spool_stale("some-query-id") is False

    def test_old_metadata_is_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("WARMUP_INTERVAL_SECONDS", "3600")
        monkeypatch.setattr(cache_mod.time, "time", lambda: 10_000.0)
        monkeypatch.setattr(
            cache_mod, "get_spool_metadata",
            lambda namespace, query_id: {"created_at": 10_000 - 3601},  # just over 1h old
        )

        assert cache_mod._is_moveout_today_spool_stale("some-query-id") is True

    def test_missing_metadata_is_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(cache_mod, "get_spool_metadata", lambda namespace, query_id: None)

        assert cache_mod._is_moveout_today_spool_stale("some-query-id") is True

    def test_missing_created_at_is_stale(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setattr(cache_mod, "get_spool_metadata", lambda namespace, query_id: {})

        assert cache_mod._is_moveout_today_spool_stale("some-query-id") is True


class TestMoveoutInflightStateDedup:
    """Moveout counterpart of TestInflightStateDedup, PA-18."""

    def test_inflight_skips_build_warmup_moveout_job(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        monkeypatch.setattr(
            cache_mod, "get_inflight_state",
            lambda namespace, query_id: {"started_at": 456.0, "job_id": "warmup-pa-moveout-x"},
        )
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_moveout_job", mock_build)

        result = cache_mod.ensure_moveout_today_loaded()

        assert result is None
        mock_build.assert_not_called()

    def test_not_inflight_triggers_build_warmup_moveout_job_as_before(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        monkeypatch.setattr(
            cache_mod, "get_inflight_state", lambda namespace, query_id: None
        )

        run_calls = []

        class _FakeJob:
            def __init__(self, job_id, params):
                self.job_id = job_id
                self.params = params

            def run(self):
                run_calls.append((self.job_id, self.params))
                return "/fake/moveout/spool/path.parquet"

        monkeypatch.setattr(
            cache_mod, "_build_warmup_moveout_job",
            lambda job_id, params: _FakeJob(job_id, params),
        )

        result = cache_mod.ensure_moveout_today_loaded()

        assert result == "/fake/moveout/spool/path.parquet"
        assert len(run_calls) == 1


class TestMoveoutFlagOffKillSwitch:
    def test_flag_off_no_ops_without_importing_worker_module(self, monkeypatch):
        """Independent re-read of PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB
        BEFORE the lazy moveout worker import: with the flag off, the
        moveout worker module must NEVER be imported. Proven by sabotaging
        sys.modules so ANY import attempt raises ImportError immediately --
        if the flag-off path incorrectly imported the worker anyway, this
        test would fail with an ImportError instead of passing cleanly."""
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "off")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        monkeypatch.setitem(
            sys.modules, "mes_dashboard.workers.production_achievement_moveout_worker", None
        )

        result = cache_mod.ensure_moveout_today_loaded()
        assert result is None

    def test_flag_off_never_calls_build_warmup_moveout_job(self, monkeypatch):
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod

        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "off")
        monkeypatch.setattr(
            cache_mod, "get_spool_file_path", lambda namespace, query_id: None
        )
        mock_build = MagicMock()
        monkeypatch.setattr(cache_mod, "_build_warmup_moveout_job", mock_build)

        assert cache_mod.ensure_moveout_today_loaded() is None
        assert cache_mod.ensure_moveout_yesterday_loaded() is None
        mock_build.assert_not_called()


class TestMoveoutProgressReportOverride:
    def test_progress_report_override_never_calls_update_job_progress(self):
        """PA-18 Redis-orphan-key trap (moveout counterpart of PA-14):
        ProductionAchievementMoveoutJob.progress_report() (inherited from
        BaseChunkedDuckDBJob) calls async_query_job_service.update_job_progress(),
        an UNCONDITIONAL Redis HSET with no TTL and no existence check. The
        warm-cache subclass's progress_report() override must be a complete
        no-op so calling .run() directly (bypassing enqueue_query_job's TTL
        registration) never leaks an orphaned, un-expiring Redis key."""
        from mes_dashboard.services.production_achievement_daily_cache import (
            _build_warmup_moveout_job,
        )
        from mes_dashboard.workers.production_achievement_moveout_worker import (
            ProductionAchievementMoveoutJob,
        )

        job = _build_warmup_moveout_job(
            job_id="warmup-pa-moveout-2026-07-13",
            params={"start_date": "2026-07-13", "end_date": "2026-07-13"},
        )

        # Genuine subclass reusing ProductionAchievementMoveoutJob -- not a
        # hand-written parallel Oracle path.
        assert isinstance(job, ProductionAchievementMoveoutJob)
        assert type(job) is not ProductionAchievementMoveoutJob

        with patch(
            "mes_dashboard.services.async_query_job_service.update_job_progress"
        ) as mock_update_progress:
            job.progress_report(50)

        mock_update_progress.assert_not_called()


# ---------------------------------------------------------------------------
# TestMultiCycleWarmupIntegration -- end-to-end acceptance test for the
# reported production bug ("hourly auto-refresh never picks up new Oracle
# rows, only the manual force-refresh button does").
#
# This deliberately does NOT mock _build_warmup_job, _is_today_spool_stale,
# or register_spool_file -- it runs the REAL ProductionAchievementJob
# pipeline (pre_query -> fan-out -> post_aggregate -> the CAS-protected
# register_spool_file in query_spool_store.py) twice in a row, simulating
# two consecutive real hourly scheduler cycles, with only Oracle access
# (BaseChunkedDuckDBJob._fetch_chunk) stubbed out. Two hypotheses this test
# distinguishes between:
#
#   H1 (CAS non-monotonic cas_value): register_spool_file's
#      cas_field="query_started_at" write could be skipped because a later
#      cycle's query_started_at is <= an earlier cycle's. REFUTED by
#      inspection + existing coverage: ProductionAchievementJob.pre_query()
#      (production_achievement_worker.py) sets self._query_started_at =
#      time.time() FRESH at the start of every .run() call (verified by
#      tests/test_production_achievement_unified_job.py::
#      TestInflightStateAndCas::test_pre_query_records_started_at_and_sets_inflight_state),
#      and tests/test_query_spool_store.py::test_register_spool_file_cas_writes_when_newer
#      already proves a strictly-larger cas_value always wins the CAS. Two
#      serial (non-overlapping) cycles separated by real wall-clock time can
#      never produce a non-increasing cas_value, so H1 does not reproduce.
#
#   H2 (staleness watermark anchored to the WRONG clock, CONFIRMED,
#      reproduced below): _is_today_spool_stale() compares "now" against
#      the spool's "created_at" -- the timestamp of when the LAST WRITE
#      FINISHED (post_aggregate, after the Oracle fetch completed) -- using
#      the exact SAME threshold as WARMUP_INTERVAL_SECONDS, the interval the
#      scheduler's OWN tick loop uses (spool_warmup_scheduler.py
#      _scheduler_loop's `_STOP_EVENT.wait(WARMUP_INTERVAL_SECONDS)`, which
#      ticks on a fixed cadence from thread start, NOT from when the
#      previously-enqueued job actually finished). Because a real Oracle
#      fetch always takes some non-zero duration `delta` to complete, a
#      spool that finished writing at scheduler-tick K is created at
#      (tick_K + delta), so it is only (I - delta) seconds old -- just
#      UNDER the threshold -- by the very next tick (tick_K + I). That next
#      cycle's staleness check therefore reports "not stale yet" and skips
#      the rebuild entirely, even though a full scheduler interval has
#      elapsed and new Oracle rows may already exist. This test reproduces
#      exactly that: cycle 1 takes a small non-zero simulated duration, the
#      clock then advances by exactly one WARMUP_INTERVAL_SECONDS tick (the
#      real scheduler's cadence) for cycle 2, and Oracle has MORE rows
#      available -- but pre-fix, cycle 2's rebuild never lands.
# ---------------------------------------------------------------------------


class TestMultiCycleWarmupIntegration:
    def test_second_hourly_cycle_lands_with_more_rows(self, monkeypatch, tmp_path):
        import time as real_time

        import pyarrow as pa

        import mes_dashboard.core.query_spool_store as spool_mod
        import mes_dashboard.services.production_achievement_daily_cache as cache_mod
        import mes_dashboard.workers.production_achievement_worker as worker_mod
        from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob
        from mes_dashboard.services.production_achievement_service import (
            PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE,
            make_canonical_pa_spool_id,
        )

        fake = _FakeRedis()
        monkeypatch.setattr(spool_mod, "QUERY_SPOOL_ENABLED", True)
        monkeypatch.setattr(spool_mod, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
        monkeypatch.setattr(spool_mod, "get_redis_client", lambda: fake)
        monkeypatch.setattr(spool_mod, "get_control_redis_client", lambda: fake)

        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))
        monkeypatch.setenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on")
        monkeypatch.setenv("WARMUP_INTERVAL_SECONDS", "3600")

        # One fake wall clock shared by every module on this call path that
        # reads time.time() (query_spool_store's created_at/expires_at math,
        # the daily-cache staleness check, and the worker's
        # _query_started_at) -- seeded from the REAL current epoch so
        # query_spool_store's expires_at comparisons stay sane, and only
        # ever advanced explicitly by this test (never by real elapsed
        # wall-clock time), so the reproduction is exact and not flaky.
        clock = {"t": real_time.time()}
        monkeypatch.setattr(spool_mod.time, "time", lambda: clock["t"])
        monkeypatch.setattr(cache_mod.time, "time", lambda: clock["t"])
        monkeypatch.setattr(worker_mod.time, "time", lambda: clock["t"])

        # Force strictly-serial chunk fetch (no ThreadPoolExecutor fan-out)
        # so the fake Oracle stub below never has to reason about which
        # thread runs first -- irrelevant to the bug this test targets.
        monkeypatch.setattr(BaseChunkedDuckDBJob, "max_parallel", 1)

        today = date.today()
        today_str = today.strftime("%Y-%m-%d")
        rows_holder: dict = {"rows": [], "fetch_duration_seconds": 0}

        def _fake_fetch_chunk(self, chunk_params):
            # Simulate the real Oracle round-trip taking non-zero wall-clock
            # time -- the crux of H2: even a small, realistic query duration
            # is what makes the NEXT scheduler tick's staleness check land
            # just under the raw threshold.
            clock["t"] += rows_holder["fetch_duration_seconds"]
            # Only the regular whole-day chunk (start_date == today) ever
            # carries rows -- the D6 closing chunk (PA-15, start_date ==
            # tomorrow) always contributes zero, keeping row counts exact.
            if chunk_params.get("start_date") != today_str or not rows_holder["rows"]:
                return
            rows = rows_holder["rows"]
            table = pa.table({
                "OUTPUT_DATE": pa.array([r["OUTPUT_DATE"] for r in rows], type=pa.date32()),
                "SHIFT_CODE": pa.array([r["SHIFT_CODE"] for r in rows], type=pa.string()),
                "SPECNAME": pa.array([r["SPECNAME"] for r in rows], type=pa.string()),
                "PACKAGE_LF": pa.array([r.get("PACKAGE_LF") for r in rows], type=pa.string()),
                "ACTUAL_OUTPUT_QTY": pa.array([r["ACTUAL_OUTPUT_QTY"] for r in rows], type=pa.int64()),
                "MAX_TRACKOUT_TS": pa.array([r.get("MAX_TRACKOUT_TS") for r in rows], type=pa.timestamp("us")),
            })
            for batch in table.to_batches():
                yield batch

        monkeypatch.setattr(BaseChunkedDuckDBJob, "_fetch_chunk", _fake_fetch_chunk)

        query_id = make_canonical_pa_spool_id(today_str, today_str)

        # tick_0: the scheduler's OWN nominal fire time for cycle 1 (before
        # this test's simulated Oracle fetch consumes any wall-clock time).
        tick_0 = clock["t"]

        # --- Cycle 1 (e.g. the first hourly warmup after boot): Oracle has
        # 1 row so far today; the fetch takes a realistic 30 seconds. ---
        rows_holder["rows"] = [
            {"OUTPUT_DATE": today, "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B",
             "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 100},
        ]
        rows_holder["fetch_duration_seconds"] = 30
        spool_path_1 = cache_mod.ensure_today_loaded()
        assert spool_path_1 is not None

        metadata_1 = spool_mod.get_spool_metadata(PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE, query_id)
        assert metadata_1 is not None
        assert metadata_1["row_count"] == 1

        # --- Jump to tick_1 = tick_0 + one scheduler interval -- the REAL
        # deployment's _scheduler_loop (spool_warmup_scheduler.py) ticks on
        # a FIXED cadence measured from its own thread start / previous
        # tick, NOT from when the previously-enqueued job actually
        # finished (`_STOP_EVENT.wait(WARMUP_INTERVAL_SECONDS)` runs again
        # immediately after each fast, synchronous `run_warmup_cycle()`
        # enqueue call -- the slow part, the RQ job actually executing, is
        # fully decoupled from this loop's timing). Setting the clock to
        # `tick_0 + interval` (not `clock["t"] + interval`, i.e. not
        # relative to cycle 1's finish time) is what makes this
        # reproduction exact -- simulate a second shift's worth of new
        # Oracle rows having landed by then. ---
        clock["t"] = tick_0 + 3600

        rows_holder["rows"] = [
            {"OUTPUT_DATE": today, "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B",
             "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 100},
            {"OUTPUT_DATE": today, "SHIFT_CODE": "N", "SPECNAME": "Epoxy D/B",
             "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 40},
        ]
        rows_holder["fetch_duration_seconds"] = 30
        spool_path_2 = cache_mod.ensure_today_loaded()

        metadata_2 = spool_mod.get_spool_metadata(PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE, query_id)
        assert metadata_2 is not None

        # The core assertion this bug report hinges on: cycle 2 must have
        # actually landed -- row_count/created_at must reflect the SECOND
        # run, not stay frozen at cycle 1's values. Pre-fix, cycle 2's
        # staleness check reports "not stale yet" (created_at_1 = tick_0 +
        # 60s -- both the regular AND the D6 closing chunk fetches each
        # consume the simulated 30s, so age at tick_1 = 3600 - 60 = 3540 <
        # 3600) and _ensure_day_loaded short-circuits WITHOUT ever building
        # or running a second job -- reproducing "the hourly auto-refresh
        # never picks up new Oracle rows."
        assert spool_path_2 is not None
        assert metadata_2["row_count"] == 2, (
            f"cycle 2's rebuild did not land: row_count is still "
            f"{metadata_2['row_count']} (expected 2) -- metadata: {metadata_2}"
        )
        assert metadata_2["created_at"] > metadata_1["created_at"]

        import duckdb
        con = duckdb.connect()
        try:
            total_qty = con.execute(
                f"SELECT SUM(actual_output_qty) FROM read_parquet('{spool_path_2}')"
            ).fetchone()[0]
        finally:
            con.close()
        assert total_qty == 140, f"expected cycle 2's SUM(actual_output_qty)=140, got {total_qty}"
