# -*- coding: utf-8 -*-
"""Cached filter options for MES Dashboard.

Provides cached workcenter groups and resource families for filter dropdowns.
Data is loaded from database and cached in memory with periodic refresh.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import get_redis_client, get_key, REDIS_ENABLED

logger = logging.getLogger('mes_dashboard.filter_cache')

# ============================================================
# Cache Configuration
# ============================================================

from mes_dashboard.config.constants import CACHE_TTL_FILTER_GENERAL
from mes_dashboard.core.cache_plane import snapshot_redis_ttl
CACHE_TTL_SECONDS = CACHE_TTL_FILTER_GENERAL
# Redis retention uses snapshot-plane policy: > refresh interval so expiry
# does not force Oracle fallback before the next healthy refresh cycle.
_REDIS_TTL_SECONDS = snapshot_redis_ttl(CACHE_TTL_SECONDS)
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
    'spec_workcenter_mapping': None,  # Dict {spec_name_upper: {workcenter, group, sequence}}
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


def get_spec_workcenter_mapping(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """Get SPEC -> {workcenter, group, sequence} mapping.

    Returns:
        Dict mapping normalized SPEC name (uppercase) to workcenter info.
    """
    _ensure_cache_loaded(force_refresh)
    return _CACHE.get('spec_workcenter_mapping') or {}


def get_specs_for_groups(groups: List[str]) -> List[str]:
    """Get list of SPEC names that belong to specified workcenter groups.

    Args:
        groups: List of WORKCENTER_GROUP names

    Returns:
        List of normalized SPEC names (uppercase) belonging to those groups.
    """
    mapping = get_spec_workcenter_mapping()
    if not mapping:
        return []
    target = {g.strip().upper() for g in groups if g}
    return [spec for spec, info in mapping.items()
            if info['group'].strip().upper() in target]


# ============================================================
# Redis L2 Cache Helpers
# ============================================================

_REDIS_KEY = "filter_cache:data"

# Payload keys that are persisted to / restored from Redis.
# Internal bookkeeping keys (last_refresh, is_loading) are excluded.
_REDIS_PAYLOAD_KEYS = (
    'workcenter_groups',
    'workcenter_mapping',
    'workcenter_to_short',
    'spec_order_mapping',
    'spec_workcenter_mapping',
)


def _write_to_redis(data: dict) -> None:
    """Serialize cache payload to Redis with TTL.

    Failures are logged as warnings and silently swallowed so that a Redis
    outage never prevents the in-memory cache from being used.
    """
    if not REDIS_ENABLED:
        return
    try:
        client = get_redis_client()
        if client is None:
            return
        payload = {k: data[k] for k in _REDIS_PAYLOAD_KEYS if k in data}
        client.set(
            get_key(_REDIS_KEY),
            json.dumps(payload, default=str),
            ex=_REDIS_TTL_SECONDS,
        )
        logger.debug("Filter cache written to Redis (TTL=%ds)", _REDIS_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Failed to write filter cache to Redis: %s", exc)


def _read_from_redis() -> Optional[dict]:
    """Deserialize cache payload from Redis.

    Returns:
        Dict with payload keys, or None on miss / error / Redis disabled.
    """
    if not REDIS_ENABLED:
        return None
    try:
        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(get_key(_REDIS_KEY))
        if raw is None:
            return None
        data = json.loads(raw)
        logger.debug("Filter cache restored from Redis")
        return data
    except Exception as exc:
        logger.warning("Failed to read filter cache from Redis: %s", exc)
        return None


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
            'spec_workcenter_mapping_count': len(_CACHE.get('spec_workcenter_mapping') or {}),
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
    """Load all cache data, trying Redis L2 before Oracle.

    Load order:
        1. Redis L2 — fast cross-worker hit, avoids Oracle round-trip.
        2. Oracle   — authoritative source; result is written back to Redis.

    Returns:
        True if loading succeeded, False otherwise.
    """
    with _CACHE_LOCK:
        if _CACHE.get('is_loading'):
            return False
        _CACHE['is_loading'] = True

    try:
        # --- L2: try Redis before going to Oracle ---
        redis_data = _read_from_redis()
        if redis_data is not None:
            with _CACHE_LOCK:
                for k in _REDIS_PAYLOAD_KEYS:
                    _CACHE[k] = redis_data.get(k)
                _CACHE['last_refresh'] = datetime.now()
                _CACHE['is_loading'] = False
            logger.info(
                "Filter cache populated from Redis: %d groups, %d workcenters, "
                "%d specs, %d spec-wc mappings",
                len(_CACHE.get('workcenter_groups') or []),
                len(_CACHE.get('workcenter_mapping') or {}),
                len(_CACHE.get('spec_order_mapping') or {}),
                len(_CACHE.get('spec_workcenter_mapping') or {}),
            )
            return True

        # --- L3: load from Oracle ---
        wc_groups, wc_mapping, wc_short = _load_workcenter_data()
        spec_order_mapping = _load_spec_order_mapping_from_spec()
        spec_wc_mapping = _load_spec_workcenter_mapping()

        with _CACHE_LOCK:
            _CACHE['workcenter_groups'] = wc_groups
            _CACHE['workcenter_mapping'] = wc_mapping
            _CACHE['workcenter_to_short'] = wc_short
            _CACHE['spec_order_mapping'] = spec_order_mapping
            _CACHE['spec_workcenter_mapping'] = spec_wc_mapping
            _CACHE['last_refresh'] = datetime.now()
            _CACHE['is_loading'] = False

        logger.info(
            "Filter cache refreshed from Oracle: %d groups, %d workcenters, "
            "%d specs, %d spec-wc mappings",
            len(wc_groups or []),
            len(wc_mapping or {}),
            len(spec_order_mapping or {}),
            len(spec_wc_mapping or {}),
        )

        # Write Oracle result back to Redis L2 for other workers
        _write_to_redis({
            'workcenter_groups': wc_groups,
            'workcenter_mapping': wc_mapping,
            'workcenter_to_short': wc_short,
            'spec_order_mapping': spec_order_mapping,
            'spec_workcenter_mapping': spec_wc_mapping,
        })

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


def _load_spec_workcenter_mapping() -> Dict[str, Dict[str, Any]]:
    """Load SPEC -> {workcenter, group, sequence} mapping from SPEC_WORKCENTER_V."""
    try:
        sql = f"""
            SELECT SPEC, WORK_CENTER, WORK_CENTER_GROUP, WORKCENTERSEQUENCE_GROUP
            FROM {SPEC_WORKCENTER_VIEW}
            WHERE SPEC IS NOT NULL AND WORK_CENTER IS NOT NULL
        """
        df = read_sql_df(sql)
        if df is None or df.empty:
            return {}

        mapping: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            spec = _normalize_spec_name(row.get('SPEC'))
            if not spec:
                continue
            seq = _safe_sort_value(row.get('WORKCENTERSEQUENCE_GROUP'))
            prev = mapping.get(spec)
            if prev is None or seq < prev['sequence']:
                mapping[spec] = {
                    'workcenter': str(row['WORK_CENTER']).strip(),
                    'group': str(row['WORK_CENTER_GROUP']).strip(),
                    'sequence': seq,
                }
        return mapping
    except Exception as exc:
        logger.error(f"Failed to load SPEC_WORKCENTER mapping from SPEC_WORKCENTER_V: {exc}")
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
