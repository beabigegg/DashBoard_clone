# -*- coding: utf-8 -*-
"""WIP (Work In Progress) query services for MES Dashboard.

Provides functions to query WIP data from DW_MES_WIP table.
"""

import pandas as pd
from typing import Optional, Dict, List, Any

from mes_dashboard.core.database import get_db_connection, read_sql_df
from mes_dashboard.config.workcenter_groups import get_workcenter_group
from mes_dashboard.config.constants import DEFAULT_WIP_DAYS_BACK, WIP_EXCLUDED_STATUS


# ============================================================
# WIP Base Subquery
# ============================================================

def get_current_wip_subquery(days_back: int = DEFAULT_WIP_DAYS_BACK) -> str:
    """Returns subquery to get latest record per CONTAINER (current WIP snapshot).

    Uses ROW_NUMBER() analytic function for better performance.
    Only scans recent data (default 90 days) to reduce scan size.
    Filters out completed (8) and scrapped (128) status.
    Excludes DUMMY orders (MFGORDERNAME = 'DUMMY').

    Logic explanation:
    - PARTITION BY CONTAINERNAME: Groups records by each LOT
    - ORDER BY TXNDATE DESC: Orders by transaction time (newest first)
    - rn = 1: Takes only the latest record for each LOT
    - This gives us the current/latest status of each LOT

    Args:
        days_back: Number of days to look back (default 90)

    Returns:
        SQL subquery string for current WIP snapshot.
    """
    excluded_status = ', '.join(str(s) for s in WIP_EXCLUDED_STATUS)
    return f"""
        SELECT *
        FROM (
            SELECT w.*,
                   ROW_NUMBER() OVER (PARTITION BY w.CONTAINERNAME ORDER BY w.TXNDATE DESC) as rn
            FROM DW_MES_WIP w
            WHERE w.TXNDATE >= SYSDATE - {days_back}
              AND w.STATUS NOT IN ({excluded_status})
              AND (w.MFGORDERNAME IS NULL OR w.MFGORDERNAME <> 'DUMMY')
        )
        WHERE rn = 1
    """


# ============================================================
# WIP Summary Queries
# ============================================================

def query_wip_summary(days_back: int = DEFAULT_WIP_DAYS_BACK) -> Optional[Dict]:
    """Query current WIP summary statistics.

    Args:
        days_back: Number of days to look back

    Returns:
        Dict with summary stats or None if query fails.
    """
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT
                COUNT(CONTAINERNAME) as TOTAL_LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2,
                COUNT(DISTINCT SPECNAME) as SPEC_COUNT,
                COUNT(DISTINCT WORKCENTERNAME) as WORKCENTER_COUNT,
                COUNT(DISTINCT PRODUCTLINENAME_LEF) as PRODUCT_LINE_COUNT
            FROM ({get_current_wip_subquery(days_back)}) wip
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if not result:
            return None
        return {
            'total_lot_count': result[0] or 0,
            'total_qty': result[1] or 0,
            'total_qty2': result[2] or 0,
            'spec_count': result[3] or 0,
            'workcenter_count': result[4] or 0,
            'product_line_count': result[5] or 0
        }
    except Exception as exc:
        if connection:
            connection.close()
        print(f"WIP summary query failed: {exc}")
        return None


def query_wip_by_spec_workcenter(days_back: int = DEFAULT_WIP_DAYS_BACK) -> Optional[pd.DataFrame]:
    """Query current WIP grouped by spec and workcenter.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with WIP by spec/workcenter or None if query fails.
    """
    try:
        sql = f"""
            SELECT
                SPECNAME,
                WORKCENTERNAME,
                COUNT(CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM ({get_current_wip_subquery(days_back)}) wip
            WHERE SPECNAME IS NOT NULL
              AND WORKCENTERNAME IS NOT NULL
            GROUP BY SPECNAME, WORKCENTERNAME
            ORDER BY TOTAL_QTY DESC
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"WIP by spec/workcenter query failed: {exc}")
        return None


def query_wip_by_product_line(days_back: int = DEFAULT_WIP_DAYS_BACK) -> Optional[pd.DataFrame]:
    """Query current WIP grouped by product line.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with WIP by product line or None if query fails.
    """
    try:
        sql = f"""
            SELECT
                PRODUCTLINENAME_LEF,
                SPECNAME,
                WORKCENTERNAME,
                COUNT(CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM ({get_current_wip_subquery(days_back)}) wip
            WHERE PRODUCTLINENAME_LEF IS NOT NULL
            GROUP BY PRODUCTLINENAME_LEF, SPECNAME, WORKCENTERNAME
            ORDER BY TOTAL_QTY DESC
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"WIP by product line query failed: {exc}")
        return None


