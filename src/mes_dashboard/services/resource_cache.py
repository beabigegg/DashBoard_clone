# -*- coding: utf-8 -*-
"""Resource Cache - DWH.DW_MES_RESOURCE 全表快取模組.

全表快取套用全域篩選後的設備主檔資料至 Redis。
提供統一 API 供各模組取用設備資料和篩選器選項。
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.redis_client import (
    get_redis_client,
    redis_available,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
)
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    EQUIPMENT_TYPE_FILTER,
)

logger = logging.getLogger('mes_dashboard.resource_cache')

# ============================================================
# Configuration
# ============================================================

RESOURCE_CACHE_ENABLED = os.getenv('RESOURCE_CACHE_ENABLED', 'true').lower() == 'true'
RESOURCE_SYNC_INTERVAL = int(os.getenv('RESOURCE_SYNC_INTERVAL', '14400'))  # 4 hours

# Redis key helpers
def _get_key(key: str) -> str:
    """Get full Redis key with resource prefix."""
    return f"{REDIS_KEY_PREFIX}:resource:{key}"


# ============================================================
# Internal: Oracle Load Functions
# ============================================================

def _build_filter_sql() -> str:
    """Build SQL WHERE clause for global filters."""
    conditions = [EQUIPMENT_TYPE_FILTER.strip()]

    # Workcenter filter - exclude resources without WORKCENTERNAME
    conditions.append("WORKCENTERNAME IS NOT NULL")

    # Location filter
    if EXCLUDED_LOCATIONS:
        locations_list = ", ".join(f"'{loc}'" for loc in EXCLUDED_LOCATIONS)
        conditions.append(
            f"(LOCATIONNAME IS NULL OR LOCATIONNAME NOT IN ({locations_list}))"
        )

    # Asset status filter
    if EXCLUDED_ASSET_STATUSES:
        status_list = ", ".join(f"'{s}'" for s in EXCLUDED_ASSET_STATUSES)
        conditions.append(
            f"(PJ_ASSETSSTATUS IS NULL OR PJ_ASSETSSTATUS NOT IN ({status_list}))"
        )

    return " AND ".join(conditions)


def _load_from_oracle() -> Optional[pd.DataFrame]:
    """從 Oracle 載入全表資料（套用全域篩選）.

    Returns:
        DataFrame with all columns, or None if query failed.
    """
    filter_sql = _build_filter_sql()
    sql = f"""
        SELECT *
        FROM DWH.DW_MES_RESOURCE
        WHERE {filter_sql}
    """
    try:
        df = read_sql_df(sql)
        if df is not None:
            logger.info(f"Loaded {len(df)} resources from Oracle")
        return df
    except Exception as e:
        logger.error(f"Failed to load resources from Oracle: {e}")
        return None


def _get_version_from_oracle() -> Optional[str]:
    """取得 Oracle 資料版本（MAX(LASTCHANGEDATE)）.

    Returns:
        Version string (ISO format), or None if query failed.
    """
    filter_sql = _build_filter_sql()
    sql = f"""
        SELECT MAX(LASTCHANGEDATE) as VERSION
        FROM DWH.DW_MES_RESOURCE
        WHERE {filter_sql}
    """
    try:
        df = read_sql_df(sql)
        if df is not None and not df.empty:
            version = df.iloc[0]['VERSION']
            if version is not None:
                if hasattr(version, 'isoformat'):
                    return version.isoformat()
                return str(version)
        return None
    except Exception as e:
        logger.error(f"Failed to get version from Oracle: {e}")
        return None


# ============================================================
# Internal: Redis Functions
# ============================================================

def _get_version_from_redis() -> Optional[str]:
    """取得 Redis 快取版本.

    Returns:
        Cached version string, or None.
    """
    client = get_redis_client()
    if client is None:
        return None

    try:
        return client.get(_get_key("meta:version"))
    except Exception as e:
        logger.warning(f"Failed to get version from Redis: {e}")
        return None


def _sync_to_redis(df: pd.DataFrame, version: str) -> bool:
    """同步至 Redis（使用 pipeline 確保原子性）.

    Args:
        df: DataFrame with resource data.
        version: Version string (MAX(LASTCHANGEDATE)).

    Returns:
        True if sync was successful.
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        # Convert DataFrame to JSON
        # Handle datetime columns
        df_copy = df.copy()
        for col in df_copy.select_dtypes(include=['datetime64']).columns:
            df_copy[col] = df_copy[col].astype(str)

        data_json = df_copy.to_json(orient='records', force_ascii=False)

        # Atomic update using pipeline
        now = datetime.now().isoformat()
        pipe = client.pipeline()
        pipe.set(_get_key("data"), data_json)
        pipe.set(_get_key("meta:version"), version)
        pipe.set(_get_key("meta:updated"), now)
        pipe.set(_get_key("meta:count"), str(len(df)))
        pipe.execute()

        logger.info(f"Resource cache synced: {len(df)} rows, version={version}")
        return True
    except Exception as e:
        logger.error(f"Failed to sync to Redis: {e}")
        return False


