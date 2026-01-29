# -*- coding: utf-8 -*-
"""Dashboard and KPI query services for MES Dashboard.

Provides functions to query dashboard KPIs, workcenter cards,
resource details with job info, OU trends, and utilization heatmap.
"""

import pandas as pd
from typing import Optional, Dict, List, Any, Tuple

from mes_dashboard.core.database import get_db_connection, read_sql_df
from mes_dashboard.core.utils import get_days_back, build_equipment_filter_sql
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    DEFAULT_DAYS_BACK,
)
from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS, get_workcenter_group
from mes_dashboard.services.resource_service import get_resource_latest_status_subquery


# ============================================================
# Dashboard KPI Queries
# ============================================================

def query_dashboard_kpi(filters: Optional[Dict] = None) -> Optional[Dict]:
    """Query overall KPI for dashboard header.

    Status categories:
    - RUN: PRD (Production)
    - DOWN: UDT + SDT (Down Time)
    - IDLE: SBY + NST (Idle)
    - ENG: EGT (Engineering Time)

    OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100

    Args:
        filters: Optional filter values

    Returns:
        Dict with KPI data or None if query fails.
    """
    connection = get_db_connection()
    if not connection:
        return None

    try:
        days_back = get_days_back(filters)
        base_sql = get_resource_latest_status_subquery(days_back)

        # Build filter conditions
        where_conditions = []
        if filters:
            # Equipment flag filters
            where_conditions.extend(build_equipment_filter_sql(filters))

            # Multi-select location filter
            if filters.get('locations') and len(filters['locations']) > 0:
                loc_list = "', '".join(filters['locations'])
                where_conditions.append(f"LOCATIONNAME IN ('{loc_list}')")

            # Multi-select asset status filter
            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                status_list = "', '".join(filters['assetsStatuses'])
                where_conditions.append(f"PJ_ASSETSSTATUS IN ('{status_list}')")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        sql = f"""
            SELECT
                COUNT(*) as TOTAL,
                SUM(CASE WHEN NEWSTATUSNAME = 'PRD' THEN 1 ELSE 0 END) as PRD_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'SBY' THEN 1 ELSE 0 END) as SBY_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'UDT' THEN 1 ELSE 0 END) as UDT_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'SDT' THEN 1 ELSE 0 END) as SDT_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'EGT' THEN 1 ELSE 0 END) as EGT_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'NST' THEN 1 ELSE 0 END) as NST_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME NOT IN ('PRD','SBY','UDT','SDT','EGT','NST') THEN 1 ELSE 0 END) as OTHER_COUNT
            FROM ({base_sql}) rs
            WHERE {where_clause}
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        cursor.close()
        connection.close()

        if not row:
            return None

        total = row[0] or 0
        prd = row[1] or 0
        sby = row[2] or 0
        udt = row[3] or 0
        sdt = row[4] or 0
        egt = row[5] or 0
        nst = row[6] or 0
        other = row[7] or 0

        # Status categories
        run_count = prd                    # RUN = PRD
        down_count = udt + sdt             # DOWN = UDT + SDT
        idle_count = sby + nst             # IDLE = SBY + NST
        eng_count = egt                    # ENG = EGT

        # OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100
        # Denominator excludes NST and OTHER
        operational = prd + sby + egt + sdt + udt
        ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0

        # Run% = PRD / Total * 100
        run_pct = round(prd / total * 100, 1) if total > 0 else 0

        return {
            'total': total,
            'prd': prd,
            'sby': sby,
            'udt': udt,
            'sdt': sdt,
            'egt': egt,
            'nst': nst,
            'other': other,
            # Four main indicators
            'run': run_count,
            'down': down_count,
            'idle': idle_count,
            'eng': eng_count,
            # Percentages
            'ou_pct': ou_pct,
            'run_pct': run_pct
        }
    except Exception as exc:
        if connection:
            connection.close()
        print(f"KPI query failed: {exc}")
        return None


# ============================================================
# Workcenter Cards
# ============================================================

def query_workcenter_cards(filters: Optional[Dict] = None) -> Optional[List[Dict]]:
    """Query workcenter status cards for dashboard with grouping.

    Workcenter groups order:
    0: Cutting (切割)
    1: DB Bonding (焊接_DB)
    2: WB Bonding (焊接_WB)
    3: DW Bonding (焊接_DW)
    4: Molding (成型)
    5: Deflash (去膠)
    6: Blast (水吹砂)
    7: Plating (電鍍)
    8: Marking (移印)
    9: Trim/Form (切彎腳)
    10: PKG SAW (元件切割)
    11: Test (測試)

    Args:
        filters: Optional filter values

    Returns:
        List of workcenter card data or None if query fails.
    """
    try:
        days_back = get_days_back(filters)
        base_sql = get_resource_latest_status_subquery(days_back)

        # Build filter conditions
        where_conditions = []
        if filters:
            where_conditions.extend(build_equipment_filter_sql(filters))

            if filters.get('locations') and len(filters['locations']) > 0:
                loc_list = "', '".join(filters['locations'])
                where_conditions.append(f"LOCATIONNAME IN ('{loc_list}')")

            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                status_list = "', '".join(filters['assetsStatuses'])
                where_conditions.append(f"PJ_ASSETSSTATUS IN ('{status_list}')")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        sql = f"""
            SELECT
                WORKCENTERNAME,
                COUNT(*) as TOTAL,
                SUM(CASE WHEN NEWSTATUSNAME = 'PRD' THEN 1 ELSE 0 END) as PRD,
                SUM(CASE WHEN NEWSTATUSNAME = 'SBY' THEN 1 ELSE 0 END) as SBY,
                SUM(CASE WHEN NEWSTATUSNAME = 'UDT' THEN 1 ELSE 0 END) as UDT,
                SUM(CASE WHEN NEWSTATUSNAME = 'SDT' THEN 1 ELSE 0 END) as SDT,
                SUM(CASE WHEN NEWSTATUSNAME = 'EGT' THEN 1 ELSE 0 END) as EGT,
                SUM(CASE WHEN NEWSTATUSNAME = 'NST' THEN 1 ELSE 0 END) as NST
            FROM ({base_sql}) rs
            WHERE WORKCENTERNAME IS NOT NULL AND {where_clause}
            GROUP BY WORKCENTERNAME
        """
        df = read_sql_df(sql)

        # Group workcenters
        grouped_data = {}
        ungrouped_data = []

        for _, row in df.iterrows():
            wc_name = row['WORKCENTERNAME']
            group_name, order = get_workcenter_group(wc_name)

            if group_name:
                if group_name not in grouped_data:
                    grouped_data[group_name] = {
                        'order': order,
                        'original_wcs': [],
                        'total': 0,
                        'prd': 0,
                        'sby': 0,
                        'udt': 0,
                        'sdt': 0,
                        'egt': 0,
                        'nst': 0
                    }
                grouped_data[group_name]['original_wcs'].append(wc_name)
                grouped_data[group_name]['total'] += int(row['TOTAL'])
                grouped_data[group_name]['prd'] += int(row['PRD'])
                grouped_data[group_name]['sby'] += int(row['SBY'])
                grouped_data[group_name]['udt'] += int(row['UDT'])
                grouped_data[group_name]['sdt'] += int(row['SDT'])
                grouped_data[group_name]['egt'] += int(row['EGT'])
                grouped_data[group_name]['nst'] += int(row['NST'])
            else:
                # Ungrouped workcenter
                ungrouped_data.append({
                    'workcenter': wc_name,
                    'original_wcs': [wc_name],
                    'order': 999,
                    'total': int(row['TOTAL']),
                    'prd': int(row['PRD']),
                    'sby': int(row['SBY']),
                    'udt': int(row['UDT']),
                    'sdt': int(row['SDT']),
                    'egt': int(row['EGT']),
                    'nst': int(row['NST'])
                })

        # Calculate OU% and build result
        result = []

        # Add grouped workcenters
        for group_name, data in grouped_data.items():
            prd = data['prd']
            sby = data['sby']
            egt = data['egt']
            sdt = data['sdt']
            udt = data['udt']
            total = data['total']

            # OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100
            operational = prd + sby + egt + sdt + udt
            ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0
            run_pct = round(prd / total * 100, 1) if total > 0 else 0

            result.append({
                'workcenter': group_name,
                'original_wcs': data['original_wcs'],
                'order': data['order'],
                'total': total,
                'prd': prd,
                'sby': sby,
                'udt': udt,
                'sdt': sdt,
                'egt': egt,
                'nst': data['nst'],
                'ou_pct': ou_pct,
                'run_pct': run_pct,
                'down': udt + sdt,
                'idle': sby + data['nst'],
                'eng': egt
            })

        # Add ungrouped workcenters
        for data in ungrouped_data:
            prd = data['prd']
            sby = data['sby']
            egt = data['egt']
            sdt = data['sdt']
            udt = data['udt']
            total = data['total']

            operational = prd + sby + egt + sdt + udt
            ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0
            run_pct = round(prd / total * 100, 1) if total > 0 else 0

            result.append({
                'workcenter': data['workcenter'],
                'original_wcs': data['original_wcs'],
                'order': data['order'],
                'total': total,
                'prd': prd,
                'sby': sby,
                'udt': udt,
                'sdt': sdt,
                'egt': egt,
                'nst': data['nst'],
                'ou_pct': ou_pct,
                'run_pct': run_pct,
                'down': udt + sdt,
                'idle': sby + data['nst'],
                'eng': egt
            })

        # Sort by order
        result.sort(key=lambda x: (x['order'], -x['total']))

        return result
    except Exception as exc:
        print(f"Workcenter cards query failed: {exc}")
        return None


# ============================================================
# Resource Detail with Job Info
# ============================================================

def query_resource_detail_with_job(
    filters: Optional[Dict] = None,
    limit: int = 200,
    offset: int = 0
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Query resource detail with JOB info for SDT/UDT drill-down.

    Field sources:
    - PJ_LOTID: From DWH.DW_MES_RESOURCE.PJ_LOTID
    - SYMPTOMCODENAME: From DWH.DW_MES_JOB via JOBID
    - CAUSECODENAME: From DWH.DW_MES_JOB via JOBID
    - DOWN_MINUTES: Calculated from MAX(LASTSTATUSCHANGEDATE) - resource's LASTSTATUSCHANGEDATE

    Args:
        filters: Optional filter values
        limit: Maximum rows to return
        offset: Offset for pagination

    Returns:
        Tuple of (DataFrame with detail records, max_status_time string) or (None, None) if query fails.
    """
    try:
        days_back = get_days_back(filters)

        # Build exclusion filters
        location_filter = ""
        if EXCLUDED_LOCATIONS:
            excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
            location_filter = f"AND (r.LOCATIONNAME IS NULL OR r.LOCATIONNAME NOT IN ('{excluded_locations}'))"

        asset_status_filter = ""
        if EXCLUDED_ASSET_STATUSES:
            excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
            asset_status_filter = f"AND (r.PJ_ASSETSSTATUS IS NULL OR r.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

        where_conditions = []
        if filters:
            # Support workcenter group filter
            if filters.get('workcenter'):
                wc_filter = filters['workcenter']
                # Check if it's a merged group
                if wc_filter in WORKCENTER_GROUPS:
                    patterns = WORKCENTER_GROUPS[wc_filter]['patterns']
                    pattern_conditions = []
                    for p in patterns:
                        pattern_conditions.append(f"UPPER(rs.WORKCENTERNAME) LIKE '%{p.upper()}%'")
                    where_conditions.append(f"({' OR '.join(pattern_conditions)})")
                else:
                    where_conditions.append(f"rs.WORKCENTERNAME = '{wc_filter}'")

            if filters.get('original_wcs'):
                # If original workcenter list provided, use IN query
                wcs = filters['original_wcs']
                wc_list = "', '".join(wcs)
                where_conditions.append(f"rs.WORKCENTERNAME IN ('{wc_list}')")

            if filters.get('status'):
                where_conditions.append(f"rs.NEWSTATUSNAME = '{filters['status']}'")

            # Equipment flag filters
            if filters.get('isProduction'):
                where_conditions.append("NVL(rs.PJ_ISPRODUCTION, 0) = 1")
            if filters.get('isKey'):
                where_conditions.append("NVL(rs.PJ_ISKEY, 0) = 1")
            if filters.get('isMonitor'):
                where_conditions.append("NVL(rs.PJ_ISMONITOR, 0) = 1")

            # Multi-select location filter
            if filters.get('locations') and len(filters['locations']) > 0:
                loc_list = "', '".join(filters['locations'])
                where_conditions.append(f"rs.LOCATIONNAME IN ('{loc_list}')")

            # Multi-select asset status filter
            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                status_list = "', '".join(filters['assetsStatuses'])
                where_conditions.append(f"rs.PJ_ASSETSSTATUS IN ('{status_list}')")

        # Default to showing only DOWN status (UDT, SDT)
        where_conditions.append("rs.NEWSTATUSNAME IN ('UDT', 'SDT')")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Left join with JOB table for SDT/UDT details
        start_row = offset + 1
        end_row = offset + limit
        sql = f"""
            WITH latest_txn AS (
                SELECT MAX(COALESCE(TXNDATE, LASTSTATUSCHANGEDATE)) AS MAX_TXNDATE
                FROM DWH.DW_MES_RESOURCESTATUS
            ),
            base_data AS (
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
                    FROM DWH.DW_MES_RESOURCE r
                    JOIN DWH.DW_MES_RESOURCESTATUS s ON r.RESOURCEID = s.HISTORYID
                    CROSS JOIN latest_txn lt
                    WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                        OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
                      AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= lt.MAX_TXNDATE - {days_back}
                      {location_filter}
                      {asset_status_filter}
                )
                WHERE rn = 1
            ),
            max_time AS (
                SELECT MAX(LASTSTATUSCHANGEDATE) AS MAX_STATUS_TIME FROM base_data
            )
            SELECT * FROM (
                SELECT
                    rs.RESOURCENAME,
                    rs.WORKCENTERNAME,
                    rs.RESOURCEFAMILYNAME,
                    rs.NEWSTATUSNAME,
                    rs.NEWREASONNAME,
                    rs.LASTSTATUSCHANGEDATE,
                    rs.PJ_DEPARTMENT,
                    rs.VENDORNAME,
                    rs.VENDORMODEL,
                    rs.PJ_ISPRODUCTION,
                    rs.PJ_ISKEY,
                    rs.PJ_ISMONITOR,
                    j.JOBID,
                    rs.PJ_LOTID,
                    j.JOBORDERNAME,
                    j.JOBSTATUS,
                    j.SYMPTOMCODENAME,
                    j.CAUSECODENAME,
                    j.REPAIRCODENAME,
                    j.CREATEDATE as JOB_CREATEDATE,
                    j.FIRSTCLOCKONDATE,
                    mt.MAX_STATUS_TIME,
                    ROUND((mt.MAX_STATUS_TIME - rs.LASTSTATUSCHANGEDATE) * 24 * 60, 0) as DOWN_MINUTES,
                    ROW_NUMBER() OVER (
                        ORDER BY
                            CASE rs.NEWSTATUSNAME
                                WHEN 'UDT' THEN 1
                                WHEN 'SDT' THEN 2
                                ELSE 3
                            END,
                            rs.LASTSTATUSCHANGEDATE DESC NULLS LAST
                    ) AS rn
                FROM base_data rs
                CROSS JOIN max_time mt
                LEFT JOIN DWH.DW_MES_JOB j ON j.RESOURCEID = rs.RESOURCEID
                                       AND j.CREATEDATE = rs.LASTSTATUSCHANGEDATE
                WHERE {where_clause}
            ) WHERE rn BETWEEN {start_row} AND {end_row}
        """
        df = read_sql_df(sql)

        # Get max_status_time for Last Update display
        max_status_time = None
        if 'MAX_STATUS_TIME' in df.columns and len(df) > 0:
            max_status_time = df['MAX_STATUS_TIME'].iloc[0]
            if pd.notna(max_status_time):
                max_status_time = max_status_time.strftime('%Y-%m-%d %H:%M:%S')

        # Convert datetime columns
        datetime_cols = ['LASTSTATUSCHANGEDATE', 'JOB_CREATEDATE', 'FIRSTCLOCKONDATE', 'MAX_STATUS_TIME']
        for col in datetime_cols:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else None
                )

        return df, max_status_time
    except Exception as exc:
        print(f"Detail query failed: {exc}")
        return None, None


