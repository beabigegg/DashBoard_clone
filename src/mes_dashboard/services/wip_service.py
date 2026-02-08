# -*- coding: utf-8 -*-
"""WIP (Work In Progress) query services for MES Dashboard.

Provides functions to query WIP data from DWH.DW_MES_LOT_V view.
This view provides real-time WIP information updated every 5 minutes.

Now uses Redis cache when available, with fallback to Oracle direct query.
"""

import logging
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any

import numpy as np
import pandas as pd

from mes_dashboard.core.database import (
    read_sql_df,
    DatabasePoolExhaustedError,
    DatabaseCircuitOpenError,
)
from mes_dashboard.core.cache import (
    get_cached_wip_data,
    get_cached_sys_date,
    get_cache_updated_at,
)
from mes_dashboard.sql import SQLLoader, QueryBuilder
from mes_dashboard.sql.filters import CommonFilters, NON_QUALITY_HOLD_REASONS

logger = logging.getLogger('mes_dashboard.wip_service')

_wip_search_index_lock = threading.Lock()
_wip_search_index_cache: Dict[str, Dict[str, Any]] = {}


def _safe_value(val):
    """Convert pandas NaN/NaT to None and numpy types to native Python types for JSON serialization."""
    if pd.isna(val):
        return None
    # Convert numpy types to native Python types for JSON serialization
    if hasattr(val, 'item'):  # numpy scalar types have .item() method
        return val.item()
    return val


def _build_base_conditions_builder(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    builder: Optional[QueryBuilder] = None
) -> QueryBuilder:
    """Build base WHERE conditions for WIP queries using QueryBuilder.

    Args:
        include_dummy: If False (default), exclude LOTID containing 'DUMMY'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        builder: Optional existing QueryBuilder to add conditions to

    Returns:
        QueryBuilder with base conditions and parameters
    """
    if builder is None:
        builder = QueryBuilder()

    # Exclude raw materials (NULL WORKORDER)
    builder.add_is_not_null("WORKORDER")

    # DUMMY exclusion (default behavior)
    if not include_dummy:
        builder.add_condition("LOTID NOT LIKE '%DUMMY%'")

    # WORKORDER filter (fuzzy match)
    if workorder:
        builder.add_like_condition("WORKORDER", workorder, position="both")

    # LOTID filter (fuzzy match)
    if lotid:
        builder.add_like_condition("LOTID", lotid, position="both")

    return builder


# ============================================================
# Hold Type Classification
# ============================================================
# NON_QUALITY_HOLD_REASONS is imported from sql.filters


def is_quality_hold(reason: str) -> bool:
    """Check if a hold reason is quality-related.

    Wrapper for CommonFilters.is_quality_hold for backwards compatibility.
    """
    return CommonFilters.is_quality_hold(reason)


def _add_hold_type_conditions(
    builder: QueryBuilder,
    hold_type: Optional[str] = None
) -> QueryBuilder:
    """Add hold type filter conditions to QueryBuilder.

    Args:
        builder: QueryBuilder to add conditions to
        hold_type: 'quality' for quality holds, 'non-quality' for non-quality holds

    Returns:
        QueryBuilder with hold type conditions added
    """
    if hold_type == 'quality':
        # Quality hold: HOLDREASONNAME is NULL or NOT in non-quality list
        builder.add_not_in_condition(
            "HOLDREASONNAME",
            list(NON_QUALITY_HOLD_REASONS),
            allow_null=True
        )
    elif hold_type == 'non-quality':
        # Non-quality hold: HOLDREASONNAME is in non-quality list
        builder.add_in_condition("HOLDREASONNAME", list(NON_QUALITY_HOLD_REASONS))
    return builder


# ============================================================
# Data Source Configuration
# ============================================================
# WIP view for real-time lot data
WIP_VIEW = "DWH.DW_MES_LOT_V"


# ============================================================
# Cache Data Helper Functions
# ============================================================

def _get_wip_dataframe() -> Optional[pd.DataFrame]:
    """Get WIP data from cache or return None if unavailable.

    Returns:
        DataFrame with WIP data from Redis cache, or None if cache miss.
    """
    df = get_cached_wip_data()
    if df is not None and not df.empty:
        logger.debug(f"Using cached WIP data ({len(df)} rows)")
        return df
    return None


def _get_wip_cache_version() -> str:
    """Build a lightweight cache version marker for derived index refresh."""
    updated_at = get_cache_updated_at() or ""
    sys_date = get_cached_sys_date() or ""
    return f"{updated_at}|{sys_date}"


def _distinct_sorted_values(df: pd.DataFrame, column: str) -> List[str]:
    if column not in df.columns:
        return []
    series = df[column].dropna().astype(str)
    if series.empty:
        return []
    series = series[series.str.len() > 0]
    if series.empty:
        return []
    return series.drop_duplicates().sort_values().tolist()


def _build_wip_search_index(df: pd.DataFrame, include_dummy: bool) -> Dict[str, Any]:
    filtered = _filter_base_conditions(df, include_dummy=include_dummy)
    return {
        "built_at": datetime.now().isoformat(),
        "row_count": len(filtered),
        "workorders": _distinct_sorted_values(filtered, "WORKORDER"),
        "lotids": _distinct_sorted_values(filtered, "LOTID"),
        "packages": _distinct_sorted_values(filtered, "PACKAGE_LEF"),
        "types": _distinct_sorted_values(filtered, "PJ_TYPE"),
    }


def _get_wip_search_index(include_dummy: bool) -> Optional[Dict[str, Any]]:
    cache_key = "with_dummy" if include_dummy else "without_dummy"
    version = _get_wip_cache_version()

    with _wip_search_index_lock:
        cached = _wip_search_index_cache.get(cache_key)
        if cached and cached.get("version") == version:
            return cached

    df = _get_wip_dataframe()
    if df is None:
        return None

    index_payload = _build_wip_search_index(df, include_dummy=include_dummy)
    index_payload["version"] = version

    with _wip_search_index_lock:
        _wip_search_index_cache[cache_key] = index_payload
        return index_payload


def _search_values_from_index(values: List[str], query: str, limit: int) -> List[str]:
    query_lower = query.lower()
    matched = [value for value in values if query_lower in value.lower()]
    return matched[:limit]


def get_wip_search_index_status() -> Dict[str, Any]:
    """Expose WIP derived search-index freshness for diagnostics."""
    with _wip_search_index_lock:
        snapshot = {}
        for key, payload in _wip_search_index_cache.items():
            snapshot[key] = {
                "version": payload.get("version"),
                "built_at": payload.get("built_at"),
                "row_count": payload.get("row_count", 0),
                "workorders": len(payload.get("workorders", [])),
                "lotids": len(payload.get("lotids", [])),
                "packages": len(payload.get("packages", [])),
                "types": len(payload.get("types", [])),
            }
        return snapshot


