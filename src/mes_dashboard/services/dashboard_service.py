# -*- coding: utf-8 -*-
"""Dashboard and KPI query services for MES Dashboard.

Provides functions to query dashboard KPIs, workcenter cards,
resource details with job info, OU trends, and utilization heatmap.
"""

import logging
import pandas as pd
from typing import Optional, Dict, List, Any, Tuple

logger = logging.getLogger('mes_dashboard.dashboard_service')

from mes_dashboard.core.database import (
    get_db_connection,
    read_sql_df,
    DatabasePoolExhaustedError,
    DatabaseCircuitOpenError,
)
from mes_dashboard.core.utils import get_days_back, build_equipment_filter_sql
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    DEFAULT_DAYS_BACK,
)
from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS, get_workcenter_group
from mes_dashboard.services.resource_service import (
    get_resource_latest_status_subquery,
    get_resource_status_summary,
    get_workcenter_status_matrix,
)
from mes_dashboard.sql import SQLLoader, QueryBuilder
from mes_dashboard.sql.filters import CommonFilters


# ============================================================
# Dashboard KPI Queries
# ============================================================

def query_dashboard_kpi(filters: Optional[Dict] = None) -> Optional[Dict]:
    """Query overall KPI for dashboard header using cached resource data.

    Status categories:
    - RUN: PRD (Production)
    - DOWN: UDT + SDT (Down Time)
    - IDLE: SBY + NST (Idle)
    - ENG: EGT (Engineering Time)

    OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100

    Uses get_resource_status_summary() for fast, cached data from Redis.

    Args:
        filters: Optional filter values (is_production, is_key, is_monitor)

    Returns:
        Dict with KPI data or None if query fails.
    """
    try:
        # Extract flag filters for cached query
        is_production = None
        is_key = None
        is_monitor = None
        if filters:
            if filters.get('isProduction'):
                is_production = True
            if filters.get('isKey'):
                is_key = True
            if filters.get('isMonitor'):
                is_monitor = True

        # Use cached resource status summary for fast response
        summary = get_resource_status_summary(
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not summary or summary.get('total_count', 0) == 0:
            return None

        # Extract counts from summary
        by_status = summary.get('by_status', {})
        total = summary.get('total_count', 0)
        prd = by_status.get('PRD', 0)
        sby = by_status.get('SBY', 0)
        udt = by_status.get('UDT', 0)
        sdt = by_status.get('SDT', 0)
        egt = by_status.get('EGT', 0)
        nst = by_status.get('NST', 0)
        other = by_status.get('OTHER', 0)

        # Status categories
        run_count = prd                    # RUN = PRD
        down_count = udt + sdt             # DOWN = UDT + SDT
        idle_count = sby + nst             # IDLE = SBY + NST
        eng_count = egt                    # ENG = EGT

        # OU% from cached summary (already calculated)
        ou_pct = summary.get('ou_pct', 0)

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
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"KPI query failed: {exc}")
        return None


# ============================================================
# Workcenter Cards
# ============================================================