def query_wip_by_status(days_back: int = DEFAULT_WIP_DAYS_BACK) -> Optional[pd.DataFrame]:
    """Query current WIP grouped by status.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with WIP by status or None if query fails.
    """
    try:
        sql = f"""
            SELECT
                STATUS,
                COUNT(CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY
            FROM ({get_current_wip_subquery(days_back)}) wip
            GROUP BY STATUS
            ORDER BY LOT_COUNT DESC
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"WIP by status query failed: {exc}")
        return None


def query_wip_by_mfgorder(days_back: int = DEFAULT_WIP_DAYS_BACK, top_n: int = 100) -> Optional[pd.DataFrame]:
    """Query current WIP grouped by manufacturing order (top N).

    Args:
        days_back: Number of days to look back
        top_n: Number of top orders to return

    Returns:
        DataFrame with WIP by MFG order or None if query fails.
    """
    try:
        sql = f"""
            SELECT * FROM (
                SELECT
                    MFGORDERNAME,
                    COUNT(CONTAINERNAME) as LOT_COUNT,
                    SUM(QTY) as TOTAL_QTY,
                    SUM(QTY2) as TOTAL_QTY2
                FROM ({get_current_wip_subquery(days_back)}) wip
                WHERE MFGORDERNAME IS NOT NULL
                GROUP BY MFGORDERNAME
                ORDER BY TOTAL_QTY DESC
            ) WHERE ROWNUM <= {top_n}
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"WIP by MFG order query failed: {exc}")
        return None


# ============================================================
# WIP Distribution Table Functions
# ============================================================