def _get_cached_data() -> Optional[pd.DataFrame]:
    """Get cached resource data from Redis.

    Returns:
        DataFrame with resource data, or None if cache miss.
    """
    if not REDIS_ENABLED or not RESOURCE_CACHE_ENABLED:
        return None

    client = get_redis_client()
    if client is None:
        return None

    try:
        data_json = client.get(_get_key("data"))
        if data_json is None:
            logger.debug("Resource cache miss: no data in Redis")
            return None

        df = pd.read_json(io.StringIO(data_json), orient='records')
        logger.debug(f"Resource cache hit: loaded {len(df)} rows from Redis")
        return df
    except Exception as e:
        logger.warning(f"Failed to read resource cache: {e}")
        return None


# ============================================================
# Cache Management API
# ============================================================

def refresh_cache(force: bool = False) -> bool:
    """手動刷新快取.

    Args:
        force: 強制刷新，忽略版本檢查.

    Returns:
        True if cache was refreshed.
    """
    if not REDIS_ENABLED or not RESOURCE_CACHE_ENABLED:
        logger.info("Resource cache is disabled")
        return False

    if not redis_available():
        logger.warning("Redis not available, cannot refresh resource cache")
        return False

    try:
        # Get versions
        oracle_version = _get_version_from_oracle()
        if oracle_version is None:
            logger.error("Failed to get version from Oracle")
            return False

        redis_version = _get_version_from_redis()

        # Check if update needed
        if not force and redis_version == oracle_version:
            logger.debug(f"Resource cache version unchanged ({oracle_version}), skipping")
            return False

        logger.info(f"Resource cache version changed: {redis_version} -> {oracle_version}")

        # Load and sync
        df = _load_from_oracle()
        if df is None or df.empty:
            logger.error("Failed to load resources from Oracle")
            return False

        return _sync_to_redis(df, oracle_version)

    except Exception as e:
        logger.error(f"Failed to refresh resource cache: {e}", exc_info=True)
        return False


def init_cache() -> None:
    """初始化快取（應用啟動時呼叫）."""
    if not REDIS_ENABLED or not RESOURCE_CACHE_ENABLED:
        logger.info("Resource cache is disabled, skipping init")
        return

    if not redis_available():
        logger.warning("Redis not available during resource cache init")
        return

    # Check if cache exists
    client = get_redis_client()
    if client is None:
        return

    try:
        exists = client.exists(_get_key("data"))
        if not exists:
            logger.info("Resource cache empty, performing initial load...")
            refresh_cache(force=True)
        else:
            logger.info("Resource cache already populated")
    except Exception as e:
        logger.error(f"Failed to init resource cache: {e}")


def get_cache_status() -> Dict[str, Any]:
    """取得快取狀態資訊.

    Returns:
        Dict with cache status.
    """
    status = {
        'enabled': REDIS_ENABLED and RESOURCE_CACHE_ENABLED,
        'loaded': False,
        'count': 0,
        'version': None,
        'updated_at': None,
    }

    if not status['enabled']:
        return status

    client = get_redis_client()
    if client is None:
        return status

    try:
        status['loaded'] = client.exists(_get_key("data")) > 0
        if status['loaded']:
            count_str = client.get(_get_key("meta:count"))
            status['count'] = int(count_str) if count_str else 0
            status['version'] = client.get(_get_key("meta:version"))
            status['updated_at'] = client.get(_get_key("meta:updated"))
    except Exception as e:
        logger.warning(f"Failed to get resource cache status: {e}")

    return status


# ============================================================
# Query API
# ============================================================

