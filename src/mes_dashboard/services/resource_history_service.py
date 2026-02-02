# -*- coding: utf-8 -*-
"""Resource History Analysis Service.

Provides functions for querying historical equipment performance data including:
- Filter options (workcenters, families)
- Summary data (KPI, trend, heatmap, workcenter comparison)
- Hierarchical detail data (workcenter → family → resource)
- CSV export with streaming

Architecture:
- Uses resource_cache as the single source of truth for equipment master data
- Queries DW_MES_RESOURCESTATUS_SHIFT only for valid cached resource IDs
- Merges dimension data (WORKCENTERNAME, RESOURCEFAMILYNAME, etc.) from cache
"""

import io
import csv
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Dict, List, Any, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df

logger = logging.getLogger('mes_dashboard.resource_history')

# Maximum allowed query range in days
MAX_QUERY_DAYS = 730

# E10 Status definitions
E10_STATUSES = ['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST']


# ============================================================
# Resource Cache Integration
# ============================================================

def _get_filtered_resources(
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> List[Dict[str, Any]]:
    """Get filtered resources from resource_cache.

    Applies additional filters on top of the cache's pre-applied global filters.

    Args:
        workcenter_groups: Optional list of WORKCENTER_GROUP names
        families: Optional list of RESOURCEFAMILYNAME values
        is_production: Filter by production flag
        is_key: Filter by key equipment flag
        is_monitor: Filter by monitor flag

    Returns:
        List of resource dicts matching the filters.
    """
    from mes_dashboard.services.resource_cache import get_all_resources
    from mes_dashboard.services.filter_cache import get_workcenter_mapping

    resources = get_all_resources()
    if not resources:
        logger.warning("No resources available from cache")
        return []

    # Get workcenter mapping for group filtering
    wc_mapping = get_workcenter_mapping() or {}

    # Build set of workcenters if filtering by groups
    allowed_workcenters = None
    if workcenter_groups:
        allowed_workcenters = set()
        for wc_name, info in wc_mapping.items():
            if info.get('group') in workcenter_groups:
                allowed_workcenters.add(wc_name)

    # Apply filters
    filtered = []
    for r in resources:
        # Workcenter group filter
        if allowed_workcenters is not None:
            if r.get('WORKCENTERNAME') not in allowed_workcenters:
                continue

        # Family filter
        if families and r.get('RESOURCEFAMILYNAME') not in families:
            continue

        # Equipment flags filter
        if is_production and r.get('PJ_ISPRODUCTION') != 1:
            continue
        if is_key and r.get('PJ_ISKEY') != 1:
            continue
        if is_monitor and r.get('PJ_ISMONITOR') != 1:
            continue

        filtered.append(r)

    logger.debug(f"Filtered {len(resources)} resources to {len(filtered)}")
    return filtered


def _build_resource_lookup(resources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build a lookup dict from RESOURCEID to resource info.

    Args:
        resources: List of resource dicts from cache.

    Returns:
        Dict mapping RESOURCEID to resource dict.
    """
    return {r['RESOURCEID']: r for r in resources if r.get('RESOURCEID')}


def _get_resource_ids_sql_list(resources: List[Dict[str, Any]], max_chunk_size: int = 1000) -> List[str]:
    """Build SQL IN clause lists for resource IDs.

    Oracle has a limit of ~1000 items per IN clause, so we chunk if needed.

    Args:
        resources: List of resource dicts.
        max_chunk_size: Maximum items per IN clause.

    Returns:
        List of SQL IN clause strings (e.g., "'ID1', 'ID2', 'ID3'").
    """
    resource_ids = [r['RESOURCEID'] for r in resources if r.get('RESOURCEID')]
    if not resource_ids:
        return []

    # Escape single quotes
    escaped_ids = [rid.replace("'", "''") for rid in resource_ids]

    # Chunk into groups
    chunks = []
    for i in range(0, len(escaped_ids), max_chunk_size):
        chunk = escaped_ids[i:i + max_chunk_size]
        chunks.append("'" + "', '".join(chunk) + "'")

    return chunks


def _build_historyid_filter(resources: List[Dict[str, Any]]) -> str:
    """Build SQL WHERE clause for HISTORYID filtering.

    Handles chunking for large resource lists.

    Args:
        resources: List of resource dicts.

    Returns:
        SQL condition string (e.g., "HISTORYID IN ('ID1', 'ID2') OR HISTORYID IN ('ID3', 'ID4')").
    """
    chunks = _get_resource_ids_sql_list(resources)
    if not chunks:
        return "1=0"  # No resources = no results

    if len(chunks) == 1:
        return f"HISTORYID IN ({chunks[0]})"

    # Multiple chunks need OR
    conditions = [f"HISTORYID IN ({chunk})" for chunk in chunks]
    return "(" + " OR ".join(conditions) + ")"


# ============================================================
# Filter Options
# ============================================================

def get_filter_options() -> Optional[Dict[str, Any]]:
    """Get filter options from cache.

    Uses cached workcenter groups from DWH.DW_MES_LOT_V and resource families from resource_cache.

    Returns:
        Dict with:
        - 'workcenter_groups': List of {name, sequence} sorted by sequence
        - 'families': List of family names sorted alphabetically
        Or None if cache loading fails.
    """
    from mes_dashboard.services.filter_cache import get_workcenter_groups
    from mes_dashboard.services.resource_cache import get_resource_families

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

    Uses resource_cache as the source for equipment master data.
    Queries only DW_MES_RESOURCESTATUS_SHIFT for SHIFT data.

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
        # Get filtered resources from cache
        resources = _get_filtered_resources(
            workcenter_groups=workcenter_groups,
            families=families,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not resources:
            logger.warning("No resources match the filter criteria")
            return {
                'kpi': _build_kpi_from_df(pd.DataFrame()),
                'trend': [],
                'heatmap': [],
                'workcenter_comparison': []
            }

        # Build resource lookup for dimension merging
        resource_lookup = _build_resource_lookup(resources)
        historyid_filter = _build_historyid_filter(resources)

        # Build SQL components
        date_trunc = _get_date_trunc(granularity)

        # Base CTE with resource filter
        base_cte = f"""
            WITH shift_data AS (
                SELECT /*+ MATERIALIZE */ HISTORYID, TXNDATE, OLDSTATUSNAME, HOURS
                FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
                WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
                  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
                  AND {historyid_filter}
            )
        """

        # KPI query - aggregate all
        kpi_sql = f"""
            {base_cte}
            SELECT
                SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) as NST_HOURS,
                COUNT(DISTINCT HISTORYID) as MACHINE_COUNT
            FROM shift_data
        """

        # Trend query - group by date
        trend_sql = f"""
            {base_cte}
            SELECT
                {date_trunc} as DATA_DATE,
                SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) as NST_HOURS,
                COUNT(DISTINCT HISTORYID) as MACHINE_COUNT
            FROM shift_data
            GROUP BY {date_trunc}
            ORDER BY DATA_DATE
        """

        # Heatmap/Comparison query - group by HISTORYID and date, merge dimension in Python
        heatmap_raw_sql = f"""
            {base_cte}
            SELECT
                HISTORYID,
                {date_trunc} as DATA_DATE,
                SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) as EGT_HOURS
            FROM shift_data
            GROUP BY HISTORYID, {date_trunc}
            ORDER BY HISTORYID, DATA_DATE
        """

        # Execute queries in parallel
        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(read_sql_df, kpi_sql): 'kpi',
                executor.submit(read_sql_df, trend_sql): 'trend',
                executor.submit(read_sql_df, heatmap_raw_sql): 'heatmap_raw',
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

        # Build heatmap and comparison from raw data with dimension merge
        heatmap_raw_df = results.get('heatmap_raw', pd.DataFrame())
        heatmap = _build_heatmap_from_raw_df(heatmap_raw_df, resource_lookup, granularity)
        workcenter_comparison = _build_comparison_from_raw_df(heatmap_raw_df, resource_lookup)

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

    Uses resource_cache as the source for equipment master data.
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
        # Get filtered resources from cache
        resources = _get_filtered_resources(
            workcenter_groups=workcenter_groups,
            families=families,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not resources:
            logger.warning("No resources match the filter criteria")
            return {
                'data': [],
                'total': 0,
                'truncated': False,
                'max_records': None
            }

        # Build resource lookup for dimension merging
        resource_lookup = _build_resource_lookup(resources)
        historyid_filter = _build_historyid_filter(resources)

        # Query SHIFT data grouped by HISTORYID
        detail_sql = f"""
            WITH shift_data AS (
                SELECT /*+ MATERIALIZE */ HISTORYID, OLDSTATUSNAME, HOURS
                FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
                WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
                  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
                  AND {historyid_filter}
            )
            SELECT
                HISTORYID,
                SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) as NST_HOURS,
                SUM(HOURS) as TOTAL_HOURS
            FROM shift_data
            GROUP BY HISTORYID
            ORDER BY HISTORYID
        """

        detail_df = read_sql_df(detail_sql)

        # Build detail data with dimension merge from cache
        data = _build_detail_from_raw_df(detail_df, resource_lookup)
        total = len(data)

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

    Uses resource_cache as the source for equipment master data.
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
        # Get filtered resources from cache
        resources = _get_filtered_resources(
            workcenter_groups=workcenter_groups,
            families=families,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not resources:
            yield "Error: No resources match the filter criteria\n"
            return

        # Build resource lookup for dimension merging
        resource_lookup = _build_resource_lookup(resources)
        historyid_filter = _build_historyid_filter(resources)

        # Get workcenter mapping for WORKCENTER_GROUP
        from mes_dashboard.services.filter_cache import get_workcenter_mapping
        wc_mapping = get_workcenter_mapping() or {}

        # Query SHIFT data grouped by HISTORYID
        sql = f"""
            WITH shift_data AS (
                SELECT /*+ MATERIALIZE */ HISTORYID, OLDSTATUSNAME, HOURS
                FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
                WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
                  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
                  AND {historyid_filter}
            )
            SELECT
                HISTORYID,
                SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) as EGT_HOURS,
                SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) as NST_HOURS,
                SUM(HOURS) as TOTAL_HOURS
            FROM shift_data
            GROUP BY HISTORYID
            ORDER BY HISTORYID
        """
        df = read_sql_df(sql)

        # Write CSV header
        output = io.StringIO()
        writer = csv.writer(output)
        headers = [
            '站點', '型號', '機台', 'OU%', 'Availability%',
            'PRD(h)', 'PRD(%)', 'SBY(h)', 'SBY(%)',
            'UDT(h)', 'UDT(%)', 'SDT(h)', 'SDT(%)',
            'EGT(h)', 'EGT(%)', 'NST(h)', 'NST(%)'
        ]
        writer.writerow(headers)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)

        # Write data rows
        if df is not None:
            for _, row in df.iterrows():
                historyid = row['HISTORYID']
                resource_info = resource_lookup.get(historyid, {})

                # Skip if no resource info found
                if not resource_info:
                    continue

                prd = float(row['PRD_HOURS'] or 0)
                sby = float(row['SBY_HOURS'] or 0)
                udt = float(row['UDT_HOURS'] or 0)
                sdt = float(row['SDT_HOURS'] or 0)
                egt = float(row['EGT_HOURS'] or 0)
                nst = float(row['NST_HOURS'] or 0)
                total = float(row['TOTAL_HOURS'] or 0)

                # Get dimension data from cache
                wc_name = resource_info.get('WORKCENTERNAME', '')
                wc_info = wc_mapping.get(wc_name, {})
                wc_group = wc_info.get('group', wc_name)
                family = resource_info.get('RESOURCEFAMILYNAME', '')
                resource_name = resource_info.get('RESOURCENAME', '')

                # Calculate percentages
                ou_pct = _calc_ou_pct(prd, sby, udt, sdt, egt)
                availability_pct = _calc_availability_pct(prd, sby, udt, sdt, egt, nst)
                prd_pct = round(prd / total * 100, 1) if total > 0 else 0
                sby_pct = round(sby / total * 100, 1) if total > 0 else 0
                udt_pct = round(udt / total * 100, 1) if total > 0 else 0
                sdt_pct = round(sdt / total * 100, 1) if total > 0 else 0
                egt_pct = round(egt / total * 100, 1) if total > 0 else 0
                nst_pct = round(nst / total * 100, 1) if total > 0 else 0

                csv_row = [
                    wc_group,
                    family,
                    resource_name,
                    f"{ou_pct}%",
                    f"{availability_pct}%",
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
    """Get Oracle TRUNC expression for date granularity.

    Note: Uses 'ss' as alias for shift_data CTE.
    """
    trunc_map = {
        'day': "TRUNC(TXNDATE)",
        'week': "TRUNC(TXNDATE, 'IW')",
        'month': "TRUNC(TXNDATE, 'MM')",
        'year': "TRUNC(TXNDATE, 'YYYY')"
    }
    return trunc_map.get(granularity, "TRUNC(TXNDATE)")


def _safe_float(value, default=0.0) -> float:
    """Safely convert value to float, handling NaN and None."""
    if value is None or pd.isna(value):
        return default
    return float(value)


def _calc_ou_pct(prd: float, sby: float, udt: float, sdt: float, egt: float) -> float:
    """Calculate OU% = PRD / (PRD + SBY + UDT + SDT + EGT) * 100."""
    denominator = prd + sby + udt + sdt + egt
    return round(prd / denominator * 100, 1) if denominator > 0 else 0


def _calc_availability_pct(prd: float, sby: float, udt: float, sdt: float, egt: float, nst: float) -> float:
    """Calculate Availability% = (PRD + SBY + EGT) / (PRD + SBY + EGT + SDT + UDT + NST) * 100."""
    numerator = prd + sby + egt
    denominator = prd + sby + egt + sdt + udt + nst
    return round(numerator / denominator * 100, 1) if denominator > 0 else 0


def _build_kpi_from_df(df: pd.DataFrame) -> Dict[str, Any]:
    """Build KPI dict from query result DataFrame."""
    if df is None or len(df) == 0:
        return {
            'ou_pct': 0,
            'availability_pct': 0,
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
        'availability_pct': _calc_availability_pct(prd, sby, udt, sdt, egt, nst),
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
            'availability_pct': _calc_availability_pct(prd, sby, udt, sdt, egt, nst),
            'prd_hours': round(prd, 1),
            'sby_hours': round(sby, 1),
            'udt_hours': round(udt, 1),
            'sdt_hours': round(sdt, 1),
            'egt_hours': round(egt, 1),
            'nst_hours': round(nst, 1)
        })

    return result


def _build_heatmap_from_raw_df(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]],
    granularity: str
) -> List[Dict]:
    """Build heatmap data from raw SHIFT query grouped by HISTORYID.

    Merges dimension data from resource_lookup.

    Args:
        df: DataFrame with HISTORYID, DATA_DATE, and status hours.
        resource_lookup: Dict mapping RESOURCEID to resource info.
        granularity: Time granularity for date formatting.

    Returns:
        List of heatmap data dicts.
    """
    if df is None or len(df) == 0:
        return []

    # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    wc_mapping = get_workcenter_mapping() or {}

    # Aggregate data by WORKCENTER_GROUP and date
    aggregated = {}
    for _, row in df.iterrows():
        historyid = row['HISTORYID']
        resource_info = resource_lookup.get(historyid, {})

        # Skip if no resource info
        if not resource_info:
            continue

        wc_name = resource_info.get('WORKCENTERNAME', '')
        if not wc_name:
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


def _build_comparison_from_raw_df(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]]
) -> List[Dict]:
    """Build workcenter comparison data from raw SHIFT query grouped by HISTORYID.

    Merges dimension data from resource_lookup.

    Args:
        df: DataFrame with HISTORYID and status hours (may have DATA_DATE if from heatmap query).
        resource_lookup: Dict mapping RESOURCEID to resource info.

    Returns:
        List of comparison data dicts.
    """
    if df is None or len(df) == 0:
        return []

    # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    wc_mapping = get_workcenter_mapping() or {}

    # First aggregate by HISTORYID (in case df is by HISTORYID + date)
    by_resource = {}
    for _, row in df.iterrows():
        historyid = row['HISTORYID']
        if historyid not in by_resource:
            by_resource[historyid] = {'prd': 0, 'sby': 0, 'udt': 0, 'sdt': 0, 'egt': 0}

        by_resource[historyid]['prd'] += _safe_float(row['PRD_HOURS'])
        by_resource[historyid]['sby'] += _safe_float(row['SBY_HOURS'])
        by_resource[historyid]['udt'] += _safe_float(row['UDT_HOURS'])
        by_resource[historyid]['sdt'] += _safe_float(row['SDT_HOURS'])
        by_resource[historyid]['egt'] += _safe_float(row['EGT_HOURS'])

    # Then aggregate by WORKCENTER_GROUP
    aggregated = {}
    for historyid, hours in by_resource.items():
        resource_info = resource_lookup.get(historyid, {})

        # Skip if no resource info
        if not resource_info:
            continue

        wc_name = resource_info.get('WORKCENTERNAME', '')
        if not wc_name:
            continue

        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get('group', wc_name)

        if wc_group not in aggregated:
            aggregated[wc_group] = {'prd': 0, 'sby': 0, 'udt': 0, 'sdt': 0, 'egt': 0, 'machine_count': 0}

        aggregated[wc_group]['prd'] += hours['prd']
        aggregated[wc_group]['sby'] += hours['sby']
        aggregated[wc_group]['udt'] += hours['udt']
        aggregated[wc_group]['sdt'] += hours['sdt']
        aggregated[wc_group]['egt'] += hours['egt']
        aggregated[wc_group]['machine_count'] += 1

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


def _build_detail_from_raw_df(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]]
) -> List[Dict]:
    """Build detail data from raw SHIFT query grouped by HISTORYID.

    Merges dimension data from resource_lookup.

    Args:
        df: DataFrame with HISTORYID and status hours.
        resource_lookup: Dict mapping RESOURCEID to resource info.

    Returns:
        List of detail data dicts.
    """
    if df is None or len(df) == 0:
        return []

    # Get workcenter mapping to convert WORKCENTERNAME to WORKCENTER_GROUP
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    wc_mapping = get_workcenter_mapping() or {}

    result = []
    for _, row in df.iterrows():
        historyid = row['HISTORYID']
        resource_info = resource_lookup.get(historyid, {})

        # Skip if no resource info
        if not resource_info:
            continue

        prd = _safe_float(row['PRD_HOURS'])
        sby = _safe_float(row['SBY_HOURS'])
        udt = _safe_float(row['UDT_HOURS'])
        sdt = _safe_float(row['SDT_HOURS'])
        egt = _safe_float(row['EGT_HOURS'])
        nst = _safe_float(row['NST_HOURS'])
        total = _safe_float(row['TOTAL_HOURS'])

        # Get dimension data from cache
        wc_name = resource_info.get('WORKCENTERNAME', '')
        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get('group', wc_name)  # Fallback to workcentername if no mapping
        family = resource_info.get('RESOURCEFAMILYNAME', '')
        resource_name = resource_info.get('RESOURCENAME', '')

        result.append({
            'workcenter': wc_group,
            'family': family or '',
            'resource': resource_name or '',
            'ou_pct': _calc_ou_pct(prd, sby, udt, sdt, egt),
            'availability_pct': _calc_availability_pct(prd, sby, udt, sdt, egt, nst),
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

    # Sort by workcenter, family, resource
    result.sort(key=lambda x: (x['workcenter'], x['family'], x['resource']))
    return result