def _add_wip_status_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add computed WIP status columns to DataFrame.

    Adds columns:
    - WIP_STATUS: 'RUN', 'HOLD', or 'QUEUE'
    - IS_QUALITY_HOLD: True if quality hold
    - IS_NON_QUALITY_HOLD: True if non-quality hold

    Args:
        df: DataFrame with EQUIPMENTCOUNT, CURRENTHOLDCOUNT, HOLDREASONNAME columns

    Returns:
        DataFrame with additional status columns
    """
    df = df.copy()

    # Ensure numeric columns
    df['EQUIPMENTCOUNT'] = pd.to_numeric(df['EQUIPMENTCOUNT'], errors='coerce').fillna(0)
    df['CURRENTHOLDCOUNT'] = pd.to_numeric(df['CURRENTHOLDCOUNT'], errors='coerce').fillna(0)
    df['QTY'] = pd.to_numeric(df['QTY'], errors='coerce').fillna(0)

    # Compute WIP status
    df['WIP_STATUS'] = 'QUEUE'  # Default
    df.loc[df['EQUIPMENTCOUNT'] > 0, 'WIP_STATUS'] = 'RUN'
    df.loc[(df['EQUIPMENTCOUNT'] == 0) & (df['CURRENTHOLDCOUNT'] > 0), 'WIP_STATUS'] = 'HOLD'

    # Compute hold type
    df['IS_NON_QUALITY_HOLD'] = df['HOLDREASONNAME'].isin(NON_QUALITY_HOLD_REASONS)
    df['IS_QUALITY_HOLD'] = (df['WIP_STATUS'] == 'HOLD') & ~df['IS_NON_QUALITY_HOLD']
    df['IS_NON_QUALITY_HOLD'] = (df['WIP_STATUS'] == 'HOLD') & df['IS_NON_QUALITY_HOLD']

    return df


def _filter_base_conditions(
    df: pd.DataFrame,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> pd.DataFrame:
    """Apply base filter conditions to DataFrame.

    Args:
        df: DataFrame to filter
        include_dummy: If False (default), exclude LOTID containing 'DUMMY'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)

    Returns:
        Filtered DataFrame
    """
    df = df.copy()

    # Exclude NULL WORKORDER (raw materials)
    df = df[df['WORKORDER'].notna()]

    # DUMMY exclusion
    if not include_dummy:
        df = df[~df['LOTID'].str.contains('DUMMY', case=False, na=False)]

    # WORKORDER filter (fuzzy match)
    if workorder:
        df = df[df['WORKORDER'].str.contains(workorder, case=False, na=False)]

    # LOTID filter (fuzzy match)
    if lotid:
        df = df[df['LOTID'].str.contains(lotid, case=False, na=False)]

    return df


# ============================================================
# Overview API Functions
# ============================================================

def get_wip_summary(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get WIP KPI summary for overview dashboard.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)

    Returns:
        Dict with summary stats (camelCase):
        - totalLots: Total number of lots
        - totalQtyPcs: Total quantity
        - byWipStatus: Grouped counts for RUN/QUEUE/HOLD
        - dataUpdateDate: Data timestamp
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder, lotid)
            df = _add_wip_status_columns(df)

            # Apply package filter
            if package and 'PACKAGE_LEF' in df.columns:
                df = df[df['PACKAGE_LEF'] == package]

            # Apply pj_type filter
            if pj_type and 'PJ_TYPE' in df.columns:
                df = df[df['PJ_TYPE'] == pj_type]

            if df.empty:
                return {
                    'totalLots': 0,
                    'totalQtyPcs': 0,
                    'byWipStatus': {
                        'run': {'lots': 0, 'qtyPcs': 0},
                        'queue': {'lots': 0, 'qtyPcs': 0},
                        'hold': {'lots': 0, 'qtyPcs': 0},
                        'qualityHold': {'lots': 0, 'qtyPcs': 0},
                        'nonQualityHold': {'lots': 0, 'qtyPcs': 0}
                    },
                    'dataUpdateDate': get_cached_sys_date()
                }

            # Calculate summary from cached data
            run_df = df[df['WIP_STATUS'] == 'RUN']
            queue_df = df[df['WIP_STATUS'] == 'QUEUE']
            hold_df = df[df['WIP_STATUS'] == 'HOLD']
            quality_hold_df = df[df['IS_QUALITY_HOLD']]
            non_quality_hold_df = df[df['IS_NON_QUALITY_HOLD']]

            return {
                'totalLots': len(df),
                'totalQtyPcs': int(df['QTY'].sum()),
                'byWipStatus': {
                    'run': {
                        'lots': len(run_df),
                        'qtyPcs': int(run_df['QTY'].sum())
                    },
                    'queue': {
                        'lots': len(queue_df),
                        'qtyPcs': int(queue_df['QTY'].sum())
                    },
                    'hold': {
                        'lots': len(hold_df),
                        'qtyPcs': int(hold_df['QTY'].sum())
                    },
                    'qualityHold': {
                        'lots': len(quality_hold_df),
                        'qtyPcs': int(quality_hold_df['QTY'].sum())
                    },
                    'nonQualityHold': {
                        'lots': len(non_quality_hold_df),
                        'qtyPcs': int(non_quality_hold_df['QTY'].sum())
                    }
                },
                'dataUpdateDate': get_cached_sys_date()
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based summary calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_summary_from_oracle(include_dummy, workorder, lotid, package, pj_type)


def _get_wip_summary_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get WIP summary directly from Oracle (fallback)."""
    try:
        # Build conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)

        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        # Load SQL template and build query
        base_sql = SQLLoader.load("wip/summary")
        builder.base_sql = base_sql

        # Replace NON_QUALITY_REASONS placeholder (must be literal values for CASE expressions)
        non_quality_list = CommonFilters.get_non_quality_reasons_sql()
        builder.base_sql = builder.base_sql.replace("{{ NON_QUALITY_REASONS }}", non_quality_list)

        sql, params = builder.build()
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return None

        row = df.iloc[0]
        return {
            'totalLots': int(row['TOTAL_LOTS'] or 0),
            'totalQtyPcs': int(row['TOTAL_QTY_PCS'] or 0),
            'byWipStatus': {
                'run': {
                    'lots': int(row['RUN_LOTS'] or 0),
                    'qtyPcs': int(row['RUN_QTY_PCS'] or 0)
                },
                'queue': {
                    'lots': int(row['QUEUE_LOTS'] or 0),
                    'qtyPcs': int(row['QUEUE_QTY_PCS'] or 0)
                },
                'hold': {
                    'lots': int(row['HOLD_LOTS'] or 0),
                    'qtyPcs': int(row['HOLD_QTY_PCS'] or 0)
                },
                'qualityHold': {
                    'lots': int(row['QUALITY_HOLD_LOTS'] or 0),
                    'qtyPcs': int(row['QUALITY_HOLD_QTY_PCS'] or 0)
                },
                'nonQualityHold': {
                    'lots': int(row['NON_QUALITY_HOLD_LOTS'] or 0),
                    'qtyPcs': int(row['NON_QUALITY_HOLD_QTY_PCS'] or 0)
                }
            },
            'dataUpdateDate': str(row['DATA_UPDATE_DATE']) if row['DATA_UPDATE_DATE'] else None
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP summary query failed: {exc}")
        return None


def get_wip_matrix(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get workcenter x product line matrix for overview dashboard.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)

    Returns:
        Dict with matrix data:
        - workcenters: List of workcenter groups (sorted by WORKCENTERSEQUENCE_GROUP)
        - packages: List of product lines (sorted by total QTY desc)
        - matrix: Dict of {workcenter: {package: qty}}
        - workcenter_totals: Dict of {workcenter: total_qty}
        - package_totals: Dict of {package: total_qty}
        - grand_total: Overall total
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder, lotid)
            df = _add_wip_status_columns(df)

            # Filter by WORKCENTER_GROUP and PACKAGE_LEF
            df = df[df['WORKCENTER_GROUP'].notna() & df['PACKAGE_LEF'].notna()]

            # Apply package filter
            if package:
                df = df[df['PACKAGE_LEF'] == package]

            # Apply pj_type filter
            if pj_type and 'PJ_TYPE' in df.columns:
                df = df[df['PJ_TYPE'] == pj_type]

            # WIP status filter
            if status:
                status_upper = status.upper()
                df = df[df['WIP_STATUS'] == status_upper]

                # Hold type sub-filter
                if status_upper == 'HOLD' and hold_type:
                    if hold_type == 'quality':
                        df = df[df['IS_QUALITY_HOLD']]
                    elif hold_type == 'non-quality':
                        df = df[df['IS_NON_QUALITY_HOLD']]

            if df.empty:
                return {
                    'workcenters': [],
                    'packages': [],
                    'matrix': {},
                    'workcenter_totals': {},
                    'package_totals': {},
                    'grand_total': 0
                }

            return _build_matrix_result(df)
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based matrix calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_matrix_from_oracle(include_dummy, workorder, lotid, status, hold_type, package, pj_type)