def get_all_resources() -> List[Dict]:
    """取得所有快取中的設備資料（全欄位）.

    Falls back to Oracle if cache unavailable.

    Returns:
        List of resource dicts.
    """
    # Try cache first
    df = _get_cached_data()
    if df is not None:
        return df.to_dict(orient='records')

    # Fallback to Oracle
    logger.info("Resource cache miss, falling back to Oracle")
    df = _load_from_oracle()
    if df is not None:
        return df.to_dict(orient='records')

    return []


def get_resource_by_id(resource_id: str) -> Optional[Dict]:
    """依 RESOURCEID 取得單筆設備資料.

    Args:
        resource_id: The RESOURCEID to look up.

    Returns:
        Resource dict, or None if not found.
    """
    resources = get_all_resources()
    for r in resources:
        if r.get('RESOURCEID') == resource_id:
            return r
    return None


def get_resources_by_ids(resource_ids: List[str]) -> List[Dict]:
    """依 RESOURCEID 清單批次取得設備資料.

    Args:
        resource_ids: List of RESOURCEIDs to look up.

    Returns:
        List of matching resource dicts.
    """
    id_set = set(resource_ids)
    resources = get_all_resources()
    return [r for r in resources if r.get('RESOURCEID') in id_set]


def get_resources_by_filter(
    workcenters: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    departments: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    is_production: Optional[bool] = None,
    is_key: Optional[bool] = None,
    is_monitor: Optional[bool] = None,
) -> List[Dict]:
    """依條件篩選設備資料（在 Python 端篩選）.

    Args:
        workcenters: Filter by WORKCENTERNAME values.
        families: Filter by RESOURCEFAMILYNAME values.
        departments: Filter by PJ_DEPARTMENT values.
        locations: Filter by LOCATIONNAME values.
        is_production: Filter by PJ_ISPRODUCTION flag.
        is_key: Filter by PJ_ISKEY flag.
        is_monitor: Filter by PJ_ISMONITOR flag.

    Returns:
        List of matching resource dicts.
    """
    resources = get_all_resources()

    result = []
    for r in resources:
        # Apply filters
        if workcenters and r.get('WORKCENTERNAME') not in workcenters:
            continue
        if families and r.get('RESOURCEFAMILYNAME') not in families:
            continue
        if departments and r.get('PJ_DEPARTMENT') not in departments:
            continue
        if locations and r.get('LOCATIONNAME') not in locations:
            continue
        if is_production is not None:
            val = r.get('PJ_ISPRODUCTION')
            if (val == 1) != is_production:
                continue
        if is_key is not None:
            val = r.get('PJ_ISKEY')
            if (val == 1) != is_key:
                continue
        if is_monitor is not None:
            val = r.get('PJ_ISMONITOR')
            if (val == 1) != is_monitor:
                continue

        result.append(r)

    return result


# ============================================================
# Distinct Values API (for filters)
# ============================================================

def get_distinct_values(column: str) -> List[str]:
    """取得指定欄位的唯一值清單（排序後）.

    Args:
        column: Column name (e.g., 'RESOURCEFAMILYNAME').

    Returns:
        Sorted list of unique values (excluding None, NaN, and empty strings).
    """
    resources = get_all_resources()
    values = set()
    for r in resources:
        val = r.get(column)
        # Skip None, empty strings, and NaN (pandas converts NaN to float)
        if val is None or val == '':
            continue
        # Check for NaN (float type and is NaN)
        if isinstance(val, float) and pd.isna(val):
            continue
        values.add(str(val) if not isinstance(val, str) else val)
    return sorted(values)


def get_resource_families() -> List[str]:
    """取得型號清單（便捷方法）."""
    return get_distinct_values('RESOURCEFAMILYNAME')


def get_workcenters() -> List[str]:
    """取得站點清單（便捷方法）."""
    return get_distinct_values('WORKCENTERNAME')


def get_departments() -> List[str]:
    """取得部門清單（便捷方法）."""
    return get_distinct_values('PJ_DEPARTMENT')


def get_locations() -> List[str]:
    """取得區域清單（便捷方法）."""
    return get_distinct_values('LOCATIONNAME')


def get_vendors() -> List[str]:
    """取得供應商清單（便捷方法）."""
    return get_distinct_values('VENDORNAME')
