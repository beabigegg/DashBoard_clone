# -*- coding: utf-8 -*-
"""Cache for ERP scrap reasons excluded from yield calculations.

Policy source: DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE (ENABLE_FLAG='Y').
Cache strategy:
- L2 Redis shared cache when available
- L1 process memory cache fallback
- Daily full-table refresh (default every 24 hours)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Iterable

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import get_key, get_redis_client, try_acquire_lock, release_lock

logger = logging.getLogger("mes_dashboard.scrap_reason_exclusion_cache")

_REFRESH_SECONDS = max(int(os.getenv("SCRAP_REASON_EXCLUSION_REFRESH_SECONDS", "86400")), 60)
_REDIS_DATA_KEY = get_key("scrap_exclusion:enabled_reasons")
_REDIS_META_KEY = get_key("scrap_exclusion:updated_at")
_LOCK_NAME = "scrap_reason_exclusion_cache_refresh"

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, object] = {
    "reasons": set(),
    "updated_at": None,
    "loaded": False,
    "source": None,
}

_WORKER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()


def _normalize_reason(value: object) -> str:
    return str(value or "").strip().upper()


def _extract_reason_codes(values: Iterable[object]) -> set[str]:
    normalized = {_normalize_reason(v) for v in values}
    normalized.discard("")
    return normalized


def _load_from_redis() -> tuple[set[str], str | None] | None:
    client = get_redis_client()
    if client is None:
        return None

    try:
        raw = client.get(_REDIS_DATA_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        reasons = _extract_reason_codes(data)
        updated = client.get(_REDIS_META_KEY)
        if not reasons:
            return None
        return reasons, updated
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read scrap exclusion cache from Redis: %s", exc)
        return None


def _save_to_redis(reasons: set[str], updated_at: str) -> None:
    client = get_redis_client()
    if client is None:
        return

    try:
        payload = json.dumps(sorted(reasons), ensure_ascii=False)
        # Keep redis key slightly longer than refresh interval to cover worker restarts.
        ttl = int(_REFRESH_SECONDS * 1.5)
        client.setex(_REDIS_DATA_KEY, ttl, payload)
        client.setex(_REDIS_META_KEY, ttl, updated_at)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to write scrap exclusion cache to Redis: %s", exc)


def _read_enabled_reasons_from_oracle() -> set[str]:
    sql = """
        SELECT TRIM(REASON_NAME) AS REASON_NAME
        FROM DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE
        WHERE NVL(ENABLE_FLAG, 'N') = 'Y'
    """
    df = read_sql_df(sql)
    if df is None or df.empty:
        return set()
    return _extract_reason_codes(df.get("REASON_NAME", []))


def _set_local_cache(reasons: set[str], *, source: str, updated_at: str) -> None:
    with _CACHE_LOCK:
        _CACHE["reasons"] = set(reasons)
        _CACHE["updated_at"] = updated_at
        _CACHE["loaded"] = True
        _CACHE["source"] = source


def _seconds_since_update() -> float:
    with _CACHE_LOCK:
        updated_at = _CACHE.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        return float("inf")
    try:
        dt = datetime.fromisoformat(updated_at)
        return max((datetime.now() - dt).total_seconds(), 0.0)
    except ValueError:
        return float("inf")


def refresh_cache(force: bool = False) -> bool:
    """Refresh exclusion policy cache from Oracle.

    Returns:
        True if cache contains usable data after refresh attempt.
    """
    if not force and _seconds_since_update() < _REFRESH_SECONDS:
        return True

    # Cross-worker lock (fail-closed when Redis unavailable — serve stale data).
    if not try_acquire_lock(_LOCK_NAME, ttl_seconds=120, fail_mode="closed"):
        logger.debug("Scrap exclusion cache refresh skipped (lock held by another worker)")
        with _CACHE_LOCK:
            return bool(_CACHE.get("loaded"))

    try:
        reasons = _read_enabled_reasons_from_oracle()
        updated_at = datetime.now().isoformat()
        _set_local_cache(reasons, source="oracle", updated_at=updated_at)
        _save_to_redis(reasons, updated_at)
        logger.info("Scrap exclusion cache refreshed: %s reasons", len(reasons))
        return True
    except Exception as exc:
        # Fallback to Redis payload if local refresh fails.
        redis_payload = _load_from_redis()
        if redis_payload is not None:
            reasons, updated = redis_payload
            _set_local_cache(reasons, source="redis", updated_at=updated or datetime.now().isoformat())
            logger.warning("Scrap exclusion cache fallback to Redis: %s", exc)
            return True

        with _CACHE_LOCK:
            loaded = bool(_CACHE.get("loaded"))
        logger.error("Scrap exclusion cache refresh failed: %s", exc)
        return loaded
    finally:
        release_lock(_LOCK_NAME)


def get_excluded_reasons(force_refresh: bool = False) -> set[str]:
    """Get currently cached exclusion reason codes."""
    with _CACHE_LOCK:
        loaded = bool(_CACHE.get("loaded"))
        reasons = set(_CACHE.get("reasons", set()))

    if force_refresh:
        refresh_cache(force=True)
    elif not loaded:
        # Try Redis before Oracle for fast startup in secondary workers.
        redis_payload = _load_from_redis()
        if redis_payload is not None:
            redis_reasons, updated = redis_payload
            _set_local_cache(
                redis_reasons,
                source="redis",
                updated_at=updated or datetime.now().isoformat(),
            )
            return redis_reasons
        refresh_cache(force=True)
    elif _seconds_since_update() >= _REFRESH_SECONDS:
        refresh_cache(force=True)

    with _CACHE_LOCK:
        return set(_CACHE.get("reasons", set()))


def get_cache_status() -> dict[str, object]:
    """Expose cache diagnostics for health/admin pages."""
    with _CACHE_LOCK:
        return {
            "loaded": bool(_CACHE.get("loaded")),
            "updated_at": _CACHE.get("updated_at"),
            "source": _CACHE.get("source"),
            "reason_count": len(_CACHE.get("reasons", set())),
            "refresh_interval_seconds": _REFRESH_SECONDS,
        }


def _worker_loop() -> None:
    logger.info("Scrap exclusion sync worker started (interval: %ss)", _REFRESH_SECONDS)
    while not _STOP_EVENT.is_set():
        try:
            refresh_cache(force=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Scrap exclusion worker refresh failed: %s", exc)
        _STOP_EVENT.wait(_REFRESH_SECONDS)
    logger.info("Scrap exclusion sync worker stopped")


def init_scrap_reason_exclusion_cache(app=None) -> None:
    """Initialize cache and start background sync worker."""
    refresh_cache(force=False)

    global _WORKER_THREAD
    if app is not None and app.config.get("TESTING"):
        return

    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return

    _STOP_EVENT.clear()
    _WORKER_THREAD = threading.Thread(
        target=_worker_loop,
        daemon=True,
        name="scrap-exclusion-cache-sync",
    )
    _WORKER_THREAD.start()


def stop_scrap_reason_exclusion_cache_worker(timeout: int = 5) -> None:
    global _WORKER_THREAD
    if not _WORKER_THREAD:
        return
    _STOP_EVENT.set()
    _WORKER_THREAD.join(timeout=timeout)
    _WORKER_THREAD = None
