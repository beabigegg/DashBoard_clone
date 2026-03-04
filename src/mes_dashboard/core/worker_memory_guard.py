# -*- coding: utf-8 -*-
"""Worker RSS memory guard — prevent OOM by graduated response.

Background daemon thread that periodically checks current process RSS
and takes graduated action:
  1. Warning  (>70% limit): log warning, increment telemetry counter
  2. Eviction (>85% limit): emergency-clear all ProcessLevelCache + gc.collect()
  3. Restart  (>95% limit): SIGTERM self for gunicorn graceful restart
"""

from __future__ import annotations

import gc
import logging
import os
import signal
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("mes_dashboard.worker_memory_guard")


# ============================================================
# Configuration (env vars)
# ============================================================

def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


_GUARD_ENABLED = _bool_env("WORKER_RSS_GUARD_ENABLED", True)
_RSS_LIMIT_MB = _int_env("WORKER_RSS_LIMIT_MB", 0)  # 0 = auto-detect
_WARN_RATIO = _float_env("WORKER_RSS_WARN_RATIO", 0.70)
_EVICT_RATIO = _float_env("WORKER_RSS_EVICT_RATIO", 0.85)
_HARD_RATIO = _float_env("WORKER_RSS_HARD_RATIO", 0.95)
_CHECK_INTERVAL = _int_env("WORKER_RSS_CHECK_INTERVAL", 15)
_RESTART_COOLDOWN = _int_env("WORKER_RSS_RESTART_COOLDOWN", 120)


# ============================================================
# RSS Limit Auto-Detection
# ============================================================

def _auto_detect_limit_mb() -> int:
    """Compute per-worker RSS limit: total_mem / num_workers * 0.8."""
    try:
        import psutil
        total_mb = psutil.virtual_memory().total / (1024 * 1024)
    except Exception:
        total_mb = 8192  # fallback: assume 8 GB
    num_workers = max(_int_env("GUNICORN_WORKERS", 2), 1)
    limit = int(total_mb / num_workers * 0.8)
    return max(limit, 256)  # floor at 256 MB


def _resolve_limit_mb() -> int:
    if _RSS_LIMIT_MB > 0:
        return _RSS_LIMIT_MB
    return _auto_detect_limit_mb()


# ============================================================
# Current RSS Measurement
# ============================================================