def _build_matrix_result(df: pd.DataFrame) -> Dict[str, Any]:
    """Build matrix result from DataFrame."""
    # Group by workcenter and package
    grouped = df.groupby(['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP', 'PACKAGE_LEF'])['QTY'].sum().reset_index()

    if grouped.empty:
        return {
            'workcenters': [],
            'packages': [],
            'matrix': {},
            'workcenter_totals': {},
            'package_totals': {},
            'grand_total': 0
        }

    # Build matrix
    matrix = {}
    workcenter_totals = {}
    package_totals = {}

    # Get unique workcenters sorted by sequence
    wc_order = grouped.drop_duplicates('WORKCENTER_GROUP')[['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP']]
    wc_order = wc_order.sort_values('WORKCENTERSEQUENCE_GROUP')
    workcenters = wc_order['WORKCENTER_GROUP'].tolist()

    # Build matrix and totals
    for _, row in grouped.iterrows():
        wc = row['WORKCENTER_GROUP']
        pkg = row['PACKAGE_LEF']
        qty = int(row['QTY'] or 0)

        if wc not in matrix:
            matrix[wc] = {}
        matrix[wc][pkg] = qty

        workcenter_totals[wc] = workcenter_totals.get(wc, 0) + qty
        package_totals[pkg] = package_totals.get(pkg, 0) + qty

    # Sort packages by total qty desc
    packages = sorted(package_totals.keys(), key=lambda x: package_totals[x], reverse=True)

    grand_total = sum(workcenter_totals.values())

    return {
        'workcenters': workcenters,
        'packages': packages,
        'matrix': matrix,
        'workcenter_totals': workcenter_totals,
        'package_totals': package_totals,
        'grand_total': grand_total
    }


def _get_wip_matrix_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get WIP matrix directly from Oracle (fallback)."""
    try:
        # Build conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        builder.add_is_not_null("WORKCENTER_GROUP")
        builder.add_is_not_null("PACKAGE_LEF")

        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        # WIP status filter
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) > 0")
            elif status_upper == 'HOLD':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) > 0")
                # Hold type sub-filter
                if hold_type:
                    _add_hold_type_conditions(builder, hold_type)
            elif status_upper == 'QUEUE':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) = 0")

        # Load SQL template and build query
        base_sql = SQLLoader.load("wip/matrix")
        builder.base_sql = base_sql
        sql, params = builder.build()

        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return {
                'workcenters': [],
                'packages': [],
                'matrix': {},
                'workcenter_totals': {},
                'package_totals': {},
                'grand_total': 0
            }

        return _build_matrix_result(df)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP matrix query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_wip_hold_summary(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get hold summary grouped by hold reason.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)

    Returns:
        Dict with hold items sorted by lots desc:
        - items: List of {reason, lots, qty}
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder, lotid)
            df = _add_wip_status_columns(df)

            # Filter for HOLD status with reason
            df = df[(df['WIP_STATUS'] == 'HOLD') & df['HOLDREASONNAME'].notna()]

            if df.empty:
                return {'items': []}

            # Group by hold reason
            grouped = df.groupby('HOLDREASONNAME').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            grouped.columns = ['REASON', 'LOTS', 'QTY']
            grouped = grouped.sort_values('LOTS', ascending=False)

            items = []
            for _, row in grouped.iterrows():
                reason = row['REASON']
                items.append({
                    'reason': reason,
                    'lots': int(row['LOTS'] or 0),
                    'qty': int(row['QTY'] or 0),
                    'holdType': 'quality' if is_quality_hold(reason) else 'non-quality'
                })

            return {'items': items}
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold summary calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_hold_summary_from_oracle(include_dummy, workorder, lotid)


def _get_wip_hold_summary_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get WIP hold summary directly from Oracle (fallback)."""
    try:
        # Build conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_is_not_null("HOLDREASONNAME")

        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                HOLDREASONNAME as REASON,
                COUNT(*) as LOTS,
                SUM(QTY) as QTY
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY HOLDREASONNAME
            ORDER BY COUNT(*) DESC
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return {'items': []}

        items = []
        for _, row in df.iterrows():
            reason = row['REASON']
            items.append({
                'reason': reason,
                'lots': int(row['LOTS'] or 0),
                'qty': int(row['QTY'] or 0),
                'holdType': 'quality' if is_quality_hold(reason) else 'non-quality'
            })

        return {'items': items}
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP hold summary query failed: {exc}")
        return None


# ============================================================
# Detail API Functions
# ============================================================

