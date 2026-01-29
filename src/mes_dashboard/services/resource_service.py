# -*- coding: utf-8 -*-
"""Resource (Equipment) query services for MES Dashboard.

Provides functions to query equipment status from DW_MES_RESOURCE and DW_MES_RESOURCESTATUS tables.
"""

import pandas as pd
from typing import Optional, Dict, List, Any

from mes_dashboard.core.database import get_db_connection, read_sql_df
from mes_dashboard.core.utils import get_days_back, build_equipment_filter_sql
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    DEFAULT_DAYS_BACK,
)


# ============================================================
# Resource Base Subquery
# ============================================================

def get_resource_latest_status_subquery(days_back: int = 30) -> str:
    """Returns subquery to get latest status per resource.

    Filter conditions:
    - (OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY') OR
      (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT')
    - Excludes specified locations and asset statuses

    Uses ROW_NUMBER() for performance.
    Only scans recent status changes (default 30 days).
    Includes JOBID for SDT/UDT drill-down.
    Includes PJ_LOTID from RESOURCE table.

    Args:
        days_back: Number of days to look back

    Returns:
        SQL subquery string for latest resource status.
    """
    # Build exclusion filters
    location_filter = ""
    if EXCLUDED_LOCATIONS:
        excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
        location_filter = f"AND (r.LOCATIONNAME IS NULL OR r.LOCATIONNAME NOT IN ('{excluded_locations}'))"

    asset_status_filter = ""
    if EXCLUDED_ASSET_STATUSES:
        excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
        asset_status_filter = f"AND (r.PJ_ASSETSSTATUS IS NULL OR r.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

    return f"""
          WITH latest_txn AS (
              SELECT MAX(COALESCE(TXNDATE, LASTSTATUSCHANGEDATE)) AS MAX_TXNDATE
              FROM DW_MES_RESOURCESTATUS
          )
          SELECT *
          FROM (
              SELECT
                r.RESOURCEID,
                r.RESOURCENAME,
                r.OBJECTCATEGORY,
                r.OBJECTTYPE,
                r.RESOURCEFAMILYNAME,
                r.WORKCENTERNAME,
                r.LOCATIONNAME,
                r.VENDORNAME,
                r.VENDORMODEL,
                r.PJ_DEPARTMENT,
                r.PJ_ASSETSSTATUS,
                r.PJ_ISPRODUCTION,
                r.PJ_ISKEY,
                r.PJ_ISMONITOR,
                r.PJ_LOTID,
                r.DESCRIPTION,
                  s.NEWSTATUSNAME,
                  s.NEWREASONNAME,
                  s.LASTSTATUSCHANGEDATE,
                  s.OLDSTATUSNAME,
                s.OLDREASONNAME,
                  s.AVAILABILITY,
                  s.JOBID,
                  s.TXNDATE,
                  ROW_NUMBER() OVER (
                      PARTITION BY r.RESOURCEID
                      ORDER BY s.LASTSTATUSCHANGEDATE DESC NULLS LAST,
                               COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) DESC
                  ) AS rn
              FROM DW_MES_RESOURCE r
              JOIN DW_MES_RESOURCESTATUS s ON r.RESOURCEID = s.HISTORYID
              CROSS JOIN latest_txn lt
              WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                  OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
                AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= lt.MAX_TXNDATE - {days_back}
                {location_filter}
                {asset_status_filter}
          )
          WHERE rn = 1
      """


# ============================================================
# Resource Summary Queries
# ============================================================