def _current_rss_mb() -> Optional[float]:
    """Return current process RSS in MB via psutil (not peak)."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        return None


# ============================================================
# Telemetry
# ============================================================

class _Telemetry:
    __slots__ = (
        "warn_count", "evict_count", "restart_count",
        "last_rss_mb", "last_check_at", "last_level",
        "limit_mb", "rss_pct",
    )

    def __init__(self) -> None:
        self.warn_count: int = 0
        self.evict_count: int = 0
        self.restart_count: int = 0
        self.last_rss_mb: float = 0.0
        self.last_check_at: float = 0.0
        self.last_level: str = "normal"
        self.limit_mb: int = 0
        self.rss_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": _GUARD_ENABLED,
            "limit_mb": self.limit_mb,
            "last_rss_mb": round(self.last_rss_mb, 1),
            "rss_pct": round(self.rss_pct, 1),
            "level": self.last_level,
            "warn_count": self.warn_count,
            "evict_count": self.evict_count,
            "restart_count": self.restart_count,
            "check_interval": _CHECK_INTERVAL,
        }


_telemetry = _Telemetry()


# ============================================================
# Guard Implementation
# ============================================================

class _WorkerMemoryGuard:
    """Background daemon thread that monitors RSS and takes graduated action."""

    def __init__(
        self,
        limit_mb: int,
        warn_ratio: float = 0.70,
        evict_ratio: float = 0.85,
        hard_ratio: float = 0.95,
        interval: int = 15,
        cooldown: int = 120,
    ):
        self._limit_mb = limit_mb
        self._warn_mb = limit_mb * warn_ratio
        self._evict_mb = limit_mb * evict_ratio
        self._hard_mb = limit_mb * hard_ratio
        self._interval = max(interval, 5)
        self._cooldown = cooldown
        self._last_restart_at: float = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        _telemetry.limit_mb = limit_mb

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="worker-rss-guard",
        )
        self._thread.start()
        logger.info(
            "Worker RSS guard started (limit=%d MB, warn=%.0f%%, evict=%.0f%%, "
            "hard=%.0f%%, interval=%ds, cooldown=%ds)",
            self._limit_mb,
            self._warn_mb / self._limit_mb * 100,
            self._evict_mb / self._limit_mb * 100,
            self._hard_mb / self._limit_mb * 100,
            self._interval,
            self._cooldown,
        )

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=5)
            logger.info("Worker RSS guard stopped")

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._check_rss()
            except Exception as exc:
                logger.debug("RSS guard check error: %s", exc)

    def _check_rss(self) -> None:
        rss_mb = _current_rss_mb()
        if rss_mb is None:
            return

        now = time.time()
        pct = rss_mb / self._limit_mb * 100 if self._limit_mb > 0 else 0

        _telemetry.last_rss_mb = rss_mb
        _telemetry.last_check_at = now
        _telemetry.rss_pct = pct

        # --- Level 1: Normal ---
        if rss_mb < self._warn_mb:
            _telemetry.last_level = "normal"
            return

        # --- Level 2: Warning ---
        if rss_mb < self._evict_mb:
            _telemetry.last_level = "warn"
            _telemetry.warn_count += 1
            logger.warning(
                "Worker RSS %.0f MB (%.0f%% of %d MB limit)",
                rss_mb, pct, self._limit_mb,
            )
            return

        # --- Level 3: Eviction ---
        _telemetry.last_level = "evict"
        _telemetry.evict_count += 1
        logger.warning(
            "Worker RSS %.0f MB (%.0f%%) exceeds eviction threshold (%.0f MB), "
            "clearing all process caches",
            rss_mb, pct, self._evict_mb,
        )
        from mes_dashboard.core.cache import emergency_clear_all_process_caches
        cleared = emergency_clear_all_process_caches()
        gc.collect()
        logger.info("Emergency eviction cleared %d cache(s), gc.collect() done", cleared)

        # Recheck after eviction + GC
        rss_after = _current_rss_mb()
        if rss_after is not None:
            _telemetry.last_rss_mb = rss_after
            _telemetry.rss_pct = rss_after / self._limit_mb * 100 if self._limit_mb > 0 else 0
            logger.info(
                "Post-eviction RSS: %.0f MB (was %.0f MB, freed ~%.0f MB)",
                rss_after, rss_mb, rss_mb - rss_after,
            )
            rss_mb = rss_after

        # --- Level 4: Hard restart ---
        if rss_mb >= self._hard_mb:
            elapsed = now - self._last_restart_at
            if elapsed < self._cooldown:
                logger.warning(
                    "RSS %.0f MB exceeds hard limit (%.0f MB) but restart cooldown "
                    "active (%.0fs remaining), skipping restart",
                    rss_mb, self._hard_mb, self._cooldown - elapsed,
                )
                return

            _telemetry.last_level = "restart"
            _telemetry.restart_count += 1
            self._last_restart_at = now
            logger.critical(
                "Worker RSS %.0f MB (%.0f%%) exceeds hard limit (%.0f MB), "
                "sending SIGTERM for graceful restart (pid=%d)",
                rss_mb, _telemetry.rss_pct, self._hard_mb, os.getpid(),
            )
            os.kill(os.getpid(), signal.SIGTERM)


# ============================================================
# Global Lifecycle
# ============================================================

_guard: Optional[_WorkerMemoryGuard] = None


def start_worker_memory_guard() -> None:
    """Start the RSS memory guard (call from create_app)."""
    global _guard
    if not _GUARD_ENABLED:
        logger.info("Worker RSS guard disabled (WORKER_RSS_GUARD_ENABLED=false)")
        return
    if _guard is not None:
        return
    limit_mb = _resolve_limit_mb()
    _guard = _WorkerMemoryGuard(
        limit_mb=limit_mb,
        warn_ratio=_WARN_RATIO,
        evict_ratio=_EVICT_RATIO,
        hard_ratio=_HARD_RATIO,
        interval=_CHECK_INTERVAL,
        cooldown=_RESTART_COOLDOWN,
    )
    _guard.start()


def stop_worker_memory_guard() -> None:
    """Stop the RSS memory guard (call from worker_exit)."""
    global _guard
    if _guard is not None:
        _guard.stop()
        _guard = None


def get_memory_guard_telemetry() -> Dict[str, Any]:
    """Return current guard state for admin telemetry and health checks."""
    return _telemetry.to_dict()
