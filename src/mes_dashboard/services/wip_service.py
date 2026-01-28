# -*- coding: utf-8 -*-
"""WIP (Work In Progress) query services for MES Dashboard.

Provides functions to query WIP data from DWH.DW_PJ_LOT_V view.
This view provides real-time WIP information updated every 5 minutes.
"""

from typing import Optional, Dict, List, Any

import pandas as pd

from mes_dashboard.core.database import read_sql_df


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
# The view DWH.DW_PJ_LOT_V must be accessed with schema prefix
WIP_VIEW = "DWH.DW_PJ_LOT_V"


# ============================================================
# Overview API Functions
# ============================================================

def get_wip_summary(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get WIP KPI summary for overview dashboard.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)

    Returns:
        Dict with summary stats (camelCase):
        - totalLots: Total number of lots
        - totalQtyPcs: Total quantity
        - byWipStatus: Grouped counts for RUN/QUEUE/HOLD
        - dataUpdateDate: Data timestamp
    """
    try:
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
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
        print(f"WIP summary query failed: {exc}")
        return None


def get_wip_matrix(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get workcenter x product line matrix for overview dashboard.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'

    Returns:
        Dict with matrix data:
        - workcenters: List of workcenter groups (sorted by WORKCENTERSEQUENCE_GROUP)
        - packages: List of product lines (sorted by total QTY desc)
        - matrix: Dict of {workcenter: {package: qty}}
        - workcenter_totals: Dict of {workcenter: total_qty}
        - package_totals: Dict of {package: total_qty}
        - grand_total: Overall total
    """
    try:
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
        conditions.append("WORKCENTER_GROUP IS NOT NULL")
        conditions.append("PRODUCTLINENAME IS NOT NULL")

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
                PRODUCTLINENAME,
                SUM(QTY) as QTY
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, PRODUCTLINENAME
            ORDER BY WORKCENTERSEQUENCE_GROUP, PRODUCTLINENAME
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

        # Build matrix
        matrix = {}
        workcenter_totals = {}
        package_totals = {}

        # Get unique workcenters sorted by sequence
        wc_order = df.drop_duplicates('WORKCENTER_GROUP')[['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP']]
        wc_order = wc_order.sort_values('WORKCENTERSEQUENCE_GROUP')
        workcenters = wc_order['WORKCENTER_GROUP'].tolist()

        # Build matrix and totals
        for _, row in df.iterrows():
            wc = row['WORKCENTER_GROUP']
            pkg = row['PRODUCTLINENAME']
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
    except Exception as exc:
        print(f"WIP matrix query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_wip_hold_summary(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get hold summary grouped by hold reason.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)

    Returns:
        Dict with hold items sorted by lots desc:
        - items: List of {reason, lots, qty}
    """
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
        print(f"WIP hold summary query failed: {exc}")
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

    Args:
        workcenter: WORKCENTER_GROUP name
        package: Optional PRODUCTLINENAME filter
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
    try:
        # Build WHERE conditions
        conditions = _build_base_conditions(include_dummy, workorder, lotid)
        conditions.append(f"WORKCENTER_GROUP = '{_escape_sql(workcenter)}'")

        if package:
            conditions.append(f"PRODUCTLINENAME = '{_escape_sql(package)}'")

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
            summary_conditions.append(f"PRODUCTLINENAME = '{_escape_sql(package)}'")
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
        total_count = int(summary_row['TOTAL_LOTS'] or 0)
        sys_date = str(summary_row['SYS_DATE']) if summary_row['SYS_DATE'] else None

        summary = {
            'totalLots': total_count,
            'runLots': int(summary_row['RUN_LOTS'] or 0),
            'queueLots': int(summary_row['QUEUE_LOTS'] or 0),
            'holdLots': int(summary_row['HOLD_LOTS'] or 0),
            'qualityHoldLots': int(summary_row['QUALITY_HOLD_LOTS'] or 0),
            'nonQualityHoldLots': int(summary_row['NON_QUALITY_HOLD_LOTS'] or 0)
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
                    PRODUCTLINENAME,
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
                    'package': _safe_value(row['PRODUCTLINENAME']),
                    'spec': _safe_value(row['SPECNAME'])
                })

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        return {
            'workcenter': workcenter,
            'summary': summary,
            'specs': specs,
            'lots': lots,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
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

    Args:
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of {name, lot_count} sorted by WORKCENTERSEQUENCE_GROUP
    """
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
        print(f"Workcenters query failed: {exc}")
        return None


def get_packages(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get list of packages (product lines) with lot counts.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of {name, lot_count} sorted by lot_count desc
    """
    try:
        conditions = _build_base_conditions(include_dummy)
        conditions.append("PRODUCTLINENAME IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        sql = f"""
            SELECT
                PRODUCTLINENAME,
                COUNT(*) as LOT_COUNT
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY PRODUCTLINENAME
            ORDER BY COUNT(*) DESC
        """
        df = read_sql_df(sql)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['PRODUCTLINENAME'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
    except Exception as exc:
        print(f"Packages query failed: {exc}")
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

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of matching WORKORDER values (distinct)
    """
    try:
        # Validate input
        if not q or len(q) < 2:
            return []

        limit = min(limit, 50)  # Cap at 50

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
        print(f"Search workorders failed: {exc}")
        return None


def search_lot_ids(
    q: str,
    limit: int = 20,
    include_dummy: bool = False
) -> Optional[List[str]]:
    """Search for LOTID values matching the query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of matching LOTID values
    """
    try:
        # Validate input
        if not q or len(q) < 2:
            return []

        limit = min(limit, 50)  # Cap at 50

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
        print(f"Search lot IDs failed: {exc}")
        return None