def get_wip_detail(
    workcenter: str,
    package: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 100
) -> Optional[Dict[str, Any]]:
    """Get WIP detail for a specific workcenter group.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        workcenter: WORKCENTER_GROUP name
        package: Optional PACKAGE_LEF filter
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        include_dummy: If True, include DUMMY lots (default: False)
        page: Page number (1-based)
        page_size: Number of records per page

    Returns:
        Dict with:
        - workcenter: The workcenter group name
        - summary: {totalLots, runLots, queueLots, holdLots, qualityHoldLots, nonQualityHoldLots}
        - specs: List of spec names (sorted by SPECSEQUENCE)
        - lots: List of lot details
        - pagination: {page, page_size, total_count, total_pages}
        - sys_date: Data timestamp
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder, lotid)
            df = _add_wip_status_columns(df)

            # Filter by workcenter
            df = df[df['WORKCENTER_GROUP'] == workcenter]

            if package:
                df = df[df['PACKAGE_LEF'] == package]

            # Calculate summary before status filter
            summary_df = df.copy()
            run_lots = len(summary_df[summary_df['WIP_STATUS'] == 'RUN'])
            queue_lots = len(summary_df[summary_df['WIP_STATUS'] == 'QUEUE'])
            hold_lots = len(summary_df[summary_df['WIP_STATUS'] == 'HOLD'])
            quality_hold_lots = len(summary_df[summary_df['IS_QUALITY_HOLD']])
            non_quality_hold_lots = len(summary_df[summary_df['IS_NON_QUALITY_HOLD']])
            total_lots = len(summary_df)

            summary = {
                'totalLots': total_lots,
                'runLots': run_lots,
                'queueLots': queue_lots,
                'holdLots': hold_lots,
                'qualityHoldLots': quality_hold_lots,
                'nonQualityHoldLots': non_quality_hold_lots
            }

            # Apply status filter for lots list
            if status:
                status_upper = status.upper()
                df = df[df['WIP_STATUS'] == status_upper]

                if status_upper == 'HOLD' and hold_type:
                    if hold_type == 'quality':
                        df = df[df['IS_QUALITY_HOLD']]
                    elif hold_type == 'non-quality':
                        df = df[df['IS_NON_QUALITY_HOLD']]

            # Get specs (sorted by SPECSEQUENCE if available)
            specs_df = df[df['SPECNAME'].notna()][['SPECNAME', 'SPECSEQUENCE']].drop_duplicates()
            if 'SPECSEQUENCE' in specs_df.columns:
                specs_df = specs_df.sort_values('SPECSEQUENCE')
            specs = specs_df['SPECNAME'].tolist() if not specs_df.empty else []

            # Pagination
            filtered_count = len(df)
            total_pages = (filtered_count + page_size - 1) // page_size if filtered_count > 0 else 1
            offset = (page - 1) * page_size

            # Sort by LOTID and paginate
            df = df.sort_values('LOTID')
            page_df = df.iloc[offset:offset + page_size]

            lots = []
            for _, row in page_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row.get('LOTID')),
                    'equipment': _safe_value(row.get('EQUIPMENTS')),
                    'wipStatus': _safe_value(row.get('WIP_STATUS')),
                    'holdReason': _safe_value(row.get('HOLDREASONNAME')),
                    'qty': int(row.get('QTY', 0) or 0),
                    'package': _safe_value(row.get('PACKAGE_LEF')),
                    'spec': _safe_value(row.get('SPECNAME'))
                })

            return {
                'workcenter': workcenter,
                'summary': summary,
                'specs': specs,
                'lots': lots,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': filtered_count,
                    'total_pages': total_pages
                },
                'sys_date': get_cached_sys_date()
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based detail calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_detail_from_oracle(
        workcenter, package, status, hold_type, workorder, lotid, include_dummy, page, page_size
    )


def _get_wip_detail_from_oracle(
    workcenter: str,
    package: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 100
) -> Optional[Dict[str, Any]]:
    """Get WIP detail directly from Oracle (fallback)."""
    try:
        # Build WHERE conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        builder.add_param_condition("WORKCENTER_GROUP", workcenter)

        if package:
            builder.add_param_condition("PACKAGE_LEF", package)

        # WIP status filter (RUN/QUEUE/HOLD based on EQUIPMENTCOUNT and CURRENTHOLDCOUNT)
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) > 0")
            elif status_upper == 'HOLD':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) > 0")
                # Hold type sub-filter
                if hold_type:
                    _add_hold_type_conditions(builder, hold_type)
            elif status_upper == 'QUEUE':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) = 0")

        where_clause, params = builder.build_where_only()

        # Build summary conditions (without status/hold_type filter for full breakdown)
        summary_builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        summary_builder.add_param_condition("WORKCENTER_GROUP", workcenter)
        if package:
            summary_builder.add_param_condition("PACKAGE_LEF", package)

        summary_where, summary_params = summary_builder.build_where_only()
        non_quality_list = CommonFilters.get_non_quality_reasons_sql()

        summary_sql = f"""
            SELECT
                COUNT(*) as TOTAL_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) > 0 THEN 1 ELSE 0 END) as RUN_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) = 0 THEN 1 ELSE 0 END) as QUEUE_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0 THEN 1 ELSE 0 END) as HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND (HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ({non_quality_list}))
                          THEN 1 ELSE 0 END) as QUALITY_HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND HOLDREASONNAME IN ({non_quality_list})
                          THEN 1 ELSE 0 END) as NON_QUALITY_HOLD_LOTS,
                MAX(SYS_DATE) as SYS_DATE
            FROM {WIP_VIEW}
            {summary_where}
        """

        summary_df = read_sql_df(summary_sql, summary_params)

        if summary_df is None or summary_df.empty:
            return None

        summary_row = summary_df.iloc[0]
        sys_date = str(summary_row['SYS_DATE']) if summary_row['SYS_DATE'] else None

        # Calculate counts from summary
        total_lots = int(summary_row['TOTAL_LOTS'] or 0)
        run_lots = int(summary_row['RUN_LOTS'] or 0)
        queue_lots = int(summary_row['QUEUE_LOTS'] or 0)
        hold_lots = int(summary_row['HOLD_LOTS'] or 0)
        quality_hold_lots = int(summary_row['QUALITY_HOLD_LOTS'] or 0)
        non_quality_hold_lots = int(summary_row['NON_QUALITY_HOLD_LOTS'] or 0)

        # Determine filtered count based on status filter
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                filtered_count = run_lots
            elif status_upper == 'QUEUE':
                filtered_count = queue_lots
            elif status_upper == 'HOLD':
                if hold_type == 'quality':
                    filtered_count = quality_hold_lots
                elif hold_type == 'non-quality':
                    filtered_count = non_quality_hold_lots
                else:
                    filtered_count = hold_lots
            else:
                filtered_count = total_lots
        else:
            filtered_count = total_lots

        summary = {
            'totalLots': total_lots,
            'runLots': run_lots,
            'queueLots': queue_lots,
            'holdLots': hold_lots,
            'qualityHoldLots': quality_hold_lots,
            'nonQualityHoldLots': non_quality_hold_lots
        }

        # Get unique specs for this workcenter (sorted by SPECSEQUENCE)
        specs_sql = f"""
            SELECT DISTINCT SPECNAME, SPECSEQUENCE
            FROM {WIP_VIEW}
            {where_clause}
              AND SPECNAME IS NOT NULL
            ORDER BY SPECSEQUENCE
        """

        specs_df = read_sql_df(specs_sql, params)
        specs = specs_df['SPECNAME'].tolist() if specs_df is not None and not specs_df.empty else []

        # Get paginated lot details using SQL file with bind variables
        offset = (page - 1) * page_size
        base_detail_sql = SQLLoader.load("wip/detail")
        detail_sql = base_detail_sql.replace("{{ WHERE_CLAUSE }}", where_clause)

        # Add pagination params to existing params
        detail_params = params.copy()
        detail_params['offset'] = offset
        detail_params['limit'] = page_size

        lots_df = read_sql_df(detail_sql, detail_params)

        lots = []
        if lots_df is not None and not lots_df.empty:
            for _, row in lots_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row['LOTID']),
                    'equipment': _safe_value(row['EQUIPMENTS']),
                    'wipStatus': _safe_value(row['WIP_STATUS']),
                    'holdReason': _safe_value(row['HOLDREASONNAME']),
                    'qty': int(row['QTY'] or 0),
                    'package': _safe_value(row['PACKAGE_LEF']),
                    'spec': _safe_value(row['SPECNAME'])
                })

        total_pages = (filtered_count + page_size - 1) // page_size if filtered_count > 0 else 1

        return {
            'workcenter': workcenter,
            'summary': summary,
            'specs': specs,
            'lots': lots,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': filtered_count,
                'total_pages': total_pages
            },
            'sys_date': sys_date
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP detail query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Meta API Functions
# ============================================================

def get_workcenters(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get list of workcenter groups with lot counts.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of {name, lot_count} sorted by WORKCENTERSEQUENCE_GROUP
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)
            df = df[df['WORKCENTER_GROUP'].notna()]

            if df.empty:
                return []

            # Group by workcenter with sequence
            grouped = df.groupby(['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP']).size().reset_index(name='LOT_COUNT')
            grouped = grouped.sort_values('WORKCENTERSEQUENCE_GROUP')

            result = []
            for _, row in grouped.iterrows():
                result.append({
                    'name': row['WORKCENTER_GROUP'],
                    'lot_count': int(row['LOT_COUNT'] or 0)
                })

            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based workcenters calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_workcenters_from_oracle(include_dummy)


def _get_workcenters_from_oracle(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get workcenters directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_is_not_null("WORKCENTER_GROUP")
        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                WORKCENTER_GROUP,
                WORKCENTERSEQUENCE_GROUP,
                COUNT(*) as LOT_COUNT
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP
            ORDER BY WORKCENTERSEQUENCE_GROUP
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['WORKCENTER_GROUP'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Workcenters query failed: {exc}")
        return None


def get_packages(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get list of packages (product lines) with lot counts.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of {name, lot_count} sorted by lot_count desc
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)
            df = df[df['PACKAGE_LEF'].notna()]

            if df.empty:
                return []

            # Group by package and count
            grouped = df.groupby('PACKAGE_LEF').size().reset_index(name='LOT_COUNT')
            grouped = grouped.sort_values('LOT_COUNT', ascending=False)

            result = []
            for _, row in grouped.iterrows():
                result.append({
                    'name': row['PACKAGE_LEF'],
                    'lot_count': int(row['LOT_COUNT'] or 0)
                })

            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based packages calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_packages_from_oracle(include_dummy)


def _get_packages_from_oracle(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get packages directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_is_not_null("PACKAGE_LEF")
        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                PACKAGE_LEF,
                COUNT(*) as LOT_COUNT
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY PACKAGE_LEF
            ORDER BY COUNT(*) DESC
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['PACKAGE_LEF'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Packages query failed: {exc}")
        return None


# ============================================================
# Search API Functions
# ============================================================

def search_workorders(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search for WORKORDER values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        lotid: Optional LOTID cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)
        pj_type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        List of matching WORKORDER values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not lotid and not package and not pj_type:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("workorders", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, lotid=lotid)
            df = df[df['WORKORDER'].notna()]

            # Apply cross-filters
            if package and 'PACKAGE_LEF' in df.columns:
                df = df[df['PACKAGE_LEF'] == package]
            if pj_type and 'PJ_TYPE' in df.columns:
                df = df[df['PJ_TYPE'] == pj_type]

            # Filter by search query (case-insensitive)
            df = df[df['WORKORDER'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct, sorted, limited results
            result = df['WORKORDER'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based workorder search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_workorders_from_oracle(q, limit, include_dummy, lotid, package, pj_type)


def _search_workorders_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search workorders directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, lotid=lotid)
        builder.add_like_condition("WORKORDER", q, position="both")
        builder.add_is_not_null("WORKORDER")

        # Apply cross-filters
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT DISTINCT WORKORDER
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY WORKORDER
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['WORKORDER'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search workorders failed: {exc}")
        return None


def search_lot_ids(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search for LOTID values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)
        pj_type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        List of matching LOTID values
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not workorder and not package and not pj_type:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("lotids", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder=workorder)

            # Apply cross-filters
            if package and 'PACKAGE_LEF' in df.columns:
                df = df[df['PACKAGE_LEF'] == package]
            if pj_type and 'PJ_TYPE' in df.columns:
                df = df[df['PJ_TYPE'] == pj_type]

            # Filter by search query (case-insensitive)
            df = df[df['LOTID'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get sorted, limited results
            result = df['LOTID'].sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based lot ID search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_lot_ids_from_oracle(q, limit, include_dummy, workorder, package, pj_type)


def _search_lot_ids_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search lot IDs directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, workorder=workorder)
        builder.add_like_condition("LOTID", q, position="both")

        # Apply cross-filters
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT LOTID
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY LOTID
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['LOTID'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search lot IDs failed: {exc}")
        return None


def search_packages(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search for PACKAGE_LEF values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        lotid: Optional LOTID cross-filter (fuzzy match)
        pj_type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        List of matching PACKAGE_LEF values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not workorder and not lotid and not pj_type:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("packages", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder=workorder, lotid=lotid)

            # Check if PACKAGE_LEF column exists
            if 'PACKAGE_LEF' not in df.columns:
                logger.warning("PACKAGE_LEF column not found in cache")
                return _search_packages_from_oracle(q, limit, include_dummy, workorder, lotid, pj_type)

            df = df[df['PACKAGE_LEF'].notna()]

            # Apply cross-filter
            if pj_type and 'PJ_TYPE' in df.columns:
                df = df[df['PJ_TYPE'] == pj_type]

            # Filter by search query (case-insensitive)
            df = df[df['PACKAGE_LEF'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct values sorted
            result = df['PACKAGE_LEF'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based package search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_packages_from_oracle(q, limit, include_dummy, workorder, lotid, pj_type)


def _search_packages_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search packages directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, workorder=workorder, lotid=lotid)
        builder.add_like_condition("PACKAGE_LEF", q, position="both")
        builder.add_is_not_null("PACKAGE_LEF")

        # Apply cross-filter
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT DISTINCT PACKAGE_LEF
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY PACKAGE_LEF
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['PACKAGE_LEF'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search packages failed: {exc}")
        return None


def search_types(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None
) -> Optional[List[str]]:
    """Search for PJ_TYPE values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        lotid: Optional LOTID cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)

    Returns:
        List of matching PJ_TYPE values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not workorder and not lotid and not package:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("types", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy, workorder=workorder, lotid=lotid)

            # Check if PJ_TYPE column exists
            if 'PJ_TYPE' not in df.columns:
                logger.warning("PJ_TYPE column not found in cache")
                return _search_types_from_oracle(q, limit, include_dummy, workorder, lotid, package)

            df = df[df['PJ_TYPE'].notna()]

            # Apply cross-filter
            if package and 'PACKAGE_LEF' in df.columns:
                df = df[df['PACKAGE_LEF'] == package]

            # Filter by search query (case-insensitive)
            df = df[df['PJ_TYPE'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct values sorted
            result = df['PJ_TYPE'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based type search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_types_from_oracle(q, limit, include_dummy, workorder, lotid, package)


def _search_types_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None
) -> Optional[List[str]]:
    """Search types directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, workorder=workorder, lotid=lotid)
        builder.add_like_condition("PJ_TYPE", q, position="both")
        builder.add_is_not_null("PJ_TYPE")

        # Apply cross-filter
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT DISTINCT PJ_TYPE
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY PJ_TYPE
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['PJ_TYPE'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search types failed: {exc}")
        return None


# ============================================================
# Hold Detail API Functions
# ============================================================

def get_hold_detail_summary(
    reason: str,
    include_dummy: bool = False
) -> Optional[Dict[str, Any]]:
    """Get summary statistics for a specific hold reason.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        reason: The HOLDREASONNAME to filter by
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        Dict with totalLots, totalQty, avgAge, maxAge, workcenterCount
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)
            df = _add_wip_status_columns(df)

            # Filter for HOLD status with matching reason
            df = df[(df['WIP_STATUS'] == 'HOLD') & (df['HOLDREASONNAME'] == reason)]

            if df.empty:
                return {
                    'totalLots': 0,
                    'totalQty': 0,
                    'avgAge': 0,
                    'maxAge': 0,
                    'workcenterCount': 0
                }

            # Ensure AGEBYDAYS is numeric
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)

            return {
                'totalLots': len(df),
                'totalQty': int(df['QTY'].sum()),
                'avgAge': round(float(df['AGEBYDAYS'].mean()), 1),
                'maxAge': float(df['AGEBYDAYS'].max()),
                'workcenterCount': df['WORKCENTER_GROUP'].nunique()
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold detail summary failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_hold_detail_summary_from_oracle(reason, include_dummy)


def _get_hold_detail_summary_from_oracle(
    reason: str,
    include_dummy: bool = False
) -> Optional[Dict[str, Any]]:
    """Get hold detail summary directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        builder.add_param_condition("HOLDREASONNAME", reason)
        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                COUNT(*) AS TOTAL_LOTS,
                SUM(QTY) AS TOTAL_QTY,
                ROUND(AVG(AGEBYDAYS), 1) AS AVG_AGE,
                MAX(AGEBYDAYS) AS MAX_AGE,
                COUNT(DISTINCT WORKCENTER_GROUP) AS WORKCENTER_COUNT
            FROM {WIP_VIEW}
            {where_clause}
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return None

        row = df.iloc[0]
        return {
            'totalLots': int(row['TOTAL_LOTS'] or 0),
            'totalQty': int(row['TOTAL_QTY'] or 0),
            'avgAge': float(row['AVG_AGE']) if row['AVG_AGE'] else 0,
            'maxAge': float(row['MAX_AGE']) if row['MAX_AGE'] else 0,
            'workcenterCount': int(row['WORKCENTER_COUNT'] or 0)
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold detail summary query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_hold_detail_distribution(
    reason: str,
    include_dummy: bool = False
) -> Optional[Dict[str, Any]]:
    """Get distribution statistics for a specific hold reason.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        reason: The HOLDREASONNAME to filter by
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        Dict with byWorkcenter, byPackage, byAge distributions
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)
            df = _add_wip_status_columns(df)

            # Filter for HOLD status with matching reason
            df = df[(df['WIP_STATUS'] == 'HOLD') & (df['HOLDREASONNAME'] == reason)]

            total_lots = len(df)

            if total_lots == 0:
                return {
                    'byWorkcenter': [],
                    'byPackage': [],
                    'byAge': []
                }

            # Ensure numeric columns
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)

            # By Workcenter
            wc_df = df[df['WORKCENTER_GROUP'].notna()].groupby('WORKCENTER_GROUP').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            wc_df.columns = ['NAME', 'LOTS', 'QTY']
            wc_df = wc_df.sort_values('LOTS', ascending=False)

            by_workcenter = []
            for _, row in wc_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_workcenter.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

            # By Package
            pkg_df = df[df['PACKAGE_LEF'].notna()].groupby('PACKAGE_LEF').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            pkg_df.columns = ['NAME', 'LOTS', 'QTY']
            pkg_df = pkg_df.sort_values('LOTS', ascending=False)

            by_package = []
            for _, row in pkg_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_package.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

            # By Age - compute age range
            def get_age_range(age):
                if age < 1:
                    return '0-1'
                elif age < 3:
                    return '1-3'
                elif age < 7:
                    return '3-7'
                else:
                    return '7+'

            df['AGE_RANGE'] = df['AGEBYDAYS'].apply(get_age_range)

            age_df = df.groupby('AGE_RANGE').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            age_df.columns = ['AGE_RANGE', 'LOTS', 'QTY']

            # Define age ranges in order
            age_labels = {
                '0-1': '0-1天',
                '1-3': '1-3天',
                '3-7': '3-7天',
                '7+': '7+天'
            }
            age_order = ['0-1', '1-3', '3-7', '7+']

            # Build age distribution with all ranges (even if 0)
            age_data = {r: {'lots': 0, 'qty': 0} for r in age_order}
            for _, row in age_df.iterrows():
                range_key = row['AGE_RANGE']
                if range_key in age_data:
                    age_data[range_key] = {
                        'lots': int(row['LOTS'] or 0),
                        'qty': int(row['QTY'] or 0)
                    }

            by_age = []
            for r in age_order:
                lots = age_data[r]['lots']
                by_age.append({
                    'range': r,
                    'label': age_labels[r],
                    'lots': lots,
                    'qty': age_data[r]['qty'],
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

            return {
                'byWorkcenter': by_workcenter,
                'byPackage': by_package,
                'byAge': by_age
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold detail distribution failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_hold_detail_distribution_from_oracle(reason, include_dummy)


def _get_hold_detail_distribution_from_oracle(
    reason: str,
    include_dummy: bool = False
) -> Optional[Dict[str, Any]]:
    """Get hold detail distribution directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        builder.add_param_condition("HOLDREASONNAME", reason)
        where_clause, params = builder.build_where_only()

        # Get total for percentage calculation
        total_sql = f"""
            SELECT COUNT(*) AS TOTAL_LOTS, SUM(QTY) AS TOTAL_QTY
            FROM {WIP_VIEW}
            {where_clause}
        """
        total_df = read_sql_df(total_sql, params)
        total_lots = int(total_df.iloc[0]['TOTAL_LOTS'] or 0) if total_df is not None else 0

        if total_lots == 0:
            return {
                'byWorkcenter': [],
                'byPackage': [],
                'byAge': []
            }

        # By Workcenter
        wc_sql = f"""
            SELECT
                WORKCENTER_GROUP AS NAME,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY
            FROM {WIP_VIEW}
            {where_clause}
              AND WORKCENTER_GROUP IS NOT NULL
            GROUP BY WORKCENTER_GROUP
            ORDER BY COUNT(*) DESC
        """
        wc_df = read_sql_df(wc_sql, params)
        by_workcenter = []
        if wc_df is not None and not wc_df.empty:
            for _, row in wc_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_workcenter.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

        # By Package
        pkg_sql = f"""
            SELECT
                PACKAGE_LEF AS NAME,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY
            FROM {WIP_VIEW}
            {where_clause}
              AND PACKAGE_LEF IS NOT NULL
            GROUP BY PACKAGE_LEF
            ORDER BY COUNT(*) DESC
        """
        pkg_df = read_sql_df(pkg_sql, params)
        by_package = []
        if pkg_df is not None and not pkg_df.empty:
            for _, row in pkg_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_package.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

        # By Age (station dwell time)
        age_sql = f"""
            SELECT
                CASE
                    WHEN AGEBYDAYS < 1 THEN '0-1'
                    WHEN AGEBYDAYS < 3 THEN '1-3'
                    WHEN AGEBYDAYS < 7 THEN '3-7'
                    ELSE '7+'
                END AS AGE_RANGE,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY CASE
                WHEN AGEBYDAYS < 1 THEN '0-1'
                WHEN AGEBYDAYS < 3 THEN '1-3'
                WHEN AGEBYDAYS < 7 THEN '3-7'
                ELSE '7+'
            END
        """
        age_df = read_sql_df(age_sql, params)

        # Define age ranges in order
        age_labels = {
            '0-1': '0-1天',
            '1-3': '1-3天',
            '3-7': '3-7天',
            '7+': '7+天'
        }
        age_order = ['0-1', '1-3', '3-7', '7+']

        # Build age distribution with all ranges (even if 0)
        age_data = {r: {'lots': 0, 'qty': 0} for r in age_order}
        if age_df is not None and not age_df.empty:
            for _, row in age_df.iterrows():
                range_key = row['AGE_RANGE']
                if range_key in age_data:
                    age_data[range_key] = {
                        'lots': int(row['LOTS'] or 0),
                        'qty': int(row['QTY'] or 0)
                    }

        by_age = []
        for r in age_order:
            lots = age_data[r]['lots']
            by_age.append({
                'range': r,
                'label': age_labels[r],
                'lots': lots,
                'qty': age_data[r]['qty'],
                'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
            })

        return {
            'byWorkcenter': by_workcenter,
            'byPackage': by_package,
            'byAge': by_age
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold detail distribution query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_hold_detail_lots(
    reason: str,
    workcenter: Optional[str] = None,
    package: Optional[str] = None,
    age_range: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 50
) -> Optional[Dict[str, Any]]:
    """Get paginated lot details for a specific hold reason.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        reason: The HOLDREASONNAME to filter by
        workcenter: Optional WORKCENTER_GROUP filter
        package: Optional PACKAGE_LEF filter
        age_range: Optional age range filter ('0-1', '1-3', '3-7', '7+')
        include_dummy: If True, include DUMMY lots (default: False)
        page: Page number (1-based)
        page_size: Number of records per page

    Returns:
        Dict with lots list, pagination info, and active filters
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)
            df = _add_wip_status_columns(df)

            # Filter for HOLD status with matching reason
            df = df[(df['WIP_STATUS'] == 'HOLD') & (df['HOLDREASONNAME'] == reason)]

            # Ensure numeric columns
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)

            # Optional filters
            if workcenter:
                df = df[df['WORKCENTER_GROUP'] == workcenter]
            if package:
                df = df[df['PACKAGE_LEF'] == package]
            if age_range:
                if age_range == '0-1':
                    df = df[(df['AGEBYDAYS'] >= 0) & (df['AGEBYDAYS'] < 1)]
                elif age_range == '1-3':
                    df = df[(df['AGEBYDAYS'] >= 1) & (df['AGEBYDAYS'] < 3)]
                elif age_range == '3-7':
                    df = df[(df['AGEBYDAYS'] >= 3) & (df['AGEBYDAYS'] < 7)]
                elif age_range == '7+':
                    df = df[df['AGEBYDAYS'] >= 7]

            total = len(df)

            # Sort by age descending, then LOTID
            df = df.sort_values(['AGEBYDAYS', 'LOTID'], ascending=[False, True])

            # Pagination
            offset = (page - 1) * page_size
            page_df = df.iloc[offset:offset + page_size]

            lots = []
            for _, row in page_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row.get('LOTID')),
                    'workorder': _safe_value(row.get('WORKORDER')),
                    'qty': int(row.get('QTY', 0) or 0),
                    'package': _safe_value(row.get('PACKAGE_LEF')),
                    'workcenter': _safe_value(row.get('WORKCENTER_GROUP')),
                    'spec': _safe_value(row.get('SPECNAME')),
                    'age': round(float(row.get('AGEBYDAYS', 0) or 0), 1),
                    'holdBy': _safe_value(row.get('HOLDEMP')),
                    'dept': _safe_value(row.get('DEPTNAME')),
                    'holdComment': _safe_value(row.get('COMMENT_HOLD'))
                })

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return {
                'lots': lots,
                'pagination': {
                    'page': page,
                    'perPage': page_size,
                    'total': total,
                    'totalPages': total_pages
                },
                'filters': {
                    'workcenter': workcenter,
                    'package': package,
                    'ageRange': age_range
                }
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold detail lots failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_hold_detail_lots_from_oracle(
        reason, workcenter, package, age_range, include_dummy, page, page_size
    )


def _get_hold_detail_lots_from_oracle(
    reason: str,
    workcenter: Optional[str] = None,
    package: Optional[str] = None,
    age_range: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 50
) -> Optional[Dict[str, Any]]:
    """Get hold detail lots directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        builder.add_param_condition("HOLDREASONNAME", reason)

        # Optional filters
        if workcenter:
            builder.add_param_condition("WORKCENTER_GROUP", workcenter)
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if age_range:
            if age_range == '0-1':
                builder.add_condition("AGEBYDAYS >= 0 AND AGEBYDAYS < 1")
            elif age_range == '1-3':
                builder.add_condition("AGEBYDAYS >= 1 AND AGEBYDAYS < 3")
            elif age_range == '3-7':
                builder.add_condition("AGEBYDAYS >= 3 AND AGEBYDAYS < 7")
            elif age_range == '7+':
                builder.add_condition("AGEBYDAYS >= 7")

        where_clause, params = builder.build_where_only()

        # Get total count
        count_sql = f"""
            SELECT COUNT(*) AS TOTAL
            FROM {WIP_VIEW}
            {where_clause}
        """
        count_df = read_sql_df(count_sql, params)
        total = int(count_df.iloc[0]['TOTAL'] or 0) if count_df is not None else 0

        # Get paginated lots with bind variables
        offset = (page - 1) * page_size
        lots_params = params.copy()
        lots_params['offset'] = offset
        lots_params['limit'] = page_size

        lots_sql = f"""
            SELECT * FROM (
                SELECT
                    LOTID,
                    WORKORDER,
                    QTY,
                    PACKAGE_LEF AS PACKAGE,
                    WORKCENTER_GROUP AS WORKCENTER,
                    SPECNAME AS SPEC,
                    ROUND(AGEBYDAYS, 1) AS AGE,
                    HOLDEMP AS HOLD_BY,
                    DEPTNAME AS DEPT,
                    COMMENT_HOLD AS HOLD_COMMENT,
                    ROW_NUMBER() OVER (ORDER BY AGEBYDAYS DESC, LOTID) AS RN
                FROM {WIP_VIEW}
                {where_clause}
            )
            WHERE RN > :offset AND RN <= :offset + :limit
            ORDER BY RN
        """
        lots_df = read_sql_df(lots_sql, lots_params)

        lots = []
        if lots_df is not None and not lots_df.empty:
            for _, row in lots_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row['LOTID']),
                    'workorder': _safe_value(row['WORKORDER']),
                    'qty': int(row['QTY'] or 0),
                    'package': _safe_value(row['PACKAGE']),
                    'workcenter': _safe_value(row['WORKCENTER']),
                    'spec': _safe_value(row['SPEC']),
                    'age': float(row['AGE']) if row['AGE'] else 0,
                    'holdBy': _safe_value(row['HOLD_BY']),
                    'dept': _safe_value(row['DEPT']),
                    'holdComment': _safe_value(row['HOLD_COMMENT'])
                })

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return {
            'lots': lots,
            'pagination': {
                'page': page,
                'perPage': page_size,
                'total': total,
                'totalPages': total_pages
            },
            'filters': {
                'workcenter': workcenter,
                'package': package,
                'ageRange': age_range
            }
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold detail lots query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Lot Detail API Functions
# ============================================================

# Field labels mapping for lot detail display (PowerBI naming convention)
LOT_DETAIL_FIELD_LABELS = {
    'lotId': 'Run Card Lot ID',
    'workorder': 'Work Order ID',
    'qty': 'Lot Qty(pcs)',
    'qty2': 'Lot Qty(Wafer pcs)',
    'status': 'Run Card Status',
    'holdReason': 'Hold Reason',
    'holdCount': 'Hold Count',
    'owner': 'Work Order Owner',
    'startDate': 'Run Card Start Date',
    'uts': 'UTS',
    'product': 'Product P/N',
    'productLine': 'Package',
    'packageLef': 'Package(LF)',
    'pjFunction': 'Product Function',
    'pjType': 'Product Type',
    'bop': 'BOP',
    'waferLotId': 'Wafer Lot ID',
    'waferPn': 'Wafer P/N',
    'waferLotPrefix': 'Wafer Lot ID(Prefix)',
    'spec': 'Spec',
    'specSequence': 'Spec Sequence',
    'workcenter': 'Work Center',
    'workcenterSequence': 'Work Center Sequence',
    'workcenterGroup': 'Work Center(Group)',
    'workcenterShort': 'Work Center(Short)',
    'ageByDays': 'Age By Days',
    'equipment': 'Equipment ID',
    'equipmentCount': 'Equipment Count',
    'workflow': 'Work Flow Name',
    'dateCode': 'Product Date Code',
    'leadframeName': 'LF Material Part',
    'leadframeOption': 'LF Option ID',
    'compoundName': 'Compound Material Part',
    'location': 'Run Card Location',
    'ncrId': 'NCR ID',
    'ncrDate': 'NCR-issued Time',
    'releaseTime': 'Release Time',
    'releaseEmp': 'Release Employee',
    'releaseComment': 'Release Comment',
    'holdComment': 'Hold Comment',
    'comment': 'Comment',
    'commentDate': 'Run Card Comment',
    'commentEmp': 'Run Card Comment Employee',
    'futureHoldComment': 'Future Hold Comment',
    'holdEmp': 'Hold Employee',
    'holdDept': 'Hold Employee Dept',
    'produceRegion': 'Produce Region',
    'priority': 'Work Order Priority',
    'tmttRemaining': 'TMTT Remaining',
    'dieConsumption': 'Die Consumption Qty',
    'wipStatus': 'WIP Status',
    'dataUpdateDate': 'Data Update Date'
}


def get_lot_detail(lotid: str) -> Optional[Dict[str, Any]]:
    """Get detailed information for a specific lot.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        lotid: The LOTID to retrieve

    Returns:
        Dict with lot details or None if not found
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = cached_df[cached_df['LOTID'] == lotid]

            if df.empty:
                return None

            row = df.iloc[0]
            return _build_lot_detail_response(row)
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based lot detail failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_lot_detail_from_oracle(lotid)


def _get_lot_detail_from_oracle(lotid: str) -> Optional[Dict[str, Any]]:
    """Get lot detail directly from Oracle (fallback)."""
    try:
        sql = f"""
            SELECT
                LOTID,
                WORKORDER,
                QTY,
                QTY2,
                STATUS,
                HOLDREASONNAME,
                CURRENTHOLDCOUNT,
                OWNER,
                STARTDATE,
                UTS,
                PRODUCT,
                PRODUCTLINENAME,
                PACKAGE_LEF,
                PJ_FUNCTION,
                PJ_TYPE,
                BOP,
                FIRSTNAME,
                WAFERNAME,
                WAFERLOT,
                SPECNAME,
                SPECSEQUENCE,
                WORKCENTERNAME,
                WORKCENTERSEQUENCE,
                WORKCENTER_GROUP,
                WORKCENTER_SHORT,
                AGEBYDAYS,
                EQUIPMENTS,
                EQUIPMENTCOUNT,
                WORKFLOWNAME,
                DATECODE,
                LEADFRAMENAME,
                LEADFRAMEOPTION,
                COMNAME,
                LOCATIONNAME,
                EVENTNAME,
                OCCURRENCEDATE,
                RELEASETIME,
                RELEASEEMP,
                RELEASEREASON,
                COMMENT_HOLD,
                CONTAINERCOMMENTS,
                COMMENT_DATE,
                COMMENT_EMP,
                COMMENT_FUTURE,
                HOLDEMP,
                DEPTNAME,
                PJ_PRODUCEREGION,
                PRIORITYCODENAME,
                TMTT_R,
                WAFER_FACTOR,
                SYS_DATE
            FROM {WIP_VIEW}
            WHERE LOTID = :lotid
        """
        df = read_sql_df(sql, {'lotid': lotid})

        if df is None or df.empty:
            return None

        row = df.iloc[0]
        return _build_lot_detail_response(row)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Lot detail query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def _build_lot_detail_response(row) -> Dict[str, Any]:
    """Build lot detail response from DataFrame row."""
    # Helper to safely get value from row (handles NaN and missing columns)
    def safe_get(col, default=None):
        try:
            val = row.get(col)
            if pd.isna(val):
                return default
            return val
        except Exception:
            return default

    # Helper to safely get int value
    def safe_int(col, default=0):
        val = safe_get(col)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    # Helper to safely get float value
    def safe_float(col, default=0.0):
        val = safe_get(col)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # Helper to format date value
    def format_date(col):
        val = safe_get(col)
        if val is None:
            return None
        try:
            return str(val)
        except Exception:
            return None

    # Compute WIP status
    equipment_count = safe_int('EQUIPMENTCOUNT')
    hold_count = safe_int('CURRENTHOLDCOUNT')

    if equipment_count > 0:
        wip_status = 'RUN'
    elif hold_count > 0:
        wip_status = 'HOLD'
    else:
        wip_status = 'QUEUE'

    return {
        'lotId': _safe_value(safe_get('LOTID')),
        'workorder': _safe_value(safe_get('WORKORDER')),
        'qty': safe_int('QTY'),
        'qty2': safe_int('QTY2') if safe_get('QTY2') is not None else None,
        'status': _safe_value(safe_get('STATUS')),
        'holdReason': _safe_value(safe_get('HOLDREASONNAME')),
        'holdCount': hold_count,
        'owner': _safe_value(safe_get('OWNER')),
        'startDate': format_date('STARTDATE'),
        'uts': _safe_value(safe_get('UTS')),
        'product': _safe_value(safe_get('PRODUCT')),
        'productLine': _safe_value(safe_get('PRODUCTLINENAME')),
        'packageLef': _safe_value(safe_get('PACKAGE_LEF')),
        'pjFunction': _safe_value(safe_get('PJ_FUNCTION')),
        'pjType': _safe_value(safe_get('PJ_TYPE')),
        'bop': _safe_value(safe_get('BOP')),
        'waferLotId': _safe_value(safe_get('FIRSTNAME')),
        'waferPn': _safe_value(safe_get('WAFERNAME')),
        'waferLotPrefix': _safe_value(safe_get('WAFERLOT')),
        'spec': _safe_value(safe_get('SPECNAME')),
        'specSequence': safe_int('SPECSEQUENCE') if safe_get('SPECSEQUENCE') is not None else None,
        'workcenter': _safe_value(safe_get('WORKCENTERNAME')),
        'workcenterSequence': safe_int('WORKCENTERSEQUENCE') if safe_get('WORKCENTERSEQUENCE') is not None else None,
        'workcenterGroup': _safe_value(safe_get('WORKCENTER_GROUP')),
        'workcenterShort': _safe_value(safe_get('WORKCENTER_SHORT')),
        'ageByDays': round(safe_float('AGEBYDAYS'), 2),
        'equipment': _safe_value(safe_get('EQUIPMENTS')),
        'equipmentCount': equipment_count,
        'workflow': _safe_value(safe_get('WORKFLOWNAME')),
        'dateCode': _safe_value(safe_get('DATECODE')),
        'leadframeName': _safe_value(safe_get('LEADFRAMENAME')),
        'leadframeOption': _safe_value(safe_get('LEADFRAMEOPTION')),
        'compoundName': _safe_value(safe_get('COMNAME')),
        'location': _safe_value(safe_get('LOCATIONNAME')),
        'ncrId': _safe_value(safe_get('EVENTNAME')),
        'ncrDate': format_date('OCCURRENCEDATE'),
        'releaseTime': format_date('RELEASETIME'),
        'releaseEmp': _safe_value(safe_get('RELEASEEMP')),
        'releaseComment': _safe_value(safe_get('RELEASEREASON')),
        'holdComment': _safe_value(safe_get('COMMENT_HOLD')),
        'comment': _safe_value(safe_get('CONTAINERCOMMENTS')),
        'commentDate': _safe_value(safe_get('COMMENT_DATE')),
        'commentEmp': _safe_value(safe_get('COMMENT_EMP')),
        'futureHoldComment': _safe_value(safe_get('COMMENT_FUTURE')),
        'holdEmp': _safe_value(safe_get('HOLDEMP')),
        'holdDept': _safe_value(safe_get('DEPTNAME')),
        'produceRegion': _safe_value(safe_get('PJ_PRODUCEREGION')),
        'priority': _safe_value(safe_get('PRIORITYCODENAME')),
        'tmttRemaining': _safe_value(safe_get('TMTT_R')),
        'dieConsumption': safe_int('WAFER_FACTOR') if safe_get('WAFER_FACTOR') is not None else None,
        'wipStatus': wip_status,
        'dataUpdateDate': format_date('SYS_DATE'),
        'fieldLabels': LOT_DETAIL_FIELD_LABELS
    }
