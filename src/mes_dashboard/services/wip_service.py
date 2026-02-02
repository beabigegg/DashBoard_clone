# -*- coding: utf-8 -*-
"""WIP (Work In Progress) query services for MES Dashboard.

Provides functions to query WIP data from DWH.DW_MES_LOT_V view.
This view provides real-time WIP information updated every 5 minutes.

Now uses Redis cache when available, with fallback to Oracle direct query.
"""

import logging
from typing import Optional, Dict, List, Any

import numpy as np
import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.cache import get_cached_wip_data, get_cached_sys_date

logger = logging.getLogger('mes_dashboard.wip_service')


def _safe_value(val):
    """Convert pandas NaN/NaT to None for JSON serialization."""
    if pd.isna(val):
        return None
    return val


def _escape_sql(value: str) -> str:
    """Escape single quotes in SQL string values."""
    if value is None:
        return None
    return value.replace("'", "''")


def _build_base_conditions(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> List[str]:
    """Build base WHERE conditions for WIP queries.

    Args:
        include_dummy: If False (default), exclude LOTID containing 'DUMMY'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)

    Returns:
        List of SQL condition strings
    """
    conditions = []

    # Exclude raw materials (NULL WORKORDER)
    conditions.append("WORKORDER IS NOT NULL")

    # DUMMY exclusion (default behavior)
    if not include_dummy:
        conditions.append("LOTID NOT LIKE '%DUMMY%'")

    # WORKORDER filter (fuzzy match)
    if workorder:
        conditions.append(f"WORKORDER LIKE '%{_escape_sql(workorder)}%'")

    # LOTID filter (fuzzy match)
    if lotid:
        conditions.append(f"LOTID LIKE '%{_escape_sql(lotid)}%'")

    return conditions


# ============================================================
# Hold Type Classification
# ============================================================
# Non-quality hold reasons (all other reasons are quality holds)
NON_QUALITY_HOLD_REASONS = {
    'IQC檢驗(久存品驗證)(QC)',
    '大中/安波幅50pcs樣品留樣(PD)',
    '工程驗證(PE)',
    '工程驗證(RD)',
    '指定機台生產',
    '特殊需求(X-Ray全檢)',
    '特殊需求管控',
    '第一次量產QC品質確認(QC)',
    '需綁尾數(PD)',
    '樣品需求留存打樣(樣品)',
    '盤點(收線)需求',
}


def is_quality_hold(reason: str) -> bool:
    """Check if a hold reason is quality-related.

    Args:
        reason: The HOLDREASONNAME value

    Returns:
        True if this is a quality hold, False if non-quality hold
    """
    if reason is None:
        return True  # Default to quality if reason is unknown
    return reason not in NON_QUALITY_HOLD_REASONS


def _build_hold_type_sql_list() -> str:
    """Build SQL IN clause list for non-quality hold reasons.

    Returns:
        Comma-separated string of escaped reason names for SQL IN clause
    """
    escaped = [f"'{_escape_sql(r)}'" for r in NON_QUALITY_HOLD_REASONS]
    return ', '.join(escaped)


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
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
        if package:
            conditions.append(f"PACKAGE_LEF = '{_escape_sql(package)}'")
        if pj_type:
            conditions.append(f"PJ_TYPE = '{_escape_sql(pj_type)}'")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        non_quality_list = _build_hold_type_sql_list()

        sql = f"""
            SELECT
                COUNT(*) as TOTAL_LOTS,
                SUM(QTY) as TOTAL_QTY_PCS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) > 0 THEN 1 ELSE 0 END) as RUN_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) > 0 THEN QTY ELSE 0 END) as RUN_QTY_PCS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0 THEN 1 ELSE 0 END) as HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0 THEN QTY ELSE 0 END) as HOLD_QTY_PCS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND (HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ({non_quality_list}))
                          THEN 1 ELSE 0 END) as QUALITY_HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND (HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ({non_quality_list}))
                          THEN QTY ELSE 0 END) as QUALITY_HOLD_QTY_PCS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND HOLDREASONNAME IN ({non_quality_list})
                          THEN 1 ELSE 0 END) as NON_QUALITY_HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND HOLDREASONNAME IN ({non_quality_list})
                          THEN QTY ELSE 0 END) as NON_QUALITY_HOLD_QTY_PCS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) = 0 THEN 1 ELSE 0 END) as QUEUE_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) = 0 THEN QTY ELSE 0 END) as QUEUE_QTY_PCS,
                MAX(SYS_DATE) as DATA_UPDATE_DATE
            FROM {WIP_VIEW}
            {where_clause}
        """
        df = read_sql_df(sql)

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
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
        conditions.append("WORKCENTER_GROUP IS NOT NULL")
        conditions.append("PACKAGE_LEF IS NOT NULL")
        if package:
            conditions.append(f"PACKAGE_LEF = '{_escape_sql(package)}'")
        if pj_type:
            conditions.append(f"PJ_TYPE = '{_escape_sql(pj_type)}'")

        # WIP status filter
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                conditions.append("EQUIPMENTCOUNT > 0")
            elif status_upper == 'HOLD':
                conditions.append("EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT > 0")
                # Hold type sub-filter
                if hold_type:
                    non_quality_list = _build_hold_type_sql_list()
                    if hold_type == 'quality':
                        conditions.append(
                            f"(HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ({non_quality_list}))"
                        )
                    elif hold_type == 'non-quality':
                        conditions.append(f"HOLDREASONNAME IN ({non_quality_list})")
            elif status_upper == 'QUEUE':
                conditions.append("EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT = 0")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT
                WORKCENTER_GROUP,
                WORKCENTERSEQUENCE_GROUP,
                PACKAGE_LEF,
                SUM(QTY) as QTY
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, PACKAGE_LEF
            ORDER BY WORKCENTERSEQUENCE_GROUP, PACKAGE_LEF
        """
        df = read_sql_df(sql)

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
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
        conditions.append("STATUS = 'HOLD'")
        conditions.append("HOLDREASONNAME IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

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
        df = read_sql_df(sql)

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
        # Build WHERE conditions
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
        conditions.append(f"WORKCENTER_GROUP = '{_escape_sql(workcenter)}'")

        if package:
            conditions.append(f"PACKAGE_LEF = '{_escape_sql(package)}'")

        # WIP status filter (RUN/QUEUE/HOLD based on EQUIPMENTCOUNT and CURRENTHOLDCOUNT)
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                conditions.append("COALESCE(EQUIPMENTCOUNT, 0) > 0")
            elif status_upper == 'HOLD':
                conditions.append("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) > 0")
                # Hold type sub-filter
                if hold_type:
                    non_quality_list = _build_hold_type_sql_list()
                    if hold_type == 'quality':
                        conditions.append(
                            f"(HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ({non_quality_list}))"
                        )
                    elif hold_type == 'non-quality':
                        conditions.append(f"HOLDREASONNAME IN ({non_quality_list})")
            elif status_upper == 'QUEUE':
                conditions.append("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) = 0")

        where_clause = f"WHERE {' AND '.join(conditions)}"

        # Get summary with RUN/QUEUE/HOLD classification (IT standard)
        # Note: summary always uses base_conditions (without hold_type filter) to show full breakdown
        summary_conditions = _build_base_conditions(include_dummy, workorder, lotid)
        summary_conditions.append(f"WORKCENTER_GROUP = '{_escape_sql(workcenter)}'")
        if package:
            summary_conditions.append(f"PACKAGE_LEF = '{_escape_sql(package)}'")
        summary_where = f"WHERE {' AND '.join(summary_conditions)}"
        non_quality_list = _build_hold_type_sql_list()

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

        summary_df = read_sql_df(summary_sql)

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
        # When a status filter is applied, use the corresponding count for pagination
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                filtered_count = run_lots
            elif status_upper == 'QUEUE':
                filtered_count = queue_lots
            elif status_upper == 'HOLD':
                # Further filter by hold_type if specified
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

        specs_df = read_sql_df(specs_sql)
        specs = specs_df['SPECNAME'].tolist() if specs_df is not None and not specs_df.empty else []

        # Get paginated lot details with WIP Status (IT standard)
        offset = (page - 1) * page_size
        lots_sql = f"""
            SELECT * FROM (
                SELECT
                    LOTID,
                    EQUIPMENTS,
                    STATUS,
                    HOLDREASONNAME,
                    QTY,
                    PACKAGE_LEF,
                    SPECNAME,
                    CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) > 0 THEN 'RUN'
                         WHEN COALESCE(CURRENTHOLDCOUNT, 0) > 0 THEN 'HOLD'
                         ELSE 'QUEUE' END AS WIP_STATUS,
                    ROW_NUMBER() OVER (ORDER BY LOTID) as RN
                FROM {WIP_VIEW}
                {where_clause}
            )
            WHERE RN > {offset} AND RN <= {offset + page_size}
            ORDER BY RN
        """

        lots_df = read_sql_df(lots_sql)

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
    except Exception as exc:
        print(f"WIP detail query failed: {exc}")
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
        except Exception as exc:
            logger.warning(f"Cache-based workcenters calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_workcenters_from_oracle(include_dummy)


def _get_workcenters_from_oracle(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get workcenters directly from Oracle (fallback)."""
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append("WORKCENTER_GROUP IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

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
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['WORKCENTER_GROUP'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
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
        except Exception as exc:
            logger.warning(f"Cache-based packages calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_packages_from_oracle(include_dummy)


def _get_packages_from_oracle(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get packages directly from Oracle (fallback)."""
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append("PACKAGE_LEF IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT
                PACKAGE_LEF,
                COUNT(*) as LOT_COUNT
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY PACKAGE_LEF
            ORDER BY COUNT(*) DESC
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['PACKAGE_LEF'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
    except Exception as exc:
        logger.error(f"Packages query failed: {exc}")
        return None


# ============================================================
# Search API Functions
# ============================================================

def search_workorders(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search for WORKORDER values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of matching WORKORDER values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)
            df = df[df['WORKORDER'].notna()]

            # Filter by search query (case-insensitive)
            df = df[df['WORKORDER'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct, sorted, limited results
            result = df['WORKORDER'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except Exception as exc:
            logger.warning(f"Cache-based workorder search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_workorders_from_oracle(q, limit, include_dummy)


def _search_workorders_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search workorders directly from Oracle (fallback)."""
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append(f"WORKORDER LIKE '%{_escape_sql(q)}%'")
        conditions.append("WORKORDER IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT DISTINCT WORKORDER
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY WORKORDER
            FETCH FIRST {limit} ROWS ONLY
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        return df['WORKORDER'].tolist()
    except Exception as exc:
        logger.error(f"Search workorders failed: {exc}")
        return None


def search_lot_ids(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search for LOTID values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of matching LOTID values
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)

            # Filter by search query (case-insensitive)
            df = df[df['LOTID'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get sorted, limited results
            result = df['LOTID'].sort_values().head(limit).tolist()
            return result
        except Exception as exc:
            logger.warning(f"Cache-based lot ID search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_lot_ids_from_oracle(q, limit, include_dummy)


def _search_lot_ids_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search lot IDs directly from Oracle (fallback)."""
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append(f"LOTID LIKE '%{_escape_sql(q)}%'")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT LOTID
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY LOTID
            FETCH FIRST {limit} ROWS ONLY
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        return df['LOTID'].tolist()
    except Exception as exc:
        logger.error(f"Search lot IDs failed: {exc}")
        return None


def search_packages(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search for PACKAGE_LEF values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of matching PACKAGE_LEF values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)

            # Check if PACKAGE_LEF column exists
            if 'PACKAGE_LEF' not in df.columns:
                logger.warning("PACKAGE_LEF column not found in cache")
                return _search_packages_from_oracle(q, limit, include_dummy)

            df = df[df['PACKAGE_LEF'].notna()]

            # Filter by search query (case-insensitive)
            df = df[df['PACKAGE_LEF'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct values sorted
            result = df['PACKAGE_LEF'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except Exception as exc:
            logger.warning(f"Cache-based package search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_packages_from_oracle(q, limit, include_dummy)


def _search_packages_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search packages directly from Oracle (fallback)."""
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append(f"PACKAGE_LEF LIKE '%{_escape_sql(q)}%'")
        conditions.append("PACKAGE_LEF IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT DISTINCT PACKAGE_LEF
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY PACKAGE_LEF
            FETCH FIRST {limit} ROWS ONLY
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        return df['PACKAGE_LEF'].tolist()
    except Exception as exc:
        logger.error(f"Search packages failed: {exc}")
        return None


def search_types(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search for PJ_TYPE values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of matching PJ_TYPE values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _filter_base_conditions(cached_df, include_dummy)

            # Check if PJ_TYPE column exists
            if 'PJ_TYPE' not in df.columns:
                logger.warning("PJ_TYPE column not found in cache")
                return _search_types_from_oracle(q, limit, include_dummy)

            df = df[df['PJ_TYPE'].notna()]

            # Filter by search query (case-insensitive)
            df = df[df['PJ_TYPE'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct values sorted
            result = df['PJ_TYPE'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except Exception as exc:
            logger.warning(f"Cache-based type search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_types_from_oracle(q, limit, include_dummy)


def _search_types_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search types directly from Oracle (fallback)."""
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append(f"PJ_TYPE LIKE '%{_escape_sql(q)}%'")
        conditions.append("PJ_TYPE IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT DISTINCT PJ_TYPE
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY PJ_TYPE
            FETCH FIRST {limit} ROWS ONLY
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        return df['PJ_TYPE'].tolist()
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
        conditions = _build_base_conditions(include_dummy)
        conditions.append("STATUS = 'HOLD'")
        conditions.append("CURRENTHOLDCOUNT > 0")
        conditions.append(f"HOLDREASONNAME = '{_escape_sql(reason)}'")
        where_clause = f"WHERE {' AND '.join(conditions)}"

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
        df = read_sql_df(sql)

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
        conditions = _build_base_conditions(include_dummy)
        conditions.append("STATUS = 'HOLD'")
        conditions.append("CURRENTHOLDCOUNT > 0")
        conditions.append(f"HOLDREASONNAME = '{_escape_sql(reason)}'")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        # Get total for percentage calculation
        total_sql = f"""
            SELECT COUNT(*) AS TOTAL_LOTS, SUM(QTY) AS TOTAL_QTY
            FROM {WIP_VIEW}
            {where_clause}
        """
        total_df = read_sql_df(total_sql)
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
        wc_df = read_sql_df(wc_sql)
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
        pkg_df = read_sql_df(pkg_sql)
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
        age_df = read_sql_df(age_sql)

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
        conditions = _build_base_conditions(include_dummy)
        conditions.append("STATUS = 'HOLD'")
        conditions.append("CURRENTHOLDCOUNT > 0")
        conditions.append(f"HOLDREASONNAME = '{_escape_sql(reason)}'")

        # Optional filters
        if workcenter:
            conditions.append(f"WORKCENTER_GROUP = '{_escape_sql(workcenter)}'")
        if package:
            conditions.append(f"PACKAGE_LEF = '{_escape_sql(package)}'")
        if age_range:
            if age_range == '0-1':
                conditions.append("AGEBYDAYS >= 0 AND AGEBYDAYS < 1")
            elif age_range == '1-3':
                conditions.append("AGEBYDAYS >= 1 AND AGEBYDAYS < 3")
            elif age_range == '3-7':
                conditions.append("AGEBYDAYS >= 3 AND AGEBYDAYS < 7")
            elif age_range == '7+':
                conditions.append("AGEBYDAYS >= 7")

        where_clause = f"WHERE {' AND '.join(conditions)}"

        # Get total count
        count_sql = f"""
            SELECT COUNT(*) AS TOTAL
            FROM {WIP_VIEW}
            {where_clause}
        """
        count_df = read_sql_df(count_sql)
        total = int(count_df.iloc[0]['TOTAL'] or 0) if count_df is not None else 0

        # Get paginated lots
        offset = (page - 1) * page_size
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
            WHERE RN > {offset} AND RN <= {offset + page_size}
            ORDER BY RN
        """
        lots_df = read_sql_df(lots_sql)

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
    except Exception as exc:
        logger.error(f"Hold detail lots query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None
