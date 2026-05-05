# -*- coding: utf-8 -*-
"""Resource (Equipment) query services for MES Dashboard.

Provides functions to query equipment status from DWH.DW_MES_RESOURCE and DWH.DW_MES_RESOURCESTATUS tables.
"""

import logging
import os
import pandas as pd
from typing import Optional, Dict, List, Any

logger = logging.getLogger('mes_dashboard.resource_service')

from mes_dashboard.core.database import (
    read_sql_df,
    DatabasePoolExhaustedError,
    DatabaseCircuitOpenError,
)
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    STATUS_CATEGORIES,
)
from mes_dashboard.sql import SQLLoader, QueryBuilder
from mes_dashboard.sql.filters import CommonFilters
from mes_dashboard.services.resource_cache import get_all_resources
from mes_dashboard.services.realtime_equipment_cache import (
    get_all_equipment_status,
    get_equipment_status_lookup,
)
from mes_dashboard.services.filter_cache import (
    get_workcenter_group,
    get_workcenter_group_sequence,
    get_workcenter_short,
    get_workcenter_groups,
)


# ============================================================
# Helper Functions
# ============================================================


def _is_valid_value(value) -> bool:
    """Check if a value is valid (not None, not NaN, not empty string).

    Args:
        value: The value to check.

    Returns:
        True if valid, False otherwise.
    """
    if value is None:
        return False
    if isinstance(value, str) and (not value.strip() or value == 'NaT'):
        return False
    # Check for NaN (pandas NaN or float NaN)
    try:
        if value != value:  # NaN != NaN is True
            return False
    except (TypeError, ValueError):
        pass
    return True


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

    return SQLLoader.load_with_params(
        "resource/latest_status",
        days_back=days_back,
        LOCATION_FILTER=location_filter,
        ASSET_STATUS_FILTER=asset_status_filter,
    )


# ============================================================
# Resource Summary Queries
# ============================================================

def query_resource_by_status(days_back: int = 30) -> Optional[pd.DataFrame]:
    """Query resource count grouped by status.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with status counts or None if query fails.
    """
    try:
        base_sql = get_resource_latest_status_subquery(days_back)
        sql = SQLLoader.load("resource/by_status")
        sql = sql.replace("{{ LATEST_STATUS_SUBQUERY }}", base_sql)
        return read_sql_df(sql)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Resource by status query failed: {exc}")
        return None


