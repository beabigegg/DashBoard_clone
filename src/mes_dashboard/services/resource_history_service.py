# -*- coding: utf-8 -*-
"""Resource History Analysis Service.

Provides functions for querying historical equipment performance data including:
- Filter options (workcenters, families)
- Summary data (KPI, trend, heatmap, workcenter comparison)
- Hierarchical detail data (workcenter → family → resource)
- CSV export with streaming
"""

import io
import csv
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    EQUIPMENT_TYPE_FILTER,
    EQUIPMENT_FLAG_FILTERS,
)

logger = logging.getLogger('mes_dashboard.resource_history')

# Maximum allowed query range in days
MAX_QUERY_DAYS = 730

# E10 Status definitions
E10_STATUSES = ['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST']


# ============================================================
# Filter Options
# ============================================================

def get_filter_options() -> Optional[Dict[str, Any]]:
    """Get filter options from cache.

    Uses cached workcenter groups from DW_PJ_LOT_V and resource families from DW_MES_RESOURCE.

    Returns:
        Dict with:
        - 'workcenter_groups': List of {name, sequence} sorted by sequence
        - 'families': List of family names sorted alphabetically
        Or None if cache loading fails.
    """
    from mes_dashboard.services.filter_cache import (
        get_workcenter_groups,
        get_resource_families,
    )

    try:
        groups = get_workcenter_groups()
        families = get_resource_families()

        if groups is None or families is None:
            logger.error("Filter cache not available")
            return None

        return {
            'workcenter_groups': groups,
            'families': families
        }
    except Exception as exc:
        logger.error(f"Filter options query failed: {exc}")
        return None


# ============================================================
# Summary Query
# ============================================================

