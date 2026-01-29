# -*- coding: utf-8 -*-
"""Cached filter options for MES Dashboard.

Provides cached workcenter groups and resource families for filter dropdowns.
Data is loaded from database and cached in memory with periodic refresh.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from mes_dashboard.core.database import read_sql_df

logger = logging.getLogger('mes_dashboard.filter_cache')

# ============================================================
# Cache Configuration
# ============================================================

CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL
WIP_VIEW = "DW_MES_LOT_V"

# ============================================================
# Cache Storage
# ============================================================

_CACHE = {
    'workcenter_groups': None,      # List of {name, sequence}
    'workcenter_mapping': None,     # Dict {workcentername: {group, sequence}}
    'last_refresh': None,
    'is_loading': False,
}

_CACHE_LOCK = threading.Lock()


# ============================================================
# Workcenter Group Functions
# ============================================================

def get_workcenter_groups(force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get list of workcenter groups with sequence order.

    Returns:
        List of {name, sequence} sorted by sequence, or None if loading fails.
    """
    _ensure_cache_loaded(force_refresh)
    return _CACHE.get('workcenter_groups')


def get_workcenter_mapping(force_refresh: bool = False) -> Optional[Dict[str, Dict[str, Any]]]:
    """Get workcenter name to group mapping.

    Returns:
        Dict mapping workcentername to {group, sequence}, or None if loading fails.
    """
    _ensure_cache_loaded(force_refresh)
    return _CACHE.get('workcenter_mapping')


def get_workcenters_for_groups(groups: List[str]) -> List[str]:
    """Get list of workcenter names that belong to specified groups.

    Args:
        groups: List of WORKCENTER_GROUP names

    Returns:
        List of WORKCENTERNAME values belonging to those groups
    """
    mapping = get_workcenter_mapping()
    if not mapping:
        return []

    result = []
    for wc_name, info in mapping.items():
        if info.get('group') in groups:
            result.append(wc_name)
    return result


# ============================================================
# Cache Management
# ============================================================

def get_cache_status() -> Dict[str, Any]:
    """Get current cache status.

    Returns:
        Dict with cache status information
    """
    with _CACHE_LOCK:
        last_refresh = _CACHE.get('last_refresh')
        return {
            'loaded': last_refresh is not None,
            'last_refresh': last_refresh.isoformat() if last_refresh else None,
            'is_loading': _CACHE.get('is_loading', False),
            'workcenter_groups_count': len(_CACHE.get('workcenter_groups') or []),
            'workcenter_mapping_count': len(_CACHE.get('workcenter_mapping') or {}),
        }


def refresh_cache() -> bool:
    """Force refresh the cache.

    Returns:
        True if refresh succeeded, False otherwise
    """
    return _load_cache()


def _ensure_cache_loaded(force_refresh: bool = False):
    """Ensure cache is loaded and not stale."""
    with _CACHE_LOCK:
        now = datetime.now()
        last_refresh = _CACHE.get('last_refresh')
        is_loading = _CACHE.get('is_loading', False)

        # Check if cache is valid
        cache_valid = (
            last_refresh is not None and
            (now - last_refresh).total_seconds() < CACHE_TTL_SECONDS
        )

        if cache_valid and not force_refresh:
            return

        if is_loading:
            return  # Another thread is loading

    # Load cache (outside lock to avoid blocking)
    _load_cache()


def _load_cache() -> bool:
    """Load all cache data from database.

    Returns:
        True if loading succeeded, False otherwise
    """
    with _CACHE_LOCK:
        if _CACHE.get('is_loading'):
            return False
        _CACHE['is_loading'] = True

    try:
        # Load workcenter groups from DW_MES_LOT_V
        wc_groups, wc_mapping = _load_workcenter_data()

        with _CACHE_LOCK:
            _CACHE['workcenter_groups'] = wc_groups
            _CACHE['workcenter_mapping'] = wc_mapping
            _CACHE['last_refresh'] = datetime.now()
            _CACHE['is_loading'] = False

        logger.info(
            f"Filter cache refreshed: {len(wc_groups or [])} groups, "
            f"{len(wc_mapping or {})} workcenters"
        )
        return True

    except Exception as exc:
        logger.error(f"Failed to load filter cache: {exc}")
        with _CACHE_LOCK:
            _CACHE['is_loading'] = False
        return False


def _load_workcenter_data():
    """Load workcenter group data from WIP cache (Redis) or fallback to Oracle.

    Returns:
        Tuple of (groups_list, mapping_dict)
    """
    # Try to load from WIP Redis cache first
    try:
        from mes_dashboard.core.cache import get_cached_wip_data

        df = get_cached_wip_data()
        if df is not None and not df.empty:
            logger.debug("Loading workcenter groups from WIP cache")
            return _extract_workcenter_data_from_df(df)
    except Exception as exc:
        logger.warning(f"Failed to load from WIP cache: {exc}")

    # Fallback to Oracle direct query
    logger.debug("Falling back to Oracle for workcenter groups")
    try:
        sql = f"""
            SELECT DISTINCT
                WORKCENTERNAME,
                WORKCENTERID,
                WORKCENTER_GROUP,
                WORKCENTERSEQUENCE_GROUP
            FROM {WIP_VIEW}
            WHERE WORKCENTER_GROUP IS NOT NULL
              AND WORKCENTERNAME IS NOT NULL
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            logger.warning("No workcenter data found in DW_MES_LOT_V")
            return [], {}

        return _extract_workcenter_data_from_df(df)

    except Exception as exc:
        logger.error(f"Failed to load workcenter data: {exc}")
        return [], {}


def _extract_workcenter_data_from_df(df):
    """Extract workcenter groups and mapping from DataFrame.

    Args:
        df: DataFrame with WORKCENTERNAME, WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP columns

    Returns:
        Tuple of (groups_list, mapping_dict)
    """
    # Filter to rows with valid workcenter group
    df = df[df['WORKCENTER_GROUP'].notna() & df['WORKCENTERNAME'].notna()]

    if df.empty:
        return [], {}

    # Build groups list (unique groups, take minimum sequence for each group)
    groups_df = df.groupby('WORKCENTER_GROUP')['WORKCENTERSEQUENCE_GROUP'].min().reset_index()
    groups_df = groups_df.sort_values('WORKCENTERSEQUENCE_GROUP')

    groups = []
    for _, row in groups_df.iterrows():
        groups.append({
            'name': row['WORKCENTER_GROUP'],
            'sequence': int(row['WORKCENTERSEQUENCE_GROUP'] or 999)
        })

    # Build mapping dict
    mapping = {}
    for _, row in df.iterrows():
        wc_name = row['WORKCENTERNAME']
        mapping[wc_name] = {
            'id': row.get('WORKCENTERID'),
            'group': row['WORKCENTER_GROUP'],
            'sequence': int(row['WORKCENTERSEQUENCE_GROUP'] or 999)
        }

    return groups, mapping


# ============================================================
# Initialization
# ============================================================

def init_cache():
    """Initialize the cache on application startup.

    Should be called during app initialization.
    """
    logger.info("Initializing filter cache...")
    _load_cache()