def query_resource_status_summary(days_back: int = 30) -> Optional[Dict]:
    """Query resource status summary statistics.

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
                COUNT(*) as TOTAL_COUNT,
                COUNT(DISTINCT WORKCENTERNAME) as WORKCENTER_COUNT,
                COUNT(DISTINCT RESOURCEFAMILYNAME) as FAMILY_COUNT,
                COUNT(DISTINCT PJ_DEPARTMENT) as DEPT_COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if not result:
            return None
        return {
            'total_count': result[0] or 0,
            'workcenter_count': result[1] or 0,
            'family_count': result[2] or 0,
            'dept_count': result[3] or 0
        }
    except Exception as exc:
        if connection:
            connection.close()
        print(f"Resource summary query failed: {exc}")
        return None


def query_resource_by_status(days_back: int = 30) -> Optional[pd.DataFrame]:
    """Query resource count grouped by status.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with status counts or None if query fails.
    """
    try:
        sql = f"""
            SELECT
                NEWSTATUSNAME,
                COUNT(*) as COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
            WHERE NEWSTATUSNAME IS NOT NULL
            GROUP BY NEWSTATUSNAME
            ORDER BY COUNT DESC
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"Resource by status query failed: {exc}")
        return None


def query_resource_by_workcenter(days_back: int = 30) -> Optional[pd.DataFrame]:
    """Query resource count grouped by workcenter and status.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with workcenter/status counts or None if query fails.
    """
    try:
        sql = f"""
            SELECT
                WORKCENTERNAME,
                NEWSTATUSNAME,
                COUNT(*) as COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
            WHERE WORKCENTERNAME IS NOT NULL
            GROUP BY WORKCENTERNAME, NEWSTATUSNAME
            ORDER BY WORKCENTERNAME, COUNT DESC
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"Resource by workcenter query failed: {exc}")
        return None


def query_resource_detail(
    filters: Optional[Dict] = None,
    limit: int = 500,
    offset: int = 0,
    days_back: int = 30
) -> Optional[pd.DataFrame]:
    """Query resource detail with optional filters.

    Args:
        filters: Optional filter values
        limit: Maximum rows to return
        offset: Offset for pagination
        days_back: Number of days to look back

    Returns:
        DataFrame with resource details or None if query fails.
    """
    try:
        base_sql = get_resource_latest_status_subquery(days_back)

        where_conditions = []
        if filters:
            if filters.get('workcenter'):
                where_conditions.append(f"WORKCENTERNAME = '{filters['workcenter']}'")
            if filters.get('status'):
                where_conditions.append(f"NEWSTATUSNAME = '{filters['status']}'")
            if filters.get('family'):
                where_conditions.append(f"RESOURCEFAMILYNAME = '{filters['family']}'")
            if filters.get('department'):
                where_conditions.append(f"PJ_DEPARTMENT = '{filters['department']}'")

            # Equipment flag filters
            if filters.get('isProduction') is not None:
                where_conditions.append(
                    f"NVL(PJ_ISPRODUCTION, 0) = {1 if filters['isProduction'] else 0}"
                )
            if filters.get('isKey') is not None:
                where_conditions.append(
                    f"NVL(PJ_ISKEY, 0) = {1 if filters['isKey'] else 0}"
                )
            if filters.get('isMonitor') is not None:
                where_conditions.append(
                    f"NVL(PJ_ISMONITOR, 0) = {1 if filters['isMonitor'] else 0}"
                )

        where_clause = " AND " + " AND ".join(where_conditions) if where_conditions else ""

        start_row = offset + 1
        end_row = offset + limit
        sql = f"""
            SELECT * FROM (
                SELECT
                    RESOURCENAME,
                    WORKCENTERNAME,
                    RESOURCEFAMILYNAME,
                    NEWSTATUSNAME,
                    NEWREASONNAME,
                    LASTSTATUSCHANGEDATE,
                    PJ_DEPARTMENT,
                    VENDORNAME,
                    VENDORMODEL,
                    PJ_ASSETSSTATUS,
                    AVAILABILITY,
                    PJ_ISPRODUCTION,
                    PJ_ISKEY,
                    PJ_ISMONITOR,
                    ROW_NUMBER() OVER (
                        ORDER BY LASTSTATUSCHANGEDATE DESC NULLS LAST
                    ) AS rn
                FROM ({base_sql}) rs
                WHERE 1=1 {where_clause}
            ) WHERE rn BETWEEN {start_row} AND {end_row}
        """
        df = read_sql_df(sql)

        # Convert datetime to string
        if 'LASTSTATUSCHANGEDATE' in df.columns:
            df['LASTSTATUSCHANGEDATE'] = df['LASTSTATUSCHANGEDATE'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else None
            )

        return df
    except Exception as exc:
        print(f"Resource detail query failed: {exc}")
        return None


def query_resource_workcenter_status_matrix(days_back: int = 30) -> Optional[pd.DataFrame]:
    """Query resource count matrix by workcenter and status category.

    Status values in database:
    - PRD: Productive
    - SBY: Standby
    - UDT: Unscheduled Down Time
    - SDT: Scheduled Down Time
    - EGT: Engineering Time
    - NST: Not Scheduled Time

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with workcenter/status matrix or None if query fails.
    """
    try:
        sql = f"""
            SELECT
                WORKCENTERNAME,
                CASE NEWSTATUSNAME
                    WHEN 'PRD' THEN 'PRD'
                    WHEN 'SBY' THEN 'SBY'
                    WHEN 'UDT' THEN 'UDT'
                    WHEN 'SDT' THEN 'SDT'
                    WHEN 'EGT' THEN 'EGT'
                    WHEN 'NST' THEN 'NST'
                    WHEN 'SCRAP' THEN 'SCRAP'
                    ELSE 'OTHER'
                END as STATUS_CATEGORY,
                NEWSTATUSNAME,
                COUNT(*) as COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
            WHERE WORKCENTERNAME IS NOT NULL
            GROUP BY WORKCENTERNAME,
                CASE NEWSTATUSNAME
                    WHEN 'PRD' THEN 'PRD'
                    WHEN 'SBY' THEN 'SBY'
                    WHEN 'UDT' THEN 'UDT'
                    WHEN 'SDT' THEN 'SDT'
                    WHEN 'EGT' THEN 'EGT'
                    WHEN 'NST' THEN 'NST'
                    WHEN 'SCRAP' THEN 'SCRAP'
                    ELSE 'OTHER'
                END,
                NEWSTATUSNAME
            ORDER BY WORKCENTERNAME, STATUS_CATEGORY
        """
        return read_sql_df(sql)
    except Exception as exc:
        print(f"Resource status matrix query failed: {exc}")
        return None


def query_resource_filter_options(days_back: int = 30) -> Optional[Dict]:
    """Get available filter options for resource queries.

    Uses resource_cache for static resource data (workcenters, families, departments, locations).
    Only queries Oracle for dynamic status data.

    Args:
        days_back: Number of days to look back

    Returns:
        Dict with filter options or None if query fails.
    """
    from mes_dashboard.services.resource_cache import (
        get_workcenters,
        get_resource_families,
        get_departments,
        get_locations,
        get_distinct_values,
    )

    try:
        # Get static filter options from resource cache
        workcenters = get_workcenters()
        families = get_resource_families()
        departments = get_departments()
        locations = get_locations()
        assets_statuses = get_distinct_values('PJ_ASSETSSTATUS')

        # Query only dynamic status data from Oracle
        # Note: Can't wrap CTE in subquery, so use inline approach
        sql_statuses = f"""
            WITH latest_txn AS (
                SELECT MAX(COALESCE(TXNDATE, LASTSTATUSCHANGEDATE)) AS MAX_TXNDATE
                FROM DW_MES_RESOURCESTATUS
            )
            SELECT DISTINCT s.NEWSTATUSNAME
            FROM DW_MES_RESOURCE r
            JOIN DW_MES_RESOURCESTATUS s ON r.RESOURCEID = s.HISTORYID
            CROSS JOIN latest_txn lt
            WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
              AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= lt.MAX_TXNDATE - {days_back}
              AND s.NEWSTATUSNAME IS NOT NULL
            ORDER BY s.NEWSTATUSNAME
        """
        status_df = read_sql_df(sql_statuses)
        statuses = status_df['NEWSTATUSNAME'].tolist() if status_df is not None else []

        return {
            'workcenters': workcenters,
            'statuses': statuses,
            'families': families,
            'departments': departments,
            'locations': locations,
            'assets_statuses': assets_statuses
        }
    except Exception as exc:
        print(f"Resource filter options query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None