def query_resource_by_workcenter(days_back: int = 30) -> Optional[pd.DataFrame]:
    """Query resource count grouped by workcenter and status.

    Args:
        days_back: Number of days to look back

    Returns:
        DataFrame with workcenter/status counts or None if query fails.
    """
    try:
        base_sql = get_resource_latest_status_subquery(days_back)
        sql = SQLLoader.load("resource/by_workcenter")
        sql = sql.replace("{{ LATEST_STATUS_SUBQUERY }}", base_sql)
        return read_sql_df(sql)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Resource by workcenter query failed: {exc}")
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
        try:
            max_limit = max(int(os.getenv("RESOURCE_DETAIL_MAX_LIMIT", "500")), 1)
        except (TypeError, ValueError):
            max_limit = 500
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 500
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            offset = 0

        limit = max(1, min(limit, max_limit))
        offset = max(offset, 0)

        base_sql = get_resource_latest_status_subquery(days_back)

        # Use QueryBuilder for safe parameterized conditions
        builder = QueryBuilder()
        if filters:
            if filters.get('workcenter'):
                builder.add_param_condition('WORKCENTERNAME', filters['workcenter'])
            if filters.get('status'):
                builder.add_param_condition('NEWSTATUSNAME', filters['status'])
            if filters.get('family'):
                builder.add_param_condition('RESOURCEFAMILYNAME', filters['family'])
            if filters.get('department'):
                builder.add_param_condition('PJ_DEPARTMENT', filters['department'])

            # Equipment flag filters (boolean to 0/1)
            if filters.get('isProduction') is not None:
                builder.add_condition(
                    f"NVL(PJ_ISPRODUCTION, 0) = {1 if filters['isProduction'] else 0}"
                )
            if filters.get('isKey') is not None:
                builder.add_condition(
                    f"NVL(PJ_ISKEY, 0) = {1 if filters['isKey'] else 0}"
                )
            if filters.get('isMonitor') is not None:
                builder.add_condition(
                    f"NVL(PJ_ISMONITOR, 0) = {1 if filters['isMonitor'] else 0}"
                )

        # Build WHERE clause and get parameters
        conditions_sql = builder.get_conditions_sql()
        params = builder.params.copy()

        # Add pagination parameters
        start_row = offset + 1
        end_row = offset + limit
        params['start_row'] = start_row
        params['end_row'] = end_row

        where_clause = f" AND {conditions_sql}" if conditions_sql else ""

        # Load SQL from file and replace placeholders
        sql = SQLLoader.load("resource/detail")
        sql = sql.replace("{{ LATEST_STATUS_SUBQUERY }}", base_sql)
        sql = sql.replace("{{ WHERE_CLAUSE }}", where_clause)

        df = read_sql_df(sql, params)

        # Convert datetime to string
        if 'LASTSTATUSCHANGEDATE' in df.columns:
            df['LASTSTATUSCHANGEDATE'] = df['LASTSTATUSCHANGEDATE'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else None
            )

        return df
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Resource detail query failed: {exc}")
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
        base_sql = get_resource_latest_status_subquery(days_back)
        sql = SQLLoader.load("resource/workcenter_status_matrix")
        sql = sql.replace("{{ LATEST_STATUS_SUBQUERY }}", base_sql)
        return read_sql_df(sql)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Resource status matrix query failed: {exc}")
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

        # Use STATUS_CATEGORIES constant — status values are fixed, no Oracle query needed
        statuses = list(STATUS_CATEGORIES)

        return {
            'workcenters': workcenters,
            'statuses': statuses,
            'families': families,
            'departments': departments,
            'locations': locations,
            'assets_statuses': assets_statuses
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Resource filter options query failed: {exc}", exc_info=True)
        return None


def get_resource_status_values(days_back: int = 30) -> List[Dict[str, Any]]:
    """Get distinct status values with counts from DWH.DW_MES_RESOURCESTATUS.

    Uses main pool (read_sql_df) instead of a direct connection.

    Returns:
        List of {'status': str, 'count': int} dicts ordered by count desc.
    """
    sql = """
        SELECT DISTINCT NEWSTATUSNAME, COUNT(*) as CNT
        FROM DWH.DW_MES_RESOURCESTATUS
        WHERE NEWSTATUSNAME IS NOT NULL
          AND LASTSTATUSCHANGEDATE >= SYSDATE - :days_back
        GROUP BY NEWSTATUSNAME
        ORDER BY CNT DESC
    """
    try:
        df = read_sql_df(sql, {'days_back': days_back}, caller="resource_service:status_values")
        if df is None or df.empty:
            return []
        return [
            {'status': str(row['NEWSTATUSNAME']), 'count': int(row['CNT'])}
            for _, row in df.iterrows()
        ]
    except Exception as exc:
        logger.error("get_resource_status_values failed: %s", exc, exc_info=True)
        raise


# ============================================================
# Merged Resource Status Query (Three-Layer Cache)
# ============================================================

def get_merged_resource_status(
    workcenter_groups: Optional[List[str]] = None,
    is_production: Optional[bool] = None,
    is_key: Optional[bool] = None,
    is_monitor: Optional[bool] = None,
    status_categories: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get merged resource status from three cache layers.

    Combines:
    - resource-cache: Equipment master data (RESOURCENAME, WORKCENTERNAME, etc.)
    - realtime-equipment-cache: Real-time status (EQUIPMENTASSETSSTATUS, JOBORDER, etc.)
    - workcenter-mapping: WORKCENTER_GROUP, WORKCENTER_SHORT

    Args:
        workcenter_groups: Filter by WORKCENTER_GROUP (e.g., ['焊接', '成型'])
        is_production: Filter by PJ_ISPRODUCTION flag
        is_key: Filter by PJ_ISKEY flag
        is_monitor: Filter by PJ_ISMONITOR flag
        status_categories: Filter by STATUS_CATEGORY (e.g., ['PRODUCTIVE', 'DOWN'])

    Returns:
        List of merged equipment status records.
    """
    import logging
    logger = logging.getLogger('mes_dashboard.resource_service')

    # Resource master data is served from full-table cache.
    resources = get_all_resources()
    if not resources:
        logger.warning("No resources from resource-cache")
        return []

    # Get realtime status from cache
    status_lookup = get_equipment_status_lookup()
    if not status_lookup:
        equipment_status = get_all_equipment_status()
        status_lookup = {
            str(row.get('RESOURCEID')): row
            for row in equipment_status
            if row.get('RESOURCEID') is not None
        }

    # Precompute workcenter mapping once per unique workcenter to avoid repetitive lookups.
    wc_names = {
        row.get('WORKCENTERNAME')
        for row in resources
        if row.get('WORKCENTERNAME')
    }
    wc_group_map = {name: get_workcenter_group(name) for name in wc_names}
    wc_group_seq_map = {name: get_workcenter_group_sequence(name) for name in wc_names}
    wc_short_map = {name: get_workcenter_short(name) for name in wc_names}

    # Merge data
    merged = []
    for resource in resources:
        resource_id = resource.get('RESOURCEID')
        workcenter_name = resource.get('WORKCENTERNAME')
        resource_key = str(resource_id) if resource_id is not None else None
        realtime = status_lookup.get(resource_key, {}) if resource_key else {}

        wc_group = wc_group_map.get(workcenter_name) if workcenter_name else None
        wc_group_seq = wc_group_seq_map.get(workcenter_name) if workcenter_name else None
        wc_short = wc_short_map.get(workcenter_name) if workcenter_name else None

        # Apply filters before creating merged payload.
        if workcenter_groups and wc_group not in workcenter_groups:
            continue
        if is_production is not None and bool(resource.get('PJ_ISPRODUCTION')) != is_production:
            continue
        if is_key is not None and bool(resource.get('PJ_ISKEY')) != is_key:
            continue
        if is_monitor is not None and bool(resource.get('PJ_ISMONITOR')) != is_monitor:
            continue
        if families and resource.get('RESOURCEFAMILYNAME') not in families:
            continue
        if resource_ids and str(resource_id) not in resource_ids:
            continue
        if status_categories and realtime.get('STATUS_CATEGORY') not in status_categories:
            continue

        # Build merged record
        record = {
            # From resource-cache
            'RESOURCEID': resource_id,
            'RESOURCENAME': resource.get('RESOURCENAME'),
            'WORKCENTERNAME': workcenter_name,
            'RESOURCEFAMILYNAME': resource.get('RESOURCEFAMILYNAME'),
            'PJ_DEPARTMENT': resource.get('PJ_DEPARTMENT'),
            'PJ_ASSETSSTATUS': resource.get('PJ_ASSETSSTATUS'),
            'PJ_ISPRODUCTION': resource.get('PJ_ISPRODUCTION'),
            'PJ_ISKEY': resource.get('PJ_ISKEY'),
            'PJ_ISMONITOR': resource.get('PJ_ISMONITOR'),
            'VENDORNAME': resource.get('VENDORNAME'),
            'VENDORMODEL': resource.get('VENDORMODEL'),
            'LOCATIONNAME': resource.get('LOCATIONNAME'),
            # From workcenter-mapping
            'WORKCENTER_GROUP': wc_group,
            'WORKCENTER_GROUP_SEQ': wc_group_seq,
            'WORKCENTER_SHORT': wc_short,
            # From realtime-equipment-cache
            'EQUIPMENTASSETSSTATUS': realtime.get('EQUIPMENTASSETSSTATUS'),
            'EQUIPMENTASSETSSTATUSREASON': realtime.get('EQUIPMENTASSETSSTATUSREASON'),
            'STATUS_CATEGORY': realtime.get('STATUS_CATEGORY'),
            # JOB related fields
            'JOBORDER': realtime.get('JOBORDER'),
            'JOBMODEL': realtime.get('JOBMODEL'),
            'JOBSTAGE': realtime.get('JOBSTAGE'),
            'JOBID': realtime.get('JOBID'),
            'JOBSTATUS': realtime.get('JOBSTATUS'),
            'CREATEDATE': realtime.get('CREATEDATE'),
            'CREATEUSERNAME': realtime.get('CREATEUSERNAME'),
            'CREATEUSER': realtime.get('CREATEUSER'),
            'TECHNICIANUSERNAME': realtime.get('TECHNICIANUSERNAME'),
            'TECHNICIANUSER': realtime.get('TECHNICIANUSER'),
            'SYMPTOMCODE': realtime.get('SYMPTOMCODE'),
            'CAUSECODE': realtime.get('CAUSECODE'),
            'REPAIRCODE': realtime.get('REPAIRCODE'),
            # LOT related fields
            'LOT_COUNT': realtime.get('LOT_COUNT'),
            'LOT_DETAILS': realtime.get('LOT_DETAILS'),
            'TOTAL_TRACKIN_QTY': realtime.get('TOTAL_TRACKIN_QTY'),
            'LATEST_TRACKIN_TIME': realtime.get('LATEST_TRACKIN_TIME'),
        }

        merged.append(record)

    logger.debug(f"Merged {len(merged)} resource status records")
    return merged


def get_resource_status_summary(
    workcenter_groups: Optional[List[str]] = None,
    is_production: Optional[bool] = None,
    is_key: Optional[bool] = None,
    is_monitor: Optional[bool] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get resource status summary statistics.

    Args:
        workcenter_groups: Filter by WORKCENTER_GROUP
        is_production: Filter by PJ_ISPRODUCTION flag
        is_key: Filter by PJ_ISKEY flag
        is_monitor: Filter by PJ_ISMONITOR flag
        families: Filter by RESOURCEFAMILYNAME
        resource_ids: Filter by RESOURCEID

    Returns:
        Dict with summary statistics including OU%, Availability%, and per-status counts.
    """
    # Get merged data with filters (except status_categories)
    data = get_merged_resource_status(
        workcenter_groups=workcenter_groups,
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
        families=families,
        resource_ids=resource_ids,
    )

    if not data:
        return {
            'total_count': 0,
            'by_status_category': {},
            'by_status': {},
            'by_workcenter_group': {},
            'with_active_job': 0,
            'with_wip': 0,
            'ou_pct': 0,
            'availability_pct': 0,
        }

    # Count by status category (for backward compatibility)
    by_status_category = {}
    for record in data:
        cat = record.get('STATUS_CATEGORY') or 'UNKNOWN'
        by_status_category[cat] = by_status_category.get(cat, 0) + 1

    # Count by individual E10 status (PRD, SBY, UDT, SDT, EGT, NST)
    by_status = {'PRD': 0, 'SBY': 0, 'UDT': 0, 'SDT': 0, 'EGT': 0, 'NST': 0, 'OTHER': 0}
    for record in data:
        status = record.get('EQUIPMENTASSETSSTATUS') or 'UNKNOWN'
        if status in by_status:
            by_status[status] += 1
        else:
            by_status['OTHER'] += 1

    # Count by workcenter group
    by_workcenter_group = {}
    for record in data:
        group = record.get('WORKCENTER_GROUP') or 'UNKNOWN'
        by_workcenter_group[group] = by_workcenter_group.get(group, 0) + 1

    # Count with active job (use _is_valid_value to exclude NaN/None/empty)
    with_active_job = sum(1 for r in data if _is_valid_value(r.get('JOBORDER')))

    # Count with WIP
    with_wip = sum(1 for r in data if (r.get('LOT_COUNT') or 0) > 0)

    # Calculate OU% = PRD / (PRD + SBY + UDT + SDT + EGT) * 100
    prd = by_status['PRD']
    sby = by_status['SBY']
    udt = by_status['UDT']
    sdt = by_status['SDT']
    egt = by_status['EGT']
    _nst = by_status['NST']

    ou_denominator = prd + sby + udt + sdt + egt
    ou_pct = round(prd / ou_denominator * 100, 1) if ou_denominator > 0 else 0

    # Calculate Availability% = (PRD + SBY + EGT) / total * 100
    total_count = len(data)
    availability_pct = round((prd + sby + egt) / total_count * 100, 1) if total_count > 0 else 0

    return {
        'total_count': total_count,
        'by_status_category': by_status_category,
        'by_status': by_status,
        'by_workcenter_group': by_workcenter_group,
        'with_active_job': with_active_job,
        'with_wip': with_wip,
        'ou_pct': ou_pct,
        'availability_pct': availability_pct,
    }


def get_workcenter_status_matrix(
    is_production: Optional[bool] = None,
    is_key: Optional[bool] = None,
    is_monitor: Optional[bool] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get workcenter × status matrix.

    Returns count of equipment by workcenter group and status.

    Args:
        is_production: Filter by PJ_ISPRODUCTION flag
        is_key: Filter by PJ_ISKEY flag
        is_monitor: Filter by PJ_ISMONITOR flag
        families: Filter by RESOURCEFAMILYNAME
        resource_ids: Filter by RESOURCEID

    Returns:
        List of dicts with workcenter_group and status counts.
    """
    # Get merged data
    data = get_merged_resource_status(
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
        families=families,
        resource_ids=resource_ids,
    )

    if not data:
        return []

    # Get all workcenter groups with sequence
    all_groups = get_workcenter_groups() or []
    group_sequence = {g['name']: g['sequence'] for g in all_groups}

    # Build matrix
    matrix = {}
    for record in data:
        group = record.get('WORKCENTER_GROUP') or 'UNKNOWN'
        status = record.get('EQUIPMENTASSETSSTATUS') or 'UNKNOWN'

        if group not in matrix:
            matrix[group] = {
                'workcenter_group': group,
                'workcenter_sequence': group_sequence.get(group, 999),
                'total': 0,
                'PRD': 0,
                'SBY': 0,
                'UDT': 0,
                'SDT': 0,
                'EGT': 0,
                'NST': 0,
                'OTHER': 0,
            }

        matrix[group]['total'] += 1

        # Categorize status
        if status in ('PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST'):
            matrix[group][status] += 1
        else:
            matrix[group]['OTHER'] += 1

    # Convert to list and sort by sequence
    result = list(matrix.values())
    result.sort(key=lambda x: x['workcenter_sequence'])

    return result