# ============================================================
# OU Trend
# ============================================================

def query_ou_trend(days: int = 7, filters: Optional[Dict] = None) -> Optional[List[Dict]]:
    """Query OU% trend by date using RESOURCESTATUS_SHIFT table.

    Uses HOURS field to calculate actual time-based OU%.
    OU% = PRD_HOURS / (PRD + SBY + EGT + SDT + UDT) * 100

    Args:
        days: Number of days to query (default 7)
        filters: Optional filters (isProduction, isKey, isMonitor)

    Returns:
        List of {date, ou_pct, prd_hours, total_hours} records or None if query fails.
    """
    try:
        # Build location and asset status filters
        location_filter = ""
        if EXCLUDED_LOCATIONS:
            excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
            location_filter = f"AND (ss.LOCATIONNAME IS NULL OR ss.LOCATIONNAME NOT IN ('{excluded_locations}'))"

        asset_status_filter = ""
        if EXCLUDED_ASSET_STATUSES:
            excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
            asset_status_filter = f"AND (ss.PJ_ASSETSSTATUS IS NULL OR ss.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

        # Build filter conditions for equipment flags
        flag_conditions = []
        if filters:
            if filters.get('isProduction'):
                flag_conditions.append("r.PJ_ISPRODUCTION = 1")
            if filters.get('isKey'):
                flag_conditions.append("r.PJ_ISKEY = 1")
            if filters.get('isMonitor'):
                flag_conditions.append("r.PJ_ISMONITOR = 1")

        flag_filter = ""
        if flag_conditions:
            flag_filter = "AND " + " AND ".join(flag_conditions)

        sql = f"""
            SELECT
                TRUNC(ss.TXNDATE) as DATA_DATE,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                SUM(ss.HOURS) as TOTAL_HOURS
            FROM DWH.DW_MES_RESOURCESTATUS_SHIFT ss
            JOIN DWH.DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE ss.TXNDATE >= TRUNC(SYSDATE) - {days}
              AND ss.TXNDATE < TRUNC(SYSDATE)
              AND ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                   OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
              {location_filter}
              {asset_status_filter}
              {flag_filter}
            GROUP BY TRUNC(ss.TXNDATE)
            ORDER BY DATA_DATE
        """
        df = read_sql_df(sql)

        result = []
        for _, row in df.iterrows():
            prd = float(row['PRD_HOURS'] or 0)
            sby = float(row['SBY_HOURS'] or 0)
            udt = float(row['UDT_HOURS'] or 0)
            sdt = float(row['SDT_HOURS'] or 0)
            egt = float(row['EGT_HOURS'] or 0)

            # OU% denominator: PRD + SBY + EGT + SDT + UDT (excludes NST)
            denominator = prd + sby + egt + sdt + udt
            ou_pct = round((prd / denominator * 100), 2) if denominator > 0 else 0

            result.append({
                'date': row['DATA_DATE'].strftime('%Y-%m-%d') if pd.notna(row['DATA_DATE']) else None,
                'ou_pct': ou_pct,
                'prd_hours': round(prd, 1),
                'sby_hours': round(sby, 1),
                'udt_hours': round(udt, 1),
                'sdt_hours': round(sdt, 1),
                'egt_hours': round(egt, 1),
                'total_hours': round(float(row['TOTAL_HOURS'] or 0), 1)
            })

        return result
    except Exception as exc:
        print(f"OU trend query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Utilization Heatmap
# ============================================================

def query_utilization_heatmap(days: int = 7, filters: Optional[Dict] = None) -> Optional[List[Dict]]:
    """Query equipment utilization heatmap data by workcenter and date.

    Uses HOURS field to calculate PRD% per workcenter per day.

    Args:
        days: Number of days to query (default 7)
        filters: Optional filters (isProduction, isKey, isMonitor)

    Returns:
        List of {workcenter, date, prd_pct, prd_hours, avail_hours} records or None if query fails.
    """
    try:
        # Build location and asset status filters
        location_filter = ""
        if EXCLUDED_LOCATIONS:
            excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
            location_filter = f"AND (ss.LOCATIONNAME IS NULL OR ss.LOCATIONNAME NOT IN ('{excluded_locations}'))"

        asset_status_filter = ""
        if EXCLUDED_ASSET_STATUSES:
            excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
            asset_status_filter = f"AND (ss.PJ_ASSETSSTATUS IS NULL OR ss.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

        # Build filter conditions for equipment flags
        flag_conditions = []
        if filters:
            if filters.get('isProduction'):
                flag_conditions.append("r.PJ_ISPRODUCTION = 1")
            if filters.get('isKey'):
                flag_conditions.append("r.PJ_ISKEY = 1")
            if filters.get('isMonitor'):
                flag_conditions.append("r.PJ_ISMONITOR = 1")

        flag_filter = ""
        if flag_conditions:
            flag_filter = "AND " + " AND ".join(flag_conditions)

        sql = f"""
            SELECT
                ss.WORKCENTERNAME,
                TRUNC(ss.TXNDATE) as DATA_DATE,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME IN ('PRD', 'SBY', 'UDT', 'SDT', 'EGT') THEN ss.HOURS ELSE 0 END) as AVAIL_HOURS
            FROM DWH.DW_MES_RESOURCESTATUS_SHIFT ss
            JOIN DWH.DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE ss.TXNDATE >= TRUNC(SYSDATE) - {days}
              AND ss.TXNDATE < TRUNC(SYSDATE)
              AND ss.WORKCENTERNAME IS NOT NULL
              AND ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                   OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
              {location_filter}
              {asset_status_filter}
              {flag_filter}
            GROUP BY ss.WORKCENTERNAME, TRUNC(ss.TXNDATE)
            ORDER BY ss.WORKCENTERNAME, DATA_DATE
        """
        df = read_sql_df(sql)

        # Group by workcenter for heatmap format
        result = []
        for _, row in df.iterrows():
            prd = float(row['PRD_HOURS'] or 0)
            avail = float(row['AVAIL_HOURS'] or 0)
            prd_pct = round((prd / avail * 100), 2) if avail > 0 else 0

            wc_name = row['WORKCENTERNAME']
            # Apply workcenter grouping
            group_name, _ = get_workcenter_group(wc_name)

            result.append({
                'workcenter': wc_name,
                'group': group_name,
                'date': row['DATA_DATE'].strftime('%Y-%m-%d') if pd.notna(row['DATA_DATE']) else None,
                'prd_pct': prd_pct,
                'prd_hours': round(prd, 1),
                'avail_hours': round(avail, 1)
            })

        return result
    except Exception as exc:
        print(f"Utilization heatmap query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None