def query_wip_distribution_filter_options(days_back: int = DEFAULT_WIP_DAYS_BACK) -> Optional[Dict]:
    """Get filter options for WIP distribution table.

    Returns available values for packages, types, areas, and lot statuses.

    Args:
        days_back: Number of days to look back

    Returns:
        Dict with filter options or None if query fails.
    """
    try:
        base_sql = get_current_wip_subquery(days_back)
        sql = f"""
            SELECT
                PRODUCTLINENAME_LEF,
                PJ_TYPE,
                PJ_PRODUCEREGION,
                HOLDREASONNAME
            FROM ({base_sql}) wip
        """
        df = read_sql_df(sql)

        # Extract unique values and sort
        packages = sorted([x for x in df['PRODUCTLINENAME_LEF'].dropna().unique().tolist() if x])
        types = sorted([x for x in df['PJ_TYPE'].dropna().unique().tolist() if x])
        areas = sorted([x for x in df['PJ_PRODUCEREGION'].dropna().unique().tolist() if x])

        # Lot status: based on HOLDREASONNAME - has value=Hold, no value=Active
        lot_statuses = ['Active', 'Hold']

        return {
            'packages': packages,
            'types': types,
            'areas': areas,
            'lot_statuses': lot_statuses
        }
    except Exception as exc:
        print(f"WIP filter options query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def _build_wip_distribution_where_clause(filters: Optional[Dict]) -> str:
    """Build WHERE clause for WIP distribution queries.

    Args:
        filters: Dict with filter values

    Returns:
        SQL WHERE clause conditions string.
    """
    where_conditions = []

    if filters:
        if filters.get('packages') and len(filters['packages']) > 0:
            pkg_list = "', '".join(filters['packages'])
            where_conditions.append(f"PRODUCTLINENAME_LEF IN ('{pkg_list}')")

        if filters.get('types') and len(filters['types']) > 0:
            type_list = "', '".join(filters['types'])
            where_conditions.append(f"PJ_TYPE IN ('{type_list}')")

        if filters.get('areas') and len(filters['areas']) > 0:
            area_list = "', '".join(filters['areas'])
            where_conditions.append(f"PJ_PRODUCEREGION IN ('{area_list}')")

        # Lot status filter: Active = HOLDREASONNAME IS NULL, Hold = IS NOT NULL
        if filters.get('lot_statuses') and len(filters['lot_statuses']) > 0:
            status_conds = []
            if 'Active' in filters['lot_statuses']:
                status_conds.append("HOLDREASONNAME IS NULL")
            if 'Hold' in filters['lot_statuses']:
                status_conds.append("HOLDREASONNAME IS NOT NULL")
            if status_conds:
                where_conditions.append(f"({' OR '.join(status_conds)})")

        if filters.get('search'):
            search_term = filters['search'].replace("'", "''")
            where_conditions.append(
                f"(UPPER(MFGORDERNAME) LIKE UPPER('%{search_term}%') "
                f"OR UPPER(CONTAINERNAME) LIKE UPPER('%{search_term}%'))"
            )

    return " AND ".join(where_conditions) if where_conditions else "1=1"


def query_wip_distribution_pivot_columns(
    filters: Optional[Dict] = None,
    days_back: int = DEFAULT_WIP_DAYS_BACK
) -> Optional[List[Dict]]:
    """Get pivot columns for WIP distribution table.

    Returns Workcenter|Spec combinations that have data.

    Args:
        filters: Optional filter values
        days_back: Number of days to look back

    Returns:
        List of pivot column dicts or None if query fails.
    """
    try:
        base_sql = get_current_wip_subquery(days_back)
        where_clause = _build_wip_distribution_where_clause(filters)

        sql = f"""
            SELECT
                WORKCENTERNAME,
                SPECNAME as WC_SPEC,
                COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT
            FROM ({base_sql}) wip
            WHERE WORKCENTERNAME IS NOT NULL
              AND {where_clause}
            GROUP BY WORKCENTERNAME, SPECNAME
            ORDER BY LOT_COUNT DESC
        """
        df = read_sql_df(sql)

        # Convert to pivot column list with WORKCENTER_GROUPS mapping
        pivot_columns = []
        for _, row in df.iterrows():
            wc = row['WORKCENTERNAME'] or ''
            spec = row['WC_SPEC'] or ''
            group_name, order = get_workcenter_group(wc)
            display_wc = group_name if group_name else wc

            pivot_columns.append({
                'key': f"{wc}|{spec}",
                'workcenter': wc,
                'workcenter_group': display_wc,
                'order': order,
                'spec': spec,
                'count': int(row['LOT_COUNT'] or 0)
            })

        return pivot_columns
    except Exception as exc:
        print(f"WIP pivot columns query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def query_wip_distribution(
    filters: Optional[Dict] = None,
    limit: int = 500,
    offset: int = 0,
    days_back: int = DEFAULT_WIP_DAYS_BACK
) -> Optional[Dict]:
    """Query WIP distribution table main data.

    Returns lot details with their Workcenter|Spec positions.

    Args:
        filters: Optional filter values
        limit: Maximum rows to return
        offset: Offset for pagination
        days_back: Number of days to look back

    Returns:
        Dict with 'rows', 'total_count', 'offset', 'limit' or None if fails.
    """
    try:
        base_sql = get_current_wip_subquery(days_back)
        where_clause = _build_wip_distribution_where_clause(filters)

        # Get total count first
        count_sql = f"""
            SELECT COUNT(DISTINCT CONTAINERNAME) as TOTAL_COUNT
            FROM ({base_sql}) wip
            WHERE {where_clause}
        """
        count_df = read_sql_df(count_sql)
        total_count = int(count_df['TOTAL_COUNT'].iloc[0]) if len(count_df) > 0 else 0

        # Paginated main data query
        start_row = offset + 1
        end_row = offset + limit
        sql = f"""
            SELECT * FROM (
                SELECT
                    MFGORDERNAME,
                    CONTAINERNAME,
                    SPECNAME,
                    PRODUCTLINENAME_LEF,
                    WAFERLOT,
                    PJ_TYPE,
                    PJ_PRODUCEREGION,
                    EQUIPMENTS,
                    WORKCENTERNAME,
                    STATUS,
                    HOLDREASONNAME,
                    QTY,
                    QTY2,
                    TXNDATE,
                    ROW_NUMBER() OVER (ORDER BY TXNDATE DESC, MFGORDERNAME, CONTAINERNAME) as rn
                FROM ({base_sql}) wip
                WHERE {where_clause}
            ) WHERE rn BETWEEN {start_row} AND {end_row}
        """
        df = read_sql_df(sql)

        # Convert to response format
        rows = []
        for _, row in df.iterrows():
            wc = row['WORKCENTERNAME'] or ''
            spec = row['SPECNAME'] or ''
            pivot_key = f"{wc}|{spec}"

            # Lot status: HOLDREASONNAME has value = Hold, no value = Active
            hold_reason = row['HOLDREASONNAME']
            lot_status = 'Hold' if (pd.notna(hold_reason) and hold_reason) else 'Active'

            rows.append({
                'MFGORDERNAME': row['MFGORDERNAME'],
                'CONTAINERNAME': row['CONTAINERNAME'],
                'SPECNAME': row['SPECNAME'],
                'PRODUCTLINENAME_LEF': row['PRODUCTLINENAME_LEF'],
                'WAFERLOT': row['WAFERLOT'],
                'PJ_TYPE': row['PJ_TYPE'],
                'PJ_PRODUCEREGION': row['PJ_PRODUCEREGION'],
                'EQUIPMENTS': row['EQUIPMENTS'],
                'WORKCENTERNAME': row['WORKCENTERNAME'],
                'LOT_STATUS': lot_status,
                'HOLDREASONNAME': hold_reason if pd.notna(hold_reason) else None,
                'QTY': int(row['QTY']) if pd.notna(row['QTY']) else 0,
                'QTY2': int(row['QTY2']) if pd.notna(row['QTY2']) else 0,
                'pivot_key': pivot_key
            })

        return {
            'rows': rows,
            'total_count': total_count,
            'offset': offset,
            'limit': limit
        }
    except Exception as exc:
        print(f"WIP distribution query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None
