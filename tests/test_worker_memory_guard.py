# -*- coding: utf-8 -*-
"""Tests for worker_memory_guard module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard.core.cache import (
    ProcessLevelCache,
    _PROCESS_CACHE_REGISTRY,
    emergency_clear_all_process_caches,
    register_process_cache,
)


# ============================================================
# Test: emergency_clear_all_process_caches
# ============================================================

class TestEmergencyClearAllProcessCaches:
    def test_clears_all_registered_caches(self):
        cache_a = ProcessLevelCache(ttl_seconds=60, max_size=4)
        cache_b = ProcessLevelCache(ttl_seconds=60, max_size=4)
        import pandas as pd

        cache_a.set("k1", pd.DataFrame({"a": [1]}))
        cache_b.set("k2", pd.DataFrame({"b": [2]}))
        register_process_cache("_test_a", cache_a, "test A")
        register_process_cache("_test_b", cache_b, "test B")

        try:
            cleared = emergency_clear_all_process_caches()
            assert cleared >= 2
            assert cache_a.get("k1") is None
            assert cache_b.get("k2") is None
        finally:
            _PROCESS_CACHE_REGISTRY.pop("_test_a", None)
            _PROCESS_CACHE_REGISTRY.pop("_test_b", None)

    def test_returns_zero_when_no_caches(self):
        saved = dict(_PROCESS_CACHE_REGISTRY)
        _PROCESS_CACHE_REGISTRY.clear()
        try:
            assert emergency_clear_all_process_caches() == 0
        finally:
            _PROCESS_CACHE_REGISTRY.update(saved)


# ============================================================
# Test: Auto-detect limit
# ============================================================

class TestAutoDetectLimit:
    def test_auto_detect_with_psutil(self):
        from mes_dashboard.core.worker_memory_guard import _auto_detect_limit_mb

        with patch.dict("os.environ", {"GUNICORN_WORKERS": "2"}):
            with patch("psutil.virtual_memory") as mock_vm:
                mock_vm.return_value = MagicMock(total=8 * 1024**3)  # 8 GB
                limit = _auto_detect_limit_mb()
                # 8192 / 2 * 0.8 = 3276
                assert limit == 3276

    def test_auto_detect_single_worker(self):
        from mes_dashboard.core.worker_memory_guard import _auto_detect_limit_mb

        with patch.dict("os.environ", {"GUNICORN_WORKERS": "1"}):
            with patch("psutil.virtual_memory") as mock_vm:
                mock_vm.return_value = MagicMock(total=4 * 1024**3)  # 4 GB
                limit = _auto_detect_limit_mb()
                # 4096 / 1 * 0.8 = 3276
                assert limit == 3276

    def test_auto_detect_fallback_on_psutil_error(self):
        from mes_dashboard.core.worker_memory_guard import _auto_detect_limit_mb

        with patch.dict("os.environ", {"GUNICORN_WORKERS": "2"}):
            with patch("psutil.virtual_memory", side_effect=Exception("no psutil")):
                limit = _auto_detect_limit_mb()
                # fallback 8192 / 2 * 0.8 = 3276
                assert limit == 3276

    def test_explicit_limit_overrides_auto(self):
        from mes_dashboard.core.worker_memory_guard import _resolve_limit_mb

        with patch(
            "mes_dashboard.core.worker_memory_guard._RSS_LIMIT_MB", 2048
        ):
            assert _resolve_limit_mb() == 2048


# ============================================================
# Test: Guard graduated response
# ============================================================

class TestGuardGraduatedResponse:
    def _make_guard(self, limit_mb=1000):
        from mes_dashboard.core.worker_memory_guard import _WorkerMemoryGuard, _telemetry

        _telemetry.warn_count = 0
        _telemetry.evict_count = 0
        _telemetry.restart_count = 0
        _telemetry.last_level = "normal"
        guard = _WorkerMemoryGuard(
            limit_mb=limit_mb,
            warn_ratio=0.70,
            evict_ratio=0.85,
            hard_ratio=0.95,
            interval=15,
            cooldown=120,
        )
        return guard

    def test_normal_no_action(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        guard = self._make_guard(1000)
        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb", return_value=500.0
        ):
            guard._check_rss()
        assert _telemetry.last_level == "normal"
        assert _telemetry.warn_count == 0

    def test_warn_threshold_logs_no_eviction(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        guard = self._make_guard(1000)
        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb", return_value=750.0
        ):
            guard._check_rss()
        assert _telemetry.last_level == "warn"
        assert _telemetry.warn_count == 1
        assert _telemetry.evict_count == 0

    def test_evict_threshold_clears_caches(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        guard = self._make_guard(1000)
        # Mock psutil to report safe system memory (<85%) so _check_system_memory()
        # does not trigger a second eviction alongside the RSS eviction.
        mock_vmem = MagicMock()
        mock_vmem.percent = 50.0
        mock_vmem.available = 8 * 1024 ** 3  # 8 GB free
        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb",
            side_effect=[880.0, 600.0],  # before evict, after evict
        ):
            with patch(
                "mes_dashboard.core.cache.emergency_clear_all_process_caches",
                return_value=3,
            ) as mock_clear:
                with patch("psutil.virtual_memory", return_value=mock_vmem):
                    guard._check_rss()

        assert _telemetry.last_level == "evict"
        assert _telemetry.evict_count == 1
        mock_clear.assert_called_once()

    def test_hard_threshold_sends_sigterm(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        guard = self._make_guard(1000)
        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb",
            return_value=960.0,  # stays high after eviction
        ):
            with patch(
                "mes_dashboard.core.cache.emergency_clear_all_process_caches",
                return_value=3,
            ):
                with patch("os.kill") as mock_kill:
                    guard._check_rss()

        assert _telemetry.last_level == "restart"
        assert _telemetry.restart_count == 1
        import os
        import signal

        mock_kill.assert_called_once_with(os.getpid(), signal.SIGTERM)

    def test_restart_cooldown_prevents_rapid_restart(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        guard = self._make_guard(1000)
        guard._last_restart_at = time.time()  # just restarted

        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb",
            return_value=960.0,
        ):
            with patch(
                "mes_dashboard.core.cache.emergency_clear_all_process_caches",
                return_value=0,
            ):
                with patch("os.kill") as mock_kill:
                    guard._check_rss()

        # Should NOT restart due to cooldown
        mock_kill.assert_not_called()
        # But eviction still happens
        assert _telemetry.evict_count == 1

    def test_psutil_unavailable_no_crash(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        guard = self._make_guard(1000)
        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb", return_value=None
        ):
            guard._check_rss()
        # Should not change state
        assert _telemetry.last_level == "normal"


# ============================================================
# Test: Guard disabled
# ============================================================

class TestGuardDisabled:
    def test_disabled_guard_does_not_start(self):
        from mes_dashboard.core import worker_memory_guard as mod

        with patch.object(mod, "_GUARD_ENABLED", False):
            with patch.object(mod, "_guard", None):
                mod.start_worker_memory_guard()
                assert mod._guard is None

    def test_stop_when_no_guard(self):
        from mes_dashboard.core import worker_memory_guard as mod

        with patch.object(mod, "_guard", None):
            mod.stop_worker_memory_guard()  # should not raise


# ============================================================
# Test: Telemetry
# ============================================================

class TestTelemetry:
    def test_telemetry_dict_structure(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.limit_mb = 2048
        _telemetry.last_rss_mb = 1024.5
        _telemetry.rss_pct = 50.0
        _telemetry.last_level = "normal"
        _telemetry.warn_count = 3
        _telemetry.evict_count = 1
        _telemetry.restart_count = 0

        d = _telemetry.to_dict()
        assert d["limit_mb"] == 2048
        assert d["last_rss_mb"] == 1024.5
        assert d["rss_pct"] == 50.0
        assert d["level"] == "normal"
        assert d["warn_count"] == 3
        assert d["evict_count"] == 1
        assert d["restart_count"] == 0
        assert "check_interval" in d
        assert "enabled" in d
        assert d["process_memory"]["rss_mb"] == 1024.5
        assert d["process_memory"]["limit_mb"] == 2048
        assert d["process_memory"]["level"] == "normal"

    def test_telemetry_dict_includes_nested_system_memory_breakdown(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.system_memory_pressure = True
        _telemetry.system_mem_used_pct = 96.2
        _telemetry.system_mem_available_mb = 256.0
        _telemetry.system_mem_total_mb = 32768.0

        d = _telemetry.to_dict()

        assert d["system_mem_total_mb"] == 32768.0
        assert d["system_memory"]["pressure"] is True
        assert d["system_memory"]["pressure_state"] == "critical"
        assert d["system_memory"]["used_pct"] == pytest.approx(96.2, abs=0.1)
        assert d["system_memory"]["available_mb"] == pytest.approx(256.0, abs=1.0)
        assert d["system_memory"]["total_mb"] == pytest.approx(32768.0, abs=1.0)
        assert d["system_memory"]["used_mb"] == pytest.approx(32512.0, abs=1.0)

    def test_telemetry_dict_includes_service_memory_breakdown(self):
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.service_rss_bytes = 3145728000
        _telemetry.service_rss_mb = 3000.0
        _telemetry.service_process_count = 5
        _telemetry.service_gunicorn_rss_mb = 2500.0
        _telemetry.service_gunicorn_process_count = 3
        _telemetry.service_rq_rss_mb = 500.0
        _telemetry.service_rq_process_count = 2

        d = _telemetry.to_dict()

        assert d["service_rss_bytes"] == 3145728000
        assert d["service_rss_mb"] == pytest.approx(3000.0, abs=0.1)
        assert d["service_memory"]["rss_mb"] == pytest.approx(3000.0, abs=0.1)
        assert d["service_memory"]["process_count"] == 5
        assert d["service_memory"]["gunicorn_rss_mb"] == pytest.approx(2500.0, abs=0.1)
        assert d["service_memory"]["gunicorn_process_count"] == 3
        assert d["service_memory"]["rq_rss_mb"] == pytest.approx(500.0, abs=0.1)
        assert d["service_memory"]["rq_process_count"] == 2

    def test_get_memory_guard_telemetry_returns_dict(self):
        from mes_dashboard.core.worker_memory_guard import get_memory_guard_telemetry

        with patch(
            "mes_dashboard.core.worker_memory_guard.get_service_memory_snapshot",
            return_value={
                "total_rss_bytes": 2097152000,
                "total_rss_mb": 2000.0,
                "total_process_count": 4,
                "gunicorn_rss_mb": 1500.0,
                "gunicorn_process_count": 3,
                "rq_rss_mb": 500.0,
                "rq_process_count": 1,
            },
        ):
            t = get_memory_guard_telemetry()

        assert isinstance(t, dict)
        assert "enabled" in t
        assert "level" in t
        assert t["service_memory"]["rss_mb"] == pytest.approx(2000.0, abs=0.1)
        assert t["service_memory"]["process_count"] == 4


# ============================================================
# Test: Guard lifecycle (start/stop)
# ============================================================

class TestGuardLifecycle:
    def test_start_and_stop(self):
        from mes_dashboard.core import worker_memory_guard as mod

        original_guard = mod._guard
        try:
            mod._guard = None
            with patch.object(mod, "_GUARD_ENABLED", True):
                with patch.object(mod, "_resolve_limit_mb", return_value=2048):
                    mod.start_worker_memory_guard()
                    assert mod._guard is not None
                    assert mod._guard._thread.is_alive()

                    mod.stop_worker_memory_guard()
                    assert mod._guard is None
        finally:
            mod._guard = original_guard

    def test_double_start_is_idempotent(self):
        from mes_dashboard.core import worker_memory_guard as mod

        original_guard = mod._guard
        try:
            mod._guard = None
            with patch.object(mod, "_GUARD_ENABLED", True):
                with patch.object(mod, "_resolve_limit_mb", return_value=2048):
                    mod.start_worker_memory_guard()
                    first_guard = mod._guard
                    mod.start_worker_memory_guard()
                    assert mod._guard is first_guard  # same instance

                    mod.stop_worker_memory_guard()
        finally:
            mod._guard = original_guard
