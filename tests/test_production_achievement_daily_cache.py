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
