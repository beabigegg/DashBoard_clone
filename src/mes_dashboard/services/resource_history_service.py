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
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List, Any, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.sql import SQLLoader
from mes_dashboard.config.field_contracts import get_export_headers, get_export_api_keys
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
    resource_ids: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> List[Dict[str, Any]]:
    """Get filtered resources from resource_cache.

    Applies additional filters on top of the cache's pre-applied global filters.

    Args:
        workcenter_groups: Optional list of WORKCENTER_GROUP names
        families: Optional list of RESOURCEFAMILYNAME values
        resource_ids: Optional list of RESOURCEID values
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

    resource_id_set = set(resource_ids) if resource_ids else None

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

        # Resource ID filter
        if resource_id_set and r.get('RESOURCEID') not in resource_id_set:
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
    from mes_dashboard.services.resource_cache import (
        get_resource_families,
        get_resource_cascade_metadata,
    )

    try:
        groups = get_workcenter_groups()
        families = get_resource_families()

        if groups is None or families is None:
            logger.error("Filter cache not available")
            return None

        return {
            'workcenter_groups': groups,
            'families': families,
            'resources': get_resource_cascade_metadata(),
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
    resource_ids: Optional[List[str]] = None,
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
            resource_ids=resource_ids,
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

        # Common parameters for all queries (dates are parameterized for safety)
        params = {'start_date': start_date, 'end_date': end_date}

        # Load SQL templates and replace placeholders
        kpi_sql = SQLLoader.load("resource_history/kpi")
        kpi_sql = kpi_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)

        trend_sql = SQLLoader.load("resource_history/trend")
        trend_sql = trend_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)
        trend_sql = trend_sql.replace("{{ DATE_TRUNC }}", date_trunc)

        heatmap_raw_sql = SQLLoader.load("resource_history/heatmap")
        heatmap_raw_sql = heatmap_raw_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)
        heatmap_raw_sql = heatmap_raw_sql.replace("{{ DATE_TRUNC }}", date_trunc)

        # Execute queries in parallel with params
        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(read_sql_df, kpi_sql, params): 'kpi',
                executor.submit(read_sql_df, trend_sql, params): 'trend',
                executor.submit(read_sql_df, heatmap_raw_sql, params): 'heatmap_raw',
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
    resource_ids: Optional[List[str]] = None,
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
            resource_ids=resource_ids,
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

        # Query SHIFT data grouped by HISTORYID (dates parameterized for safety)
        params = {'start_date': start_date, 'end_date': end_date}

        # Load SQL template and replace placeholder
        detail_sql = SQLLoader.load("resource_history/detail")
        detail_sql = detail_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)

        detail_df = read_sql_df(detail_sql, params)

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
    resource_ids: Optional[List[str]] = None,
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
            resource_ids=resource_ids,
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

        # Query SHIFT data grouped by HISTORYID (dates parameterized for safety)
        params = {'start_date': start_date, 'end_date': end_date}

        # Load SQL template and replace placeholder (reuse detail.sql)
        sql = SQLLoader.load("resource_history/detail")
        sql = sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)

        df = read_sql_df(sql, params)

        # Query OEE data for CSV export
        from datetime import timedelta as _td
        from datetime import date as _date
        oee_sql = SQLLoader.load("resource_history/oee_facts")
        _reject_start = (_date.fromisoformat(start_date) - _td(days=30)).isoformat()
        _reject_end = (_date.fromisoformat(end_date) + _td(days=30)).isoformat()
        oee_params = {
            'start_date': start_date,
            'end_date': end_date,
            'reject_start': _reject_start,
            'reject_end': _reject_end,
        }
        oee_df = read_sql_df(oee_sql, oee_params)
        oee_by_equipment = {}
        if oee_df is not None and not oee_df.empty:
            oee_grouped = oee_df.groupby('EQUIPMENTID', as_index=False).agg(
                TRACKOUT_QTY=('TRACKOUT_QTY', 'sum'),
                NG_QTY=('NG_QTY', 'sum'),
            )
            for _, orow in oee_grouped.iterrows():
                oee_by_equipment[orow['EQUIPMENTID']] = {
                    'trackout_qty': int(orow['TRACKOUT_QTY']),
                    'ng_qty': int(orow['NG_QTY']),
                }

        export_keys = get_export_api_keys('resource_history')
        headers = get_export_headers('resource_history')
        if not export_keys or not headers or len(export_keys) != len(headers):
            export_keys = [
                'workcenter',
                'family',
                'resource',
                'ou_pct',
                'oee_pct',
                'availability_pct',
                'yield_pct',
                'trackout_qty',
                'ng_qty',
                'prd_hours',
                'prd_pct',
                'sby_hours',
                'sby_pct',
                'udt_hours',
                'udt_pct',
                'sdt_hours',
                'sdt_pct',
                'egt_hours',
                'egt_pct',
                'nst_hours',
                'nst_pct',
            ]
            headers = [
                '站點', '型號', '機台', 'OU%', 'OEE%', 'Availability%',
                'Yield%', 'TRACKOUT_QTY', 'NG_QTY',
                'PRD(h)', 'PRD(%)', 'SBY(h)', 'SBY(%)',
                'UDT(h)', 'UDT(%)', 'SDT(h)', 'SDT(%)',
                'EGT(h)', 'EGT(%)', 'NST(h)', 'NST(%)'
            ]

        # Write CSV header
        output = io.StringIO()
        output.write('\ufeff')  # UTF-8 BOM for Excel compatibility
        writer = csv.writer(output)
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

                # OEE fields from parallel query
                oee_info = oee_by_equipment.get(historyid, {})
                trackout_qty = oee_info.get('trackout_qty', 0)
                ng_qty = oee_info.get('ng_qty', 0)
                oee_denom = trackout_qty + ng_qty
                yield_pct = round(trackout_qty / oee_denom * 100, 1) if oee_denom > 0 else 0
                oee_pct = round(availability_pct * yield_pct / 100, 1)

                value_map = {
                    'workcenter': wc_group,
                    'family': family,
                    'resource': resource_name,
                    'ou_pct': f"{ou_pct}%",
                    'oee_pct': f"{oee_pct}%",
                    'availability_pct': f"{availability_pct}%",
                    'yield_pct': f"{yield_pct}%",
                    'trackout_qty': trackout_qty,
                    'ng_qty': ng_qty,
                    'prd_hours': round(prd, 1),
                    'prd_pct': f"{prd_pct}%",
                    'sby_hours': round(sby, 1),
                    'sby_pct': f"{sby_pct}%",
                    'udt_hours': round(udt, 1),
                    'udt_pct': f"{udt_pct}%",
                    'sdt_hours': round(sdt, 1),
                    'sdt_pct': f"{sdt_pct}%",
                    'egt_hours': round(egt, 1),
                    'egt_pct': f"{egt_pct}%",
                    'nst_hours': round(nst, 1),
                    'nst_pct': f"{nst_pct}%",
                }
                csv_row = [value_map.get(key, '') for key in export_keys]
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


def _calc_status_pct(value: float, total: float) -> float:
    """Calculate status percentage = value / total * 100."""
    return round(value / total * 100, 1) if total > 0 else 0


def _build_kpi_from_df(df: pd.DataFrame) -> Dict[str, Any]:
    """Build KPI dict from query result DataFrame."""
    if df is None or len(df) == 0:
        return {
            'ou_pct': 0,
            'availability_pct': 0,
            'prd_hours': 0,
            'prd_pct': 0,
            'sby_hours': 0,
            'sby_pct': 0,
            'udt_hours': 0,
            'udt_pct': 0,
            'sdt_hours': 0,
            'sdt_pct': 0,
            'egt_hours': 0,
            'egt_pct': 0,
            'nst_hours': 0,
            'nst_pct': 0,
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

    # Total hours for percentage calculation (includes NST)
    total_hours = prd + sby + udt + sdt + egt + nst

    return {
        'ou_pct': _calc_ou_pct(prd, sby, udt, sdt, egt),
        'availability_pct': _calc_availability_pct(prd, sby, udt, sdt, egt, nst),
        'prd_hours': round(prd, 1),
        'prd_pct': _calc_status_pct(prd, total_hours),
        'sby_hours': round(sby, 1),
        'sby_pct': _calc_status_pct(sby, total_hours),
        'udt_hours': round(udt, 1),
        'udt_pct': _calc_status_pct(udt, total_hours),
        'sdt_hours': round(sdt, 1),
        'sdt_pct': _calc_status_pct(sdt, total_hours),
        'egt_hours': round(egt, 1),
        'egt_pct': _calc_status_pct(egt, total_hours),
        'nst_hours': round(nst, 1),
        'nst_pct': _calc_status_pct(nst, total_hours),
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
    # Track sequence for each workcenter group
    wc_seq_map = {}
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
        wc_seq = wc_info.get('sequence', 999)
        wc_seq_map[wc_group] = wc_seq  # Store sequence for this group
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
            'workcenter_seq': wc_seq_map.get(wc_group, 999),
            'date': date_str,
            'ou_pct': _calc_ou_pct(data['prd'], data['sby'], data['udt'], data['sdt'], data['egt'])
        })

    # Sort by workcenter sequence (ascending, smaller first) and date
    result.sort(key=lambda x: (x['workcenter_seq'], x['date'] or ''))
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
        wc_seq = wc_info.get('sequence', 999)  # Get sequence for sorting
        family = resource_info.get('RESOURCEFAMILYNAME', '')
        resource_name = resource_info.get('RESOURCENAME', '')

        result.append({
            'workcenter': wc_group,
            'workcenter_seq': wc_seq,
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

    # Sort by workcenter sequence (ascending, smaller first), then family, resource
    result.sort(key=lambda x: (x['workcenter_seq'], x['family'], x['resource']))
    return result


