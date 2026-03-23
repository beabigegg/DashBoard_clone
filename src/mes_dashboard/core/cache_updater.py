# -*- coding: utf-8 -*-
"""Background task for updating WIP and Resource cache from Oracle to Redis."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from mes_dashboard.core.redis_client import (
    get_redis_client,
    get_key,
    redis_available,
    REDIS_ENABLED,
    try_acquire_lock,
    release_lock,
)
from mes_dashboard.core.database import read_sql_df

logger = logging.getLogger('mes_dashboard.cache_updater')

# ============================================================
# Configuration
# ============================================================

CACHE_CHECK_INTERVAL = int(os.getenv('CACHE_CHECK_INTERVAL', '600'))  # 10 minutes
WIP_VIEW = "DWH.DW_MES_LOT_V"
WIP_CACHE_TTL_SECONDS = int(os.getenv('WIP_CACHE_TTL_SECONDS', '0'))

# Resource cache sync interval (default: 4 hours)
RESOURCE_SYNC_INTERVAL = int(os.getenv('RESOURCE_SYNC_INTERVAL', '14400'))

# ============================================================
# Cache Updater Class
# ============================================================


class CacheUpdater:
    """Background task that periodically checks SYS_DATE and updates cache."""

    def __init__(self, interval: int = CACHE_CHECK_INTERVAL):
        """Initialize cache updater.

        Args:
            interval: Check interval in seconds (default: 600)
        """
        self.interval = interval
        self.resource_sync_interval = RESOURCE_SYNC_INTERVAL
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._last_resource_sync: Optional[float] = None

    def start(self) -> None:
        """Start the background update thread."""
        if not REDIS_ENABLED:
            logger.info("Redis is disabled, cache updater will not start")
            return

        if self._thread is not None and self._thread.is_alive():
            logger.warning("Cache updater is already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="cache-updater"
        )
        self._thread.start()
        self._is_running = True
        logger.info(f"Cache updater started (interval: {self.interval}s)")

    def stop(self) -> None:
        """Stop the background update thread."""
        if self._thread is None or not self._thread.is_alive():
            return

        self._stop_event.set()
        self._thread.join(timeout=5)
        self._is_running = False
        logger.info("Cache updater stopped")

    def is_running(self) -> bool:
        """Check if the updater is running."""
        return self._is_running and self._thread is not None and self._thread.is_alive()

    def force_update(self) -> bool:
        """Force an immediate cache update.

        Returns:
            True if update was successful.
        """
        return self._check_and_update(force=True)

    def _worker(self) -> None:
        """Background worker that runs the update loop."""
        # Initial update on startup
        logger.info("Performing initial cache load...")
        self._check_and_update(force=True)

        # Initial resource cache load
        self._check_resource_update(force=True)
        self._run_dataset_warmups()

        # Periodic updates
        while not self._stop_event.wait(self.interval):
            try:
                self._check_and_update()
                self._check_resource_update()
                self._run_dataset_warmups()
            except Exception as e:
                logger.error(f"Cache update failed: {e}", exc_info=True)

    def _run_dataset_warmups(self) -> None:
        for warmup_name, warmup_fn in (
            ("reject_dataset", self._warmup_reject_dataset),
            ("yield_alert_dataset", self._warmup_yield_alert_dataset),
            ("reject_options", self._warmup_reject_options),
        ):
            try:
                warmup_fn()
            except Exception as exc:
                logger.warning("Warmup task failed (%s): %s", warmup_name, exc)

    def _check_and_update(self, force: bool = False) -> bool:
        """Check SYS_DATE and update cache if needed.

        Uses distributed lock to prevent multiple workers from updating simultaneously.

        Args:
            force: If True, update regardless of SYS_DATE.

        Returns:
            True if cache was updated.
        """
        if not redis_available():
            logger.warning("Redis not available, skipping cache update")
            return False

        # Try to acquire distributed lock (non-blocking)
        if not try_acquire_lock("wip_cache_update", ttl_seconds=120):
            logger.debug("Another worker is updating WIP cache, skipping")
            return False

        try:
            # Get current SYS_DATE from Oracle
            oracle_sys_date = self._check_sys_date()
            if oracle_sys_date is None:
                logger.error("Failed to get SYS_DATE from Oracle")
                return False

            # Get cached SYS_DATE from Redis
            cached_sys_date = self._get_cached_sys_date()

            # Compare and decide whether to update
            if not force and cached_sys_date == oracle_sys_date:
                logger.debug(f"SYS_DATE unchanged ({oracle_sys_date}), skipping update")
                return False

            logger.info(f"SYS_DATE changed: {cached_sys_date} -> {oracle_sys_date}, updating cache...")

            # Load full table and update Redis
            df = self._load_full_table()
            if df is None or df.empty:
                logger.error("Failed to load data from Oracle")
                return False

            success = self._update_redis_cache(df, oracle_sys_date)
            if success:
                logger.info(f"Cache updated successfully ({len(df)} rows)")
            return success

        except Exception as e:
            logger.error(f"Error in cache update: {e}", exc_info=True)
            return False
        finally:
            release_lock("wip_cache_update")

    def _check_sys_date(self) -> Optional[str]:
        """Query Oracle for MAX(SYS_DATE).

        Returns:
            SYS_DATE string or None if query failed.
        """
        sql = f"SELECT MAX(SYS_DATE) as SYS_DATE FROM {WIP_VIEW}"
        try:
            df = read_sql_df(sql, caller="cache_updater:_check_sys_date")
            if df is not None and not df.empty:
                sys_date = df.iloc[0]['SYS_DATE']
                return str(sys_date) if sys_date else None
            return None
        except Exception as e:
            logger.error(f"Failed to query SYS_DATE: {e}")
            return None

    def _get_cached_sys_date(self) -> Optional[str]:
        """Get cached SYS_DATE from Redis.

        Returns:
            Cached SYS_DATE string or None.
        """
        client = get_redis_client()
        if client is None:
            return None

        try:
            return client.get(get_key("meta:sys_date"))
        except Exception as e:
            logger.warning(f"Failed to get cached SYS_DATE: {e}")
            return None

    def _load_full_table(self) -> Optional[pd.DataFrame]:
        """Load entire DWH.DW_MES_LOT_V table from Oracle.

        Returns:
            DataFrame with all rows, or None if failed.
        """
        sql = f"""
            SELECT *
            FROM {WIP_VIEW}
            WHERE WORKORDER IS NOT NULL
        """
        try:
            df = read_sql_df(sql, caller="cache_updater:_load_full_table")
            return df
        except Exception as e:
            logger.error(f"Failed to load full table: {e}")
            return None

    def _update_redis_cache(self, df: pd.DataFrame, sys_date: str) -> bool:
        """Update Redis cache with staged publish for coherent snapshot visibility.

        Args:
            df: DataFrame with full table data.
            sys_date: Current SYS_DATE from Oracle.

        Returns:
            True if update was successful.
        """
        client = get_redis_client()
        if client is None:
            return False

        staging_key: str | None = None
        try:
            ttl_seconds = self._resolve_cache_ttl_seconds()
            # Convert DataFrame to JSON
            # Handle datetime columns
            df_copy = df.copy()
            for col in df_copy.select_dtypes(include=['datetime64']).columns:
                df_copy[col] = df_copy[col].astype(str)

            data_json = df_copy.to_json(orient='records', force_ascii=False)

            # Stage payload first, then atomically publish live key + metadata.
            now = datetime.now().isoformat()
            unique_suffix = f"{int(time.time() * 1000)}:{threading.get_ident()}"
            staging_key = get_key(f"data:staging:{unique_suffix}")

            pipe = client.pipeline()
            pipe.set(staging_key, data_json, ex=ttl_seconds)
            pipe.rename(staging_key, get_key("data"))
            pipe.set(get_key("meta:sys_date"), sys_date, ex=ttl_seconds)
            pipe.set(get_key("meta:updated_at"), now, ex=ttl_seconds)
            pipe.execute()

            # Dual-key: also store as Parquet for faster deserialization
            try:
                from mes_dashboard.core.redis_df_store import redis_store_df
                redis_store_df(get_key("data:parquet"), df_copy, ttl=ttl_seconds)
                logger.debug("WIP Parquet cache updated alongside JSON")
            except Exception as parquet_exc:
                logger.warning("WIP Parquet cache write failed (JSON still valid): %s", parquet_exc)

            return True
        except Exception as e:
            logger.error(f"Failed to update Redis cache: {e}")
            if staging_key:
                try:
                    client.delete(staging_key)
                except Exception:
                    pass
            return False

    def _resolve_cache_ttl_seconds(self) -> int:
        """Resolve Redis TTL for WIP snapshot keys.

        Default strategy: 3x sync interval to tolerate temporary sync gaps while
        preventing stale data from lingering forever when updater stops.
        """
        if WIP_CACHE_TTL_SECONDS > 0:
            return WIP_CACHE_TTL_SECONDS
        return max(int(self.interval) * 3, 60)

    def _check_resource_update(self, force: bool = False) -> bool:
        """Check and update resource cache if needed.

        Uses distributed lock to prevent multiple workers from updating simultaneously.

        Args:
            force: If True, update regardless of interval.

        Returns:
            True if cache was updated.
        """
        from mes_dashboard.services.resource_cache import (
            refresh_cache as refresh_resource_cache,
            RESOURCE_CACHE_ENABLED,
        )

        if not RESOURCE_CACHE_ENABLED:
            return False

        # Check if sync is needed based on interval
        now = time.time()
        if not force and self._last_resource_sync is not None:
            elapsed = now - self._last_resource_sync
            if elapsed < self.resource_sync_interval:
                logger.debug(
                    f"Resource sync not due yet ({elapsed:.0f}s < {self.resource_sync_interval}s)"
                )
                return False

        # Try to acquire distributed lock (non-blocking)
        if not try_acquire_lock("resource_cache_update", ttl_seconds=300):
            logger.debug("Another worker is updating resource cache, skipping")
            return False

        # Perform sync
        logger.info("Checking resource cache for updates...")
        try:
            updated = refresh_resource_cache(force=force)
            self._last_resource_sync = now
            return updated
        except Exception as e:
            logger.error(f"Resource cache update failed: {e}", exc_info=True)
            return False
        finally:
            release_lock("resource_cache_update")

    def _warmup_reject_dataset(self) -> None:
        from mes_dashboard.services import reject_dataset_cache
        result = reject_dataset_cache.ensure_dataset_loaded()
        logger.info(
            "Reject dataset warmup complete query_id=%s cache_hit=%s",
            result.get("query_id"),
            result.get("cache_hit"),
        )

    def _warmup_yield_alert_dataset(self) -> None:
        from mes_dashboard.services import yield_alert_dataset_cache
        result = yield_alert_dataset_cache.ensure_dataset_loaded()
        logger.info(
            "Yield-alert dataset warmup complete query_id=%s cache_hit=%s",
            result.get("query_id"),
            result.get("cache_hit"),
        )

    def _warmup_reject_options(self) -> None:
        from mes_dashboard.services.reject_history_service import get_filter_options

        end = datetime.now().date()
        start = end - timedelta(days=29)
        _ = get_filter_options(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            include_excluded_scrap=False,
            exclude_material_scrap=True,
            exclude_pb_diode=True,
        )
        logger.info("Reject options warmup complete")


# ============================================================
# Global Instance
# ============================================================

_CACHE_UPDATER: Optional[CacheUpdater] = None


def get_cache_updater() -> CacheUpdater:
    """Get or create the global cache updater instance."""
    global _CACHE_UPDATER
    if _CACHE_UPDATER is None:
        _CACHE_UPDATER = CacheUpdater()
    return _CACHE_UPDATER


def start_cache_updater() -> None:
    """Start the global cache updater."""
    get_cache_updater().start()


def stop_cache_updater() -> None:
    """Stop the global cache updater."""
    if _CACHE_UPDATER is not None:
        _CACHE_UPDATER.stop()