def query_summary(
    start_date: str,
    end_date: str,
    granularity: str = 'day',
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Optional[Dict[str, Any]]:
    """Query summary data including KPI, trend, heatmap, and workcenter comparison.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        granularity: Time granularity ('day', 'week', 'month', 'year')
        workcenter_groups: Optional list of WORKCENTER_GROUP names to filter
        families: Optional list of RESOURCEFAMILYNAME values to filter
        is_production: Filter by production flag
        is_key: Filter by key equipment flag
        is_monitor: Filter by monitor flag

    Returns:
        Dict with 'kpi', 'trend', 'heatmap', 'workcenter_comparison' sections,
        or None if query fails.
    """
    # Validate date range
    validation = _validate_date_range(start_date, end_date)
    if validation:
        return {'error': validation}

    try:
        # Build SQL components
        date_trunc = _get_date_trunc(granularity)
        location_filter = _build_location_filter('r')
        asset_status_filter = _build_asset_status_filter('r')
        equipment_filter = _build_equipment_flags_filter(is_production, is_key, is_monitor, 'r')
        workcenter_filter = _build_workcenter_groups_filter(workcenter_groups, 'r')
        family_filter = _build_families_filter(families, 'r')

        # Common CTE with MATERIALIZE hint to force Oracle to materialize the subquery
        # This prevents the optimizer from inlining the CTE multiple times
        base_cte = f"""
            WITH shift_data AS (
                SELECT /*+ MATERIALIZE */ HISTORYID, TXNDATE, OLDSTATUSNAME, HOURS
                FROM DW_MES_RESOURCESTATUS_SHIFT
                WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
                  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
            )
        """

        # Common filter conditions
        common_filters = f"""
            WHERE {EQUIPMENT_TYPE_FILTER}
              {location_filter}
              {asset_status_filter}
              {equipment_filter}
              {workcenter_filter}
              {family_filter}
        """

        # Build all 4 SQL queries
        kpi_sql = f"""
            {base_cte}
            SELECT
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'NST' THEN ss.HOURS ELSE 0 END) as NST_HOURS,
                COUNT(DISTINCT ss.HISTORYID) as MACHINE_COUNT
            FROM shift_data ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            {common_filters}
        """

        trend_sql = f"""
            {base_cte}
            SELECT
                {date_trunc} as DATA_DATE,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'NST' THEN ss.HOURS ELSE 0 END) as NST_HOURS,
                COUNT(DISTINCT ss.HISTORYID) as MACHINE_COUNT
            FROM shift_data ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            {common_filters}
            GROUP BY {date_trunc}
            ORDER BY DATA_DATE
        """

        heatmap_sql = f"""
            {base_cte}
            SELECT
                r.WORKCENTERNAME,
                {date_trunc} as DATA_DATE,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS
            FROM shift_data ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE r.WORKCENTERNAME IS NOT NULL
              AND {EQUIPMENT_TYPE_FILTER}
              {location_filter}
              {asset_status_filter}
              {equipment_filter}
              {workcenter_filter}
              {family_filter}
            GROUP BY r.WORKCENTERNAME, {date_trunc}
            ORDER BY r.WORKCENTERNAME, DATA_DATE
        """

        comparison_sql = f"""
            {base_cte}
            SELECT
                r.WORKCENTERNAME,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                COUNT(DISTINCT ss.HISTORYID) as MACHINE_COUNT
            FROM shift_data ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE r.WORKCENTERNAME IS NOT NULL
              AND {EQUIPMENT_TYPE_FILTER}
              {location_filter}
              {asset_status_filter}
              {equipment_filter}
              {workcenter_filter}
              {family_filter}
            GROUP BY r.WORKCENTERNAME
            ORDER BY PRD_HOURS DESC
        """

        # Execute all 4 queries in parallel using ThreadPoolExecutor
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(read_sql_df, kpi_sql): 'kpi',
                executor.submit(read_sql_df, trend_sql): 'trend',
                executor.submit(read_sql_df, heatmap_sql): 'heatmap',
                executor.submit(read_sql_df, comparison_sql): 'comparison',
            }
            for future in as_completed(futures):
                query_name = futures[future]
                try:
                    results[query_name] = future.result()
                except Exception as exc:
                    logger.error(f"{query_name} query failed: {exc}")
                    results[query_name] = pd.DataFrame()

        # Build response from results
        kpi = _build_kpi_from_df(results.get('kpi', pd.DataFrame()))
        trend = _build_trend_from_df(results.get('trend', pd.DataFrame()), granularity)
        heatmap = _build_heatmap_from_df(results.get('heatmap', pd.DataFrame()), granularity)
        workcenter_comparison = _build_comparison_from_df(results.get('comparison', pd.DataFrame()))

        return {
            'kpi': kpi,
            'trend': trend,
            'heatmap': heatmap,
            'workcenter_comparison': workcenter_comparison
        }
    except Exception as exc:
        logger.error(f"Summary query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Detail Query
# ============================================================

# Maximum records limit for detail query (disabled - no limit)
# MAX_DETAIL_RECORDS = 5000


def query_detail(
    start_date: str,
    end_date: str,
    granularity: str = 'day',
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Optional[Dict[str, Any]]:
    """Query hierarchical detail data.

    Returns flat data with workcenter, family, resource dimensions.
    Frontend handles hierarchy assembly.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        granularity: Time granularity ('day', 'week', 'month', 'year')
        workcenter_groups: Optional list of WORKCENTER_GROUP names to filter
        families: Optional list of RESOURCEFAMILYNAME values to filter
        is_production: Filter by production flag
        is_key: Filter by key equipment flag
        is_monitor: Filter by monitor flag

    Returns:
        Dict with 'data', 'total', 'truncated' fields,
        or None if query fails.
    """
    # Validate date range
    validation = _validate_date_range(start_date, end_date)
    if validation:
        return {'error': validation}

    try:
        # Build SQL components
        location_filter = _build_location_filter('r')
        asset_status_filter = _build_asset_status_filter('r')
        equipment_filter = _build_equipment_flags_filter(is_production, is_key, is_monitor, 'r')
        workcenter_filter = _build_workcenter_groups_filter(workcenter_groups, 'r')
        family_filter = _build_families_filter(families, 'r')

        # Common CTE with MATERIALIZE hint
        base_cte = f"""
            WITH shift_data AS (
                SELECT /*+ MATERIALIZE */ HISTORYID, OLDSTATUSNAME, HOURS
                FROM DW_MES_RESOURCESTATUS_SHIFT
                WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
                  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
            )
        """

        # Common filter conditions
        common_filters = f"""
            WHERE {EQUIPMENT_TYPE_FILTER}
              {location_filter}
              {asset_status_filter}
              {equipment_filter}
              {workcenter_filter}
              {family_filter}
        """

        # Query all detail data (no pagination)
        detail_sql = f"""
            {base_cte}
            SELECT
                r.WORKCENTERNAME,
                r.RESOURCEFAMILYNAME,
                r.RESOURCENAME,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'NST' THEN ss.HOURS ELSE 0 END) as NST_HOURS,
                SUM(ss.HOURS) as TOTAL_HOURS
            FROM shift_data ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            {common_filters}
            GROUP BY r.WORKCENTERNAME, r.RESOURCEFAMILYNAME, r.RESOURCENAME
            ORDER BY r.WORKCENTERNAME, r.RESOURCEFAMILYNAME, r.RESOURCENAME
        """

        detail_df = read_sql_df(detail_sql)
        total = len(detail_df) if detail_df is not None else 0

        data = _build_detail_from_df(detail_df)

        return {
            'data': data,
            'total': total,
            'truncated': False,
            'max_records': None
        }
    except Exception as exc:
        logger.error(f"Detail query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# CSV Export
# ============================================================

def export_csv(
    start_date: str,
    end_date: str,
    granularity: str = 'day',
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Generator[str, None, None]:
    """Generate CSV data as a stream for export.

    Yields CSV rows one at a time to avoid memory issues with large datasets.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        granularity: Time granularity
        workcenter_groups: Optional list of WORKCENTER_GROUP names to filter
        families: Optional list of RESOURCEFAMILYNAME values to filter
        is_production: Filter by production flag
        is_key: Filter by key equipment flag
        is_monitor: Filter by monitor flag

    Yields:
        CSV rows as strings
    """
    # Validate date range
    validation = _validate_date_range(start_date, end_date)
    if validation:
        yield f"Error: {validation}\n"
        return

    try:
        # Build SQL components
        location_filter = _build_location_filter('r')
        asset_status_filter = _build_asset_status_filter('r')
        equipment_filter = _build_equipment_flags_filter(is_production, is_key, is_monitor, 'r')
        workcenter_filter = _build_workcenter_groups_filter(workcenter_groups, 'r')
        family_filter = _build_families_filter(families, 'r')

        # Query all data with CTE and MATERIALIZE hint for performance optimization
        sql = f"""
            WITH shift_data AS (
                SELECT /*+ MATERIALIZE */ HISTORYID, OLDSTATUSNAME, HOURS
                FROM DW_MES_RESOURCESTATUS_SHIFT
                WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
                  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
            )
            SELECT
                r.WORKCENTERNAME,
                r.RESOURCEFAMILYNAME,
                r.RESOURCENAME,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'NST' THEN ss.HOURS ELSE 0 END) as NST_HOURS,
                SUM(ss.HOURS) as TOTAL_HOURS
            FROM shift_data ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE {EQUIPMENT_TYPE_FILTER}
              {location_filter}
              {asset_status_filter}
              {equipment_filter}
              {workcenter_filter}
              {family_filter}
            GROUP BY r.WORKCENTERNAME, r.RESOURCEFAMILYNAME, r.RESOURCENAME
            ORDER BY r.WORKCENTERNAME, r.RESOURCEFAMILYNAME, r.RESOURCENAME
        """
        df = read_sql_df(sql)

        # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
        from mes_dashboard.services.filter_cache import get_workcenter_mapping
        wc_mapping = get_workcenter_mapping() or {}

        # Write CSV header
        output = io.StringIO()
        writer = csv.writer(output)
        headers = [
            '站點', '型號', '機台', 'OU%',
            'PRD(h)', 'PRD(%)', 'SBY(h)', 'SBY(%)',
            'UDT(h)', 'UDT(%)', 'SDT(h)', 'SDT(%)',
            'EGT(h)', 'EGT(%)', 'NST(h)', 'NST(%)'
        ]
        writer.writerow(headers)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)

        # Write data rows
        for _, row in df.iterrows():
            prd = float(row['PRD_HOURS'] or 0)
            sby = float(row['SBY_HOURS'] or 0)
            udt = float(row['UDT_HOURS'] or 0)
            sdt = float(row['SDT_HOURS'] or 0)
            egt = float(row['EGT_HOURS'] or 0)
            nst = float(row['NST_HOURS'] or 0)
            total = float(row['TOTAL_HOURS'] or 0)

            # Map WORKCENTERNAME to WORKCENTER_GROUP
            wc_name = row['WORKCENTERNAME']
            wc_info = wc_mapping.get(wc_name, {})
            wc_group = wc_info.get('group', wc_name)  # Fallback to workcentername if no mapping

            # Calculate percentages
            ou_pct = _calc_ou_pct(prd, sby, udt, sdt, egt)
            prd_pct = round(prd / total * 100, 1) if total > 0 else 0
            sby_pct = round(sby / total * 100, 1) if total > 0 else 0
            udt_pct = round(udt / total * 100, 1) if total > 0 else 0
            sdt_pct = round(sdt / total * 100, 1) if total > 0 else 0
            egt_pct = round(egt / total * 100, 1) if total > 0 else 0
            nst_pct = round(nst / total * 100, 1) if total > 0 else 0

            csv_row = [
                wc_group,
                row['RESOURCEFAMILYNAME'],
                row['RESOURCENAME'],
                f"{ou_pct}%",
                round(prd, 1), f"{prd_pct}%",
                round(sby, 1), f"{sby_pct}%",
                round(udt, 1), f"{udt_pct}%",
                round(sdt, 1), f"{sdt_pct}%",
                round(egt, 1), f"{egt_pct}%",
                round(nst, 1), f"{nst_pct}%"
            ]
            writer.writerow(csv_row)
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)

    except Exception as exc:
        logger.error(f"CSV export failed: {exc}")
        yield f"Error: {exc}\n"


# ============================================================
# Helper Functions
# ============================================================

def _validate_date_range(start_date: str, end_date: str) -> Optional[str]:
    """Validate date range doesn't exceed MAX_QUERY_DAYS."""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        diff = (end - start).days

        if diff > MAX_QUERY_DAYS:
            return f'查詢範圍不可超過 {MAX_QUERY_DAYS} 天（兩年）'
        if diff < 0:
            return '結束日期必須大於起始日期'
        return None
    except ValueError as e:
        return f'日期格式錯誤: {e}'


def _get_date_trunc(granularity: str) -> str:
    """Get Oracle TRUNC expression for date granularity."""
    trunc_map = {
        'day': "TRUNC(ss.TXNDATE)",
        'week': "TRUNC(ss.TXNDATE, 'IW')",
        'month': "TRUNC(ss.TXNDATE, 'MM')",
        'year': "TRUNC(ss.TXNDATE, 'YYYY')"
    }
    return trunc_map.get(granularity, "TRUNC(ss.TXNDATE)")


def _build_location_filter(alias: str) -> str:
    """Build SQL filter for excluded locations."""
    if not EXCLUDED_LOCATIONS:
        return ""
    excluded = "', '".join(EXCLUDED_LOCATIONS)
    return f"AND ({alias}.LOCATIONNAME IS NULL OR {alias}.LOCATIONNAME NOT IN ('{excluded}'))"


def _build_asset_status_filter(alias: str) -> str:
    """Build SQL filter for excluded asset statuses."""
    if not EXCLUDED_ASSET_STATUSES:
        return ""
    excluded = "', '".join(EXCLUDED_ASSET_STATUSES)
    return f"AND ({alias}.PJ_ASSETSSTATUS IS NULL OR {alias}.PJ_ASSETSSTATUS NOT IN ('{excluded}'))"


def _build_equipment_flags_filter(
    is_production: bool,
    is_key: bool,
    is_monitor: bool,
    alias: str
) -> str:
    """Build SQL filter for equipment flags."""
    conditions = []
    if is_production:
        conditions.append(f"NVL({alias}.PJ_ISPRODUCTION, 0) = 1")
    if is_key:
        conditions.append(f"NVL({alias}.PJ_ISKEY, 0) = 1")
    if is_monitor:
        conditions.append(f"NVL({alias}.PJ_ISMONITOR, 0) = 1")
    return "AND " + " AND ".join(conditions) if conditions else ""


def _build_workcenter_groups_filter(groups: Optional[List[str]], alias: str) -> str:
    """Build SQL filter for workcenter groups.

    Uses filter_cache to get workcentername list for selected groups.

    Args:
        groups: List of WORKCENTER_GROUP names, or None for no filter
        alias: Table alias for WORKCENTERNAME column

    Returns:
        SQL filter clause (empty string if no filter)
    """
    if not groups:
        return ""

    from mes_dashboard.services.filter_cache import get_workcenters_for_groups
    workcenters = get_workcenters_for_groups(groups)

    if not workcenters:
        return ""

    # Escape single quotes and build IN clause
    escaped = [wc.replace("'", "''") for wc in workcenters]
    in_list = "', '".join(escaped)
    return f"AND {alias}.WORKCENTERNAME IN ('{in_list}')"


def _build_families_filter(families: Optional[List[str]], alias: str) -> str:
    """Build SQL filter for resource families.

    Args:
        families: List of RESOURCEFAMILYNAME values, or None for no filter
        alias: Table alias for RESOURCEFAMILYNAME column

    Returns:
        SQL filter clause (empty string if no filter)
    """
    if not families:
        return ""

    # Escape single quotes and build IN clause
    escaped = [f.replace("'", "''") for f in families]
    in_list = "', '".join(escaped)
    return f"AND {alias}.RESOURCEFAMILYNAME IN ('{in_list}')"


def _safe_float(value, default=0.0) -> float:
    """Safely convert value to float, handling NaN and None."""
    if value is None or pd.isna(value):
        return default
    return float(value)


def _calc_ou_pct(prd: float, sby: float, udt: float, sdt: float, egt: float) -> float:
    """Calculate OU% = PRD / (PRD + SBY + UDT + SDT + EGT) * 100."""
    denominator = prd + sby + udt + sdt + egt
    return round(prd / denominator * 100, 1) if denominator > 0 else 0


def _build_kpi_from_df(df: pd.DataFrame) -> Dict[str, Any]:
    """Build KPI dict from query result DataFrame."""
    if df is None or len(df) == 0:
        return {
            'ou_pct': 0,
            'prd_hours': 0,
            'sby_hours': 0,
            'udt_hours': 0,
            'sdt_hours': 0,
            'egt_hours': 0,
            'nst_hours': 0,
            'machine_count': 0
        }

    row = df.iloc[0]
    prd = _safe_float(row['PRD_HOURS'])
    sby = _safe_float(row['SBY_HOURS'])
    udt = _safe_float(row['UDT_HOURS'])
    sdt = _safe_float(row['SDT_HOURS'])
    egt = _safe_float(row['EGT_HOURS'])
    nst = _safe_float(row['NST_HOURS'])
    machine_count = int(_safe_float(row['MACHINE_COUNT']))

    return {
        'ou_pct': _calc_ou_pct(prd, sby, udt, sdt, egt),
        'prd_hours': round(prd, 1),
        'sby_hours': round(sby, 1),
        'udt_hours': round(udt, 1),
        'sdt_hours': round(sdt, 1),
        'egt_hours': round(egt, 1),
        'nst_hours': round(nst, 1),
        'machine_count': machine_count
    }


def _format_date(date_val, granularity: str) -> Optional[str]:
    """Format date value based on granularity."""
    if pd.isna(date_val):
        return None

    if granularity == 'year':
        return date_val.strftime('%Y')
    elif granularity == 'month':
        return date_val.strftime('%Y-%m')
    elif granularity == 'week':
        return date_val.strftime('%Y-%m-%d')  # Week start date
    else:
        return date_val.strftime('%Y-%m-%d')


def _build_trend_from_df(df: pd.DataFrame, granularity: str) -> List[Dict]:
    """Build trend data from query result DataFrame."""
    if df is None or len(df) == 0:
        return []

    result = []
    for _, row in df.iterrows():
        prd = _safe_float(row['PRD_HOURS'])
        sby = _safe_float(row['SBY_HOURS'])
        udt = _safe_float(row['UDT_HOURS'])
        sdt = _safe_float(row['SDT_HOURS'])
        egt = _safe_float(row['EGT_HOURS'])
        nst = _safe_float(row['NST_HOURS'])

        result.append({
            'date': _format_date(row['DATA_DATE'], granularity),
            'ou_pct': _calc_ou_pct(prd, sby, udt, sdt, egt),
            'prd_hours': round(prd, 1),
            'sby_hours': round(sby, 1),
            'udt_hours': round(udt, 1),
            'sdt_hours': round(sdt, 1),
            'egt_hours': round(egt, 1),
            'nst_hours': round(nst, 1)
        })

    return result


def _build_heatmap_from_df(df: pd.DataFrame, granularity: str) -> List[Dict]:
    """Build heatmap data from query result DataFrame."""
    if df is None or len(df) == 0:
        return []

    # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    wc_mapping = get_workcenter_mapping() or {}

    # Aggregate data by WORKCENTER_GROUP and date
    aggregated = {}
    for _, row in df.iterrows():
        wc_name = row['WORKCENTERNAME']
        # Skip rows with NaN workcenter name
        if pd.isna(wc_name):
            continue
        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get('group', wc_name)
        date_str = _format_date(row['DATA_DATE'], granularity)
        key = (wc_group, date_str)

        if key not in aggregated:
            aggregated[key] = {'prd': 0, 'sby': 0, 'udt': 0, 'sdt': 0, 'egt': 0}

        aggregated[key]['prd'] += _safe_float(row['PRD_HOURS'])
        aggregated[key]['sby'] += _safe_float(row['SBY_HOURS'])
        aggregated[key]['udt'] += _safe_float(row['UDT_HOURS'])
        aggregated[key]['sdt'] += _safe_float(row['SDT_HOURS'])
        aggregated[key]['egt'] += _safe_float(row['EGT_HOURS'])

    result = []
    for (wc_group, date_str), data in aggregated.items():
        result.append({
            'workcenter': wc_group,
            'date': date_str,
            'ou_pct': _calc_ou_pct(data['prd'], data['sby'], data['udt'], data['sdt'], data['egt'])
        })

    # Sort by workcenter and date
    result.sort(key=lambda x: (x['workcenter'], x['date'] or ''))
    return result


def _build_comparison_from_df(df: pd.DataFrame) -> List[Dict]:
    """Build workcenter comparison data from query result DataFrame."""
    if df is None or len(df) == 0:
        return []

    # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    wc_mapping = get_workcenter_mapping() or {}

    # Aggregate data by WORKCENTER_GROUP
    aggregated = {}
    for _, row in df.iterrows():
        wc_name = row['WORKCENTERNAME']
        # Skip rows with NaN workcenter name
        if pd.isna(wc_name):
            continue
        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get('group', wc_name)

        if wc_group not in aggregated:
            aggregated[wc_group] = {'prd': 0, 'sby': 0, 'udt': 0, 'sdt': 0, 'egt': 0, 'machine_count': 0}

        aggregated[wc_group]['prd'] += _safe_float(row['PRD_HOURS'])
        aggregated[wc_group]['sby'] += _safe_float(row['SBY_HOURS'])
        aggregated[wc_group]['udt'] += _safe_float(row['UDT_HOURS'])
        aggregated[wc_group]['sdt'] += _safe_float(row['SDT_HOURS'])
        aggregated[wc_group]['egt'] += _safe_float(row['EGT_HOURS'])
        aggregated[wc_group]['machine_count'] += int(_safe_float(row['MACHINE_COUNT']))

    result = []
    for wc_group, data in aggregated.items():
        result.append({
            'workcenter': wc_group,
            'ou_pct': _calc_ou_pct(data['prd'], data['sby'], data['udt'], data['sdt'], data['egt']),
            'prd_hours': round(data['prd'], 1),
            'machine_count': data['machine_count']
        })

    # Sort by OU% descending
    result.sort(key=lambda x: x['ou_pct'], reverse=True)
    return result


def _build_detail_from_df(df: pd.DataFrame) -> List[Dict]:
    """Build detail data from query result DataFrame."""
    if df is None or len(df) == 0:
        return []

    # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    wc_mapping = get_workcenter_mapping() or {}

    result = []
    for _, row in df.iterrows():
        # Skip rows with NaN workcenter name
        wc_name = row['WORKCENTERNAME']
        if pd.isna(wc_name):
            continue

        prd = _safe_float(row['PRD_HOURS'])
        sby = _safe_float(row['SBY_HOURS'])
        udt = _safe_float(row['UDT_HOURS'])
        sdt = _safe_float(row['SDT_HOURS'])
        egt = _safe_float(row['EGT_HOURS'])
        nst = _safe_float(row['NST_HOURS'])
        total = _safe_float(row['TOTAL_HOURS'])

        # Map WORKCENTERNAME to WORKCENTER_GROUP
        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get('group', wc_name)  # Fallback to workcentername if no mapping

        # Handle NaN in string fields
        family = row['RESOURCEFAMILYNAME']
        resource = row['RESOURCENAME']

        result.append({
            'workcenter': wc_group,
            'family': family if not pd.isna(family) else '',
            'resource': resource if not pd.isna(resource) else '',
            'ou_pct': _calc_ou_pct(prd, sby, udt, sdt, egt),
            'prd_hours': round(prd, 1),
            'prd_pct': round(prd / total * 100, 1) if total > 0 else 0,
            'sby_hours': round(sby, 1),
            'sby_pct': round(sby / total * 100, 1) if total > 0 else 0,
            'udt_hours': round(udt, 1),
            'udt_pct': round(udt / total * 100, 1) if total > 0 else 0,
            'sdt_hours': round(sdt, 1),
            'sdt_pct': round(sdt / total * 100, 1) if total > 0 else 0,
            'egt_hours': round(egt, 1),
            'egt_pct': round(egt / total * 100, 1) if total > 0 else 0,
            'nst_hours': round(nst, 1),
            'nst_pct': round(nst / total * 100, 1) if total > 0 else 0,
            'machine_count': 1
        })

    return result