def query_workcenter_cards(filters: Optional[Dict] = None) -> Optional[List[Dict]]:
    """Query workcenter status cards for dashboard with grouping.

    Uses cached resource data from Redis for fast response times.
    Data is pre-grouped by workcenter group in the cache.

    Args:
        filters: Optional filter values (isProduction, isKey, isMonitor)

    Returns:
        List of workcenter card data or None if query fails.
    """
    try:
        # Extract flag filters for cached query
        is_production = None
        is_key = None
        is_monitor = None
        if filters:
            if filters.get('isProduction'):
                is_production = True
            if filters.get('isKey'):
                is_key = True
            if filters.get('isMonitor'):
                is_monitor = True

        # Use cached workcenter matrix for fast response
        matrix = get_workcenter_status_matrix(
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not matrix:
            return None

        # Transform matrix data to expected card format
        result = []
        for row in matrix:
            group_name = row['workcenter_group']
            order = row['workcenter_sequence']
            total = row['total']
            prd = row['PRD']
            sby = row['SBY']
            udt = row['UDT']
            sdt = row['SDT']
            egt = row['EGT']
            nst = row['NST']

            # OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100
            operational = prd + sby + egt + sdt + udt
            ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0
            run_pct = round(prd / total * 100, 1) if total > 0 else 0

            result.append({
                'workcenter': group_name,
                'original_wcs': [],  # Not available from cache (aggregated by group)
                'order': order,
                'total': total,
                'prd': prd,
                'sby': sby,
                'udt': udt,
                'sdt': sdt,
                'egt': egt,
                'nst': nst,
                'ou_pct': ou_pct,
                'run_pct': run_pct,
                'down': udt + sdt,
                'idle': sby + nst,
                'eng': egt
            })

        # Sort by order (already sorted by sequence, but ensure consistency)
        result.sort(key=lambda x: (x['order'], -x['total']))

        return result
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Workcenter cards query failed: {exc}")
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

        # Build exclusion filters using CommonFilters (legacy format for SQL placeholders)
        location_filter = CommonFilters.build_location_filter_legacy(
            excluded_locations=list(EXCLUDED_LOCATIONS) if EXCLUDED_LOCATIONS else None
        )
        if location_filter:
            location_filter = f"AND {location_filter.replace('LOCATIONNAME', 'r.LOCATIONNAME')}"

        asset_status_filter = CommonFilters.build_asset_status_filter_legacy(
            excluded_statuses=list(EXCLUDED_ASSET_STATUSES) if EXCLUDED_ASSET_STATUSES else None
        )
        if asset_status_filter:
            asset_status_filter = f"AND {asset_status_filter.replace('PJ_ASSETSSTATUS', 'r.PJ_ASSETSSTATUS')}"

        # Build filter conditions using QueryBuilder for safety
        builder = QueryBuilder()
        if filters:
            # Support workcenter group filter
            if filters.get('workcenter'):
                wc_filter = filters['workcenter']
                # Check if it's a merged group
                if wc_filter in WORKCENTER_GROUPS:
                    patterns = WORKCENTER_GROUPS[wc_filter]['patterns']
                    # Use parameterized OR LIKE conditions (safe escaping)
                    builder.add_or_like_conditions(
                        'rs.WORKCENTERNAME',
                        patterns,
                        case_insensitive=True,
                    )
                else:
                    builder.add_param_condition('rs.WORKCENTERNAME', wc_filter)

            if filters.get('original_wcs'):
                # If original workcenter list provided, use IN query
                builder.add_in_condition('rs.WORKCENTERNAME', list(filters['original_wcs']))

            if filters.get('status'):
                builder.add_param_condition('rs.NEWSTATUSNAME', filters['status'])

            # Equipment flag filters (safe - boolean values)
            if filters.get('isProduction'):
                builder.add_condition("NVL(rs.PJ_ISPRODUCTION, 0) = 1")
            if filters.get('isKey'):
                builder.add_condition("NVL(rs.PJ_ISKEY, 0) = 1")
            if filters.get('isMonitor'):
                builder.add_condition("NVL(rs.PJ_ISMONITOR, 0) = 1")

            # Multi-select location filter (parameterized)
            if filters.get('locations') and len(filters['locations']) > 0:
                builder.add_in_condition('rs.LOCATIONNAME', list(filters['locations']))

            # Multi-select asset status filter (parameterized)
            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                builder.add_in_condition('rs.PJ_ASSETSSTATUS', list(filters['assetsStatuses']))

        # Default to showing only DOWN status (UDT, SDT)
        builder.add_in_condition('rs.NEWSTATUSNAME', ['UDT', 'SDT'])

        conditions_sql = builder.get_conditions_sql()
        params = builder.params.copy()
        where_clause = conditions_sql if conditions_sql else "1=1"

        # Add pagination parameters
        start_row = offset + 1
        end_row = offset + limit
        params['start_row'] = start_row
        params['end_row'] = end_row

        # Load SQL from file and replace placeholders
        sql = SQLLoader.load("dashboard/resource_detail_with_job")
        sql = sql.replace("{{ DAYS_BACK }}", str(days_back))
        sql = sql.replace("{{ LOCATION_FILTER }}", location_filter if location_filter else "")
        sql = sql.replace("{{ ASSET_STATUS_FILTER }}", asset_status_filter if asset_status_filter else "")
        sql = sql.replace("{{ WHERE_CLAUSE }}", where_clause)
        df = read_sql_df(sql, params)

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
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Detail query failed: {exc}")
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
        # Build exclusion filters using CommonFilters (legacy format for SQL placeholders)
        location_filter = CommonFilters.build_location_filter_legacy(
            excluded_locations=list(EXCLUDED_LOCATIONS) if EXCLUDED_LOCATIONS else None
        )
        if location_filter:
            location_filter = f"AND {location_filter.replace('LOCATIONNAME', 'ss.LOCATIONNAME')}"

        asset_status_filter = CommonFilters.build_asset_status_filter_legacy(
            excluded_statuses=list(EXCLUDED_ASSET_STATUSES) if EXCLUDED_ASSET_STATUSES else None
        )
        if asset_status_filter:
            asset_status_filter = f"AND {asset_status_filter.replace('PJ_ASSETSSTATUS', 'ss.PJ_ASSETSSTATUS')}"

        # Build filter conditions for equipment flags (safe - boolean values)
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

        # Load SQL from file and replace placeholders
        sql = SQLLoader.load("dashboard/ou_trend")
        sql = sql.replace("{{ LOCATION_FILTER }}", location_filter if location_filter else "")
        sql = sql.replace("{{ ASSET_STATUS_FILTER }}", asset_status_filter if asset_status_filter else "")
        sql = sql.replace("{{ FLAG_FILTER }}", flag_filter)

        df = read_sql_df(sql, {'days': days})

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
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"OU trend query failed: {exc}", exc_info=True)
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
        # Build exclusion filters using CommonFilters (legacy format for SQL placeholders)
        location_filter = CommonFilters.build_location_filter_legacy(
            excluded_locations=list(EXCLUDED_LOCATIONS) if EXCLUDED_LOCATIONS else None
        )
        if location_filter:
            location_filter = f"AND {location_filter.replace('LOCATIONNAME', 'r.LOCATIONNAME')}"
        else:
            location_filter = ""

        asset_status_filter = CommonFilters.build_asset_status_filter_legacy(
            excluded_statuses=list(EXCLUDED_ASSET_STATUSES) if EXCLUDED_ASSET_STATUSES else None
        )
        if asset_status_filter:
            asset_status_filter = f"AND {asset_status_filter.replace('PJ_ASSETSSTATUS', 'r.PJ_ASSETSSTATUS')}"
        else:
            asset_status_filter = ""

        # Build filter conditions for equipment flags (safe - boolean values)
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

        # Load SQL from file and replace placeholders
        sql = SQLLoader.load("dashboard/heatmap")
        sql = sql.replace("{{ LOCATION_FILTER }}", location_filter)
        sql = sql.replace("{{ ASSET_STATUS_FILTER }}", asset_status_filter)
        sql = sql.replace("{{ FLAG_FILTER }}", flag_filter)

        df = read_sql_df(sql, {'days': days})

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
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Utilization heatmap query failed: {exc}", exc_info=True)
        return None
