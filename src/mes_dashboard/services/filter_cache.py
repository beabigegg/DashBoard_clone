# -*- coding: utf-8 -*-
"""Cached filter options for MES Dashboard.

Provides cached workcenter groups and resource families for filter dropdowns.
Data is loaded from database and cached in memory with periodic refresh.
"""

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from mes_dashboard.core.database import read_sql_df

logger = logging.getLogger('mes_dashboard.filter_cache')

# ============================================================
# Cache Configuration
# ============================================================

CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL
WIP_VIEW = os.getenv("FILTER_CACHE_WIP_VIEW", "DWH.DW_MES_LOT_V")
SPEC_WORKCENTER_VIEW = os.getenv("FILTER_CACHE_SPEC_WORKCENTER_VIEW", "DWH.DW_MES_SPEC_WORKCENTER_V")

# ============================================================
# Cache Storage
# ============================================================

_CACHE = {
    'workcenter_groups': None,      # List of {name, sequence}
    'workcenter_mapping': None,     # Dict {workcentername: {group, sequence}}
    'workcenter_to_short': None,    # Dict {workcentername: short_name}
    'spec_order_mapping': None,     # Dict {spec_name_upper: spec_order}
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


def get_workcenter_group(workcenter_name: str) -> Optional[str]:
    """Get workcenter group for a workcenter name.

    Args:
        workcenter_name: The workcenter name to look up.

    Returns:
        The WORK_CENTER_GROUP, or None if not found.
    """
    mapping = get_workcenter_mapping()
    if not mapping or workcenter_name not in mapping:
        return None
    return mapping[workcenter_name].get('group')


def get_workcenter_group_sequence(workcenter_name: str) -> Optional[int]:
    """Get workcenter group sequence for a workcenter name.

    Args:
        workcenter_name: The workcenter name to look up.

    Returns:
        The WORKCENTERSEQUENCE_GROUP, or None if not found.
    """
    mapping = get_workcenter_mapping()
    if not mapping or workcenter_name not in mapping:
        return None
    return mapping[workcenter_name].get('sequence')


def get_workcenter_short(workcenter_name: str) -> Optional[str]:
    """Get workcenter short name for a workcenter name.

    Args:
        workcenter_name: The workcenter name to look up.

    Returns:
        The WORK_CENTER_SHORT (e.g., DB, WB, Mold), or None if not found.
    """
    _ensure_cache_loaded()
    short_mapping = _CACHE.get('workcenter_to_short')
    if not short_mapping or workcenter_name not in short_mapping:
        return None
    return short_mapping.get(workcenter_name)


def get_workcenters_by_group(group_name: str) -> List[str]:
    """Get all workcenter names that belong to a specific group.

    Args:
        group_name: The WORKCENTER_GROUP name.

    Returns:
        List of workcenter names in that group.
    """
    mapping = get_workcenter_mapping()
    if not mapping:
        return []

    return [
        wc_name
        for wc_name, info in mapping.items()
        if info.get('group') == group_name
    ]


def get_spec_order_mapping(force_refresh: bool = False) -> Dict[str, int]:
    """Get SPEC -> SPEC_ORDER mapping from SPEC_WORKCENTER_V cache.

    Returns:
        Dict mapping normalized SPEC name (uppercase) to integer SPEC_ORDER.
    """
    _ensure_cache_loaded(force_refresh)
    mapping = _CACHE.get('spec_order_mapping')
    if isinstance(mapping, dict):
        return mapping
    return {}


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
            'spec_order_mapping_count': len(_CACHE.get('spec_order_mapping') or {}),
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
        # Load workcenter groups - prioritize SPEC_WORKCENTER_V
        wc_groups, wc_mapping, wc_short = _load_workcenter_data()
        spec_order_mapping = _load_spec_order_mapping_from_spec()

        with _CACHE_LOCK:
            _CACHE['workcenter_groups'] = wc_groups
            _CACHE['workcenter_mapping'] = wc_mapping
            _CACHE['workcenter_to_short'] = wc_short
            _CACHE['spec_order_mapping'] = spec_order_mapping
            _CACHE['last_refresh'] = datetime.now()
            _CACHE['is_loading'] = False

        logger.info(
            f"Filter cache refreshed: {len(wc_groups or [])} groups, "
            f"{len(wc_mapping or {})} workcenters, "
            f"{len(spec_order_mapping or {})} specs"
        )
        return True

    except Exception as exc:
        logger.error(f"Failed to load filter cache: {exc}")
        with _CACHE_LOCK:
            _CACHE['is_loading'] = False
        return False


def _load_workcenter_data():
    """Load workcenter group data from SPEC_WORKCENTER_V (preferred) or fallback to WIP.

    Returns:
        Tuple of (groups_list, mapping_dict, short_mapping_dict)
    """
    # Try to load from SPEC_WORKCENTER_V first (authoritative source)
    result = _load_workcenter_mapping_from_spec()
    if result[0]:  # If groups are loaded
        logger.debug("Loaded workcenter groups from SPEC_WORKCENTER_V")
        return result

    # Fallback to WIP cache
    logger.warning("Falling back to WIP source for workcenter groups")
    try:
        from mes_dashboard.core.cache import get_cached_wip_data

        df = get_cached_wip_data()
        if df is not None and not df.empty:
            logger.debug("Loading workcenter groups from WIP cache")
            groups, mapping = _extract_workcenter_data_from_df(df)
            return groups, mapping, {}
    except Exception as exc:
        logger.warning(f"Failed to load from WIP cache: {exc}")

    # Fallback to Oracle WIP view direct query
    logger.debug("Falling back to Oracle WIP view for workcenter groups")
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
            logger.warning("No workcenter data found in DWH.DW_MES_LOT_V")
            return [], {}, {}

        groups, mapping = _extract_workcenter_data_from_df(df)
        return groups, mapping, {}

    except Exception as exc:
        logger.error(f"Failed to load workcenter data: {exc}")
        return [], {}, {}


def _load_workcenter_mapping_from_spec():
    """Load workcenter mapping from DW_MES_SPEC_WORKCENTER_V.

    This is the authoritative source for workcenter -> group mapping.

    Returns:
        Tuple of (groups_list, mapping_dict, short_mapping_dict)
    """
    try:
        sql = f"""
            SELECT DISTINCT
                WORK_CENTER,
                WORK_CENTER_GROUP,
                WORKCENTERSEQUENCE_GROUP,
                WORK_CENTER_SHORT
            FROM {SPEC_WORKCENTER_VIEW}
            WHERE WORK_CENTER IS NOT NULL
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            logger.warning("No data found in SPEC_WORKCENTER_V")
            return [], {}, {}

        # Build groups list (unique groups, take minimum sequence for each group)
        groups_df = df.groupby('WORK_CENTER_GROUP')['WORKCENTERSEQUENCE_GROUP'].min().reset_index()
        groups_df = groups_df.sort_values('WORKCENTERSEQUENCE_GROUP')

        groups = []
        for _, row in groups_df.iterrows():
            group_name = row['WORK_CENTER_GROUP']
            if group_name:
                groups.append({
                    'name': group_name,
                    'sequence': int(row['WORKCENTERSEQUENCE_GROUP'] or 999)
                })

        # Build mapping dict (WORK_CENTER -> group info)
        mapping = {}
        short_mapping = {}
        for _, row in df.iterrows():
            wc_name = row['WORK_CENTER']
            if wc_name:
                mapping[wc_name] = {
                    'group': row['WORK_CENTER_GROUP'],
                    'sequence': int(row['WORKCENTERSEQUENCE_GROUP'] or 999)
                }
                if row.get('WORK_CENTER_SHORT'):
                    short_mapping[wc_name] = row['WORK_CENTER_SHORT']

        logger.info(f"Loaded {len(mapping)} workcenters from SPEC_WORKCENTER_V")
        return groups, mapping, short_mapping

    except Exception as exc:
        logger.error(f"Failed to load from SPEC_WORKCENTER_V: {exc}")
        return [], {}, {}


def _safe_sort_value(value: Any, default: int = 999999) -> int:
    """Parse sequence/order values into stable integers."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        if not text:
            return default
        digits = ''.join(ch for ch in text if ch.isdigit())
        if not digits:
            return default
        try:
            return int(digits)
        except (TypeError, ValueError):
            return default


def _normalize_spec_name(spec_name: Any) -> str:
    if spec_name is None:
        return ''
    return str(spec_name).strip().upper()


def _load_spec_order_mapping_from_spec() -> Dict[str, int]:
    """Load SPEC -> SPEC_ORDER mapping from DW_MES_SPEC_WORKCENTER_V."""
    try:
        sql = f"""
            SELECT DISTINCT
                SPEC,
                SPEC_ORDER
            FROM {SPEC_WORKCENTER_VIEW}
            WHERE SPEC IS NOT NULL
        """
        df = read_sql_df(sql)
        if df is None or df.empty:
            return {}

        mapping: Dict[str, int] = {}
        for _, row in df.iterrows():
            normalized_spec = _normalize_spec_name(row.get('SPEC'))
            if not normalized_spec:
                continue
            sort_order = _safe_sort_value(row.get('SPEC_ORDER'))
            previous = mapping.get(normalized_spec)
            if previous is None or sort_order < previous:
                mapping[normalized_spec] = sort_order
        return mapping
    except Exception as exc:
        logger.error(f"Failed to load SPEC_ORDER mapping from SPEC_WORKCENTER_V: {exc}")
        return {}


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
