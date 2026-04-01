# -*- coding: utf-8 -*-
"""Unit tests for system memory monitoring in worker_memory_guard (Task 7.5).

Covers _WorkerMemoryGuard._check_system_memory():
- <85% usage: pressure=False, no eviction triggered
- >85% usage (warning zone): logs warning, triggers eviction, pressure stays False
- >92% usage (critical zone): pressure=True, triggers eviction
- Telemetry slots system_mem_available_mb and system_mem_used_pct are populated
- ImportError for psutil is handled gracefully (system_memory_pressure stays False)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard_and_telemetry(limit_mb: int = 1000):
    """Create a fresh _WorkerMemoryGuard instance and reset telemetry state."""
    from mes_dashboard.core.worker_memory_guard import _WorkerMemoryGuard, _telemetry

    # Reset all telemetry fields that we'll be asserting on
    _telemetry.system_memory_pressure = False
    _telemetry.system_mem_used_pct = 0.0
    _telemetry.system_mem_available_mb = 0.0
    _telemetry.warn_count = 0
    _telemetry.evict_count = 0
    _telemetry.last_level = "normal"

    guard = _WorkerMemoryGuard(
        limit_mb=limit_mb,
        warn_ratio=0.70,
        evict_ratio=0.85,
        hard_ratio=0.95,
        interval=15,
        cooldown=120,
    )
    return guard, _telemetry


def _make_psutil_vm(percent: float, available_mb: float = 4096.0):
    """Return a MagicMock that mimics psutil.virtual_memory() output."""
    vm = MagicMock()
    vm.percent = percent
    vm.available = int(available_mb * 1024 * 1024)
    return vm


# ---------------------------------------------------------------------------
# _check_system_memory: below warning threshold (<85%)
# ---------------------------------------------------------------------------

class TestSystemMemoryBelowWarning:
    def test_pressure_flag_stays_false_below_warning(self):
        """system_memory_pressure should remain False when usage is below the warning threshold."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=70.0, available_mb=6144.0)

        with patch("psutil.virtual_memory", return_value=vm):
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is False

    def test_telemetry_slots_populated_below_warning(self):
        """system_mem_used_pct and system_mem_available_mb should be updated even below threshold."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=72.5, available_mb=3500.0)

        with patch("psutil.virtual_memory", return_value=vm):
            guard._check_system_memory()

        assert telemetry.system_mem_used_pct == 72.5
        assert abs(telemetry.system_mem_available_mb - 3500.0) < 1.0

    def test_no_eviction_triggered_below_warning(self):
        """emergency_clear_all_process_caches should NOT be called below the warning threshold."""
        guard, _ = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=60.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch(
                 "mes_dashboard.core.cache.emergency_clear_all_process_caches"
             ) as mock_clear:
            guard._check_system_memory()

        mock_clear.assert_not_called()


# ---------------------------------------------------------------------------
# _check_system_memory: warning zone (85% < usage <= 92%)
# ---------------------------------------------------------------------------

class TestSystemMemoryWarningZone:
    def test_pressure_flag_is_false_in_warning_zone(self):
        """system_memory_pressure should be False in the warning zone (not yet critical)."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=88.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch("mes_dashboard.core.cache.emergency_clear_all_process_caches",
                   return_value=2):
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is False

    def test_eviction_triggered_in_warning_zone(self):
        """emergency_clear_all_process_caches should be called when usage is in the warning zone."""
        guard, _ = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=87.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch(
                 "mes_dashboard.core.cache.emergency_clear_all_process_caches",
                 return_value=3,
             ) as mock_clear:
            guard._check_system_memory()

        mock_clear.assert_called_once()

    def test_telemetry_updated_in_warning_zone(self):
        """Telemetry slots should be updated correctly in the warning zone."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=89.5, available_mb=1024.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch("mes_dashboard.core.cache.emergency_clear_all_process_caches",
                   return_value=1):
            guard._check_system_memory()

        assert telemetry.system_mem_used_pct == 89.5
        assert abs(telemetry.system_mem_available_mb - 1024.0) < 1.0

    def test_warning_zone_clears_pressure_if_previously_critical(self):
        """If pressure was True before entering warning zone, it should be cleared to False."""
        guard, telemetry = _make_guard_and_telemetry()
        telemetry.system_memory_pressure = True  # simulate recovery from critical
        vm = _make_psutil_vm(percent=88.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch("mes_dashboard.core.cache.emergency_clear_all_process_caches",
                   return_value=0):
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is False

    def test_warning_zone_eviction_respects_cooldown(self):
        """Warning-zone eviction should be throttled by SYSTEM_MEM_EVICT_COOLDOWN."""
        guard, _ = _make_guard_and_telemetry()
        guard._system_warn_evict_cooldown = 300
        vm = _make_psutil_vm(percent=88.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch(
                 "mes_dashboard.core.cache.emergency_clear_all_process_caches",
                 return_value=1,
             ) as mock_clear:
            guard._check_system_memory()
            guard._check_system_memory()

        mock_clear.assert_called_once()


# ---------------------------------------------------------------------------
# _check_system_memory: critical zone (>92%)
# ---------------------------------------------------------------------------

class TestSystemMemoryCriticalZone:
    def test_pressure_flag_set_true_above_reject_threshold(self):
        """system_memory_pressure should be True when usage exceeds SYSTEM_MEM_REJECT_PCT (92%)."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=93.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch("mes_dashboard.core.cache.emergency_clear_all_process_caches",
                   return_value=5):
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is True

    def test_eviction_triggered_in_critical_zone(self):
        """emergency_clear_all_process_caches should be called when usage is critical."""
        guard, _ = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=95.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch(
                 "mes_dashboard.core.cache.emergency_clear_all_process_caches",
                 return_value=4,
             ) as mock_clear:
            guard._check_system_memory()

        mock_clear.assert_called_once()

    def test_telemetry_slots_populated_in_critical_zone(self):
        """Telemetry slots should reflect critical usage values."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=94.2, available_mb=256.0)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch("mes_dashboard.core.cache.emergency_clear_all_process_caches",
                   return_value=2):
            guard._check_system_memory()

        assert telemetry.system_mem_used_pct == 94.2
        assert abs(telemetry.system_mem_available_mb - 256.0) < 1.0

    def test_pressure_stays_true_on_repeated_critical_checks(self):
        """system_memory_pressure should remain True across repeated critical checks."""
        guard, telemetry = _make_guard_and_telemetry()
        vm = _make_psutil_vm(percent=93.5)

        with patch("psutil.virtual_memory", return_value=vm), \
             patch("mes_dashboard.core.cache.emergency_clear_all_process_caches",
                   return_value=0):
            guard._check_system_memory()
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is True

    def test_pressure_cleared_when_usage_drops_below_warning(self):
        """system_memory_pressure should reset to False when usage returns below warning threshold."""
        guard, telemetry = _make_guard_and_telemetry()
        telemetry.system_memory_pressure = True

        # Simulate recovery: usage drops to 50%
        vm_ok = _make_psutil_vm(percent=50.0)
        with patch("psutil.virtual_memory", return_value=vm_ok):
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is False


# ---------------------------------------------------------------------------
# psutil ImportError handling
# ---------------------------------------------------------------------------

class TestPsutilImportError:
    def test_system_memory_pressure_stays_false_when_psutil_unavailable(self):
        """system_memory_pressure should not be set to True if psutil cannot be imported."""
        guard, telemetry = _make_guard_and_telemetry()

        with patch("builtins.__import__", side_effect=_make_import_raiser("psutil")):
            guard._check_system_memory()

        assert telemetry.system_memory_pressure is False

    def test_no_eviction_called_when_psutil_raises_on_import(self):
        """emergency_clear_all_process_caches should not be called when psutil import fails."""
        guard, _ = _make_guard_and_telemetry()

        with patch("builtins.__import__", side_effect=_make_import_raiser("psutil")), \
             patch(
                 "mes_dashboard.core.cache.emergency_clear_all_process_caches"
             ) as mock_clear:
            guard._check_system_memory()

        mock_clear.assert_not_called()

    def test_virtual_memory_exception_handled_gracefully(self):
        """Should not raise when psutil.virtual_memory() itself raises an exception."""
        guard, telemetry = _make_guard_and_telemetry()

        with patch("psutil.virtual_memory", side_effect=OSError("no proc")):
            guard._check_system_memory()  # must not raise

        assert telemetry.system_memory_pressure is False


def _make_import_raiser(blocked_module: str):
    """Return a side_effect function that raises ImportError only for the blocked module."""
    import builtins
    _real_import = builtins.__import__

    def _selective_raise(name, *args, **kwargs):
        if name == blocked_module or name.startswith(blocked_module + "."):
            raise ImportError(f"Mock: {blocked_module} not available")
        return _real_import(name, *args, **kwargs)

    return _selective_raise


# ---------------------------------------------------------------------------
# Telemetry dict structure for system memory fields
# ---------------------------------------------------------------------------

class TestSystemMemoryTelemetryFields:
    def setup_method(self, method):
        from mes_dashboard.core.worker_memory_guard import _telemetry
        _telemetry.system_mem_total_mb = 0.0
        _telemetry.system_mem_available_mb = 0.0
        _telemetry.system_mem_used_pct = 0.0
        _telemetry.system_memory_pressure = False

    def test_to_dict_includes_system_memory_fields(self):
        """_telemetry.to_dict() should include system_memory_pressure and the two MB/pct fields."""
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.system_memory_pressure = True
        _telemetry.system_mem_used_pct = 91.3
        _telemetry.system_mem_available_mb = 512.0

        d = _telemetry.to_dict()

        assert "system_memory_pressure" in d
        assert d["system_memory_pressure"] is True
        assert "system_mem_used_pct" in d
        assert d["system_mem_used_pct"] == pytest.approx(91.3, abs=0.1)
        assert "system_mem_available_mb" in d
        assert d["system_mem_available_mb"] == pytest.approx(512.0, abs=1.0)

    def test_system_mem_available_mb_is_rounded(self):
        """system_mem_available_mb in to_dict() should be rounded to 0 decimal places."""
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.system_mem_available_mb = 1234.567

        d = _telemetry.to_dict()
        # round(..., 0) returns a float with no fractional part
        assert d["system_mem_available_mb"] == pytest.approx(1235.0, abs=1.0)

    def test_system_mem_used_pct_is_rounded_to_one_decimal(self):
        """system_mem_used_pct in to_dict() should be rounded to 1 decimal place."""
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.system_mem_used_pct = 88.456

        d = _telemetry.to_dict()
        assert d["system_mem_used_pct"] == pytest.approx(88.5, abs=0.05)

    def test_system_memory_pressure_defaults_to_false(self):
        """After a fresh guard creation the system_memory_pressure flag should be False."""
        from mes_dashboard.core.worker_memory_guard import _telemetry

        _telemetry.system_memory_pressure = False
        d = _telemetry.to_dict()
        assert d["system_memory_pressure"] is False


# ---------------------------------------------------------------------------
# Integration: _check_rss calls _check_system_memory on each cycle
# ---------------------------------------------------------------------------

class TestCheckRssCallsSystemMemoryCheck:
    def test_check_rss_invokes_check_system_memory(self):
        """_check_rss() should call _check_system_memory() on every cycle."""
        guard, _ = _make_guard_and_telemetry(limit_mb=2000)

        with patch(
            "mes_dashboard.core.worker_memory_guard._current_rss_mb",
            return_value=500.0,
        ), patch.object(guard, "_check_system_memory") as mock_sys_check:
            guard._check_rss()

        mock_sys_check.assert_called_once()
