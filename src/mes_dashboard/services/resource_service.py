# -*- coding: utf-8 -*-
"""Resource (Equipment) query services for MES Dashboard.

Provides functions to query equipment status from DWH.DW_MES_RESOURCE and DWH.DW_MES_RESOURCESTATUS tables.
"""

import logging
import pandas as pd
from typing import Optional, Dict, List, Any

logger = logging.getLogger('mes_dashboard.resource_service')

from mes_dashboard.core.database import get_db_connection, read_sql_df
from mes_dashboard.core.utils import get_days_back, build_equipment_filter_sql
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    DEFAULT_DAYS_BACK,
    STATUS_CATEGORIES,
)
from mes_dashboard.sql import SQLLoader, QueryBuilder
from mes_dashboard.sql.filters import CommonFilters
from mes_dashboard.services.resource_cache import get_all_resources
from mes_dashboard.services.realtime_equipment_cache import (
    get_all_equipment_status,
    get_equipment_status_by_id,
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

        # Query only dynamic status data from Oracle using SQLLoader
        sql_statuses = SQLLoader.load("resource/distinct_statuses")
        status_df = read_sql_df(sql_statuses, {'days_back': days_back})
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
        logger.error(f"Resource filter options query failed: {exc}", exc_info=True)
        return None


# ============================================================
# Merged Resource Status Query (Three-Layer Cache)
# ============================================================

def get_merged_resource_status(
    workcenter_groups: Optional[List[str]] = None,
    is_production: Optional[bool] = None,
    is_key: Optional[bool] = None,
    is_monitor: Optional[bool] = None,
    status_categories: Optional[List[str]] = None,
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

    # Get resource master data from cache
    resources = get_all_resources()
    if not resources:
        logger.warning("No resources from resource-cache")
        return []

    # Get realtime status from cache
    equipment_status = get_all_equipment_status()

    # Build status lookup by RESOURCEID
    status_lookup = {
        s['RESOURCEID']: s
        for s in equipment_status
    } if equipment_status else {}

    # Merge data
    merged = []
    for resource in resources:
        resource_id = resource.get('RESOURCEID')
        workcenter_name = resource.get('WORKCENTERNAME')

        # Get realtime status
        realtime = status_lookup.get(resource_id, {})

        # Get workcenter mapping
        wc_group = get_workcenter_group(workcenter_name) if workcenter_name else None
        wc_group_seq = get_workcenter_group_sequence(workcenter_name) if workcenter_name else None
        wc_short = get_workcenter_short(workcenter_name) if workcenter_name else None

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

        # Apply filters
        if workcenter_groups and wc_group not in workcenter_groups:
            continue
        if is_production is not None:
            if bool(resource.get('PJ_ISPRODUCTION')) != is_production:
                continue
        if is_key is not None:
            if bool(resource.get('PJ_ISKEY')) != is_key:
                continue
        if is_monitor is not None:
            if bool(resource.get('PJ_ISMONITOR')) != is_monitor:
                continue
        if status_categories:
            if record.get('STATUS_CATEGORY') not in status_categories:
                continue

        merged.append(record)

    logger.debug(f"Merged {len(merged)} resource status records")
    return merged


def get_resource_status_summary(
    workcenter_groups: Optional[List[str]] = None,
    is_production: Optional[bool] = None,
    is_key: Optional[bool] = None,
    is_monitor: Optional[bool] = None,
) -> Dict[str, Any]:
    """Get resource status summary statistics.

    Args:
        workcenter_groups: Filter by WORKCENTER_GROUP
        is_production: Filter by PJ_ISPRODUCTION flag
        is_key: Filter by PJ_ISKEY flag
        is_monitor: Filter by PJ_ISMONITOR flag

    Returns:
        Dict with summary statistics including OU%, Availability%, and per-status counts.
    """
    # Get merged data with filters (except status_categories)
    data = get_merged_resource_status(
        workcenter_groups=workcenter_groups,
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
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
    nst = by_status['NST']

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
) -> List[Dict[str, Any]]:
    """Get workcenter × status matrix.

    Returns count of equipment by workcenter group and status.

    Args:
        is_production: Filter by PJ_ISPRODUCTION flag
        is_key: Filter by PJ_ISKEY flag
        is_monitor: Filter by PJ_ISMONITOR flag

    Returns:
        List of dicts with workcenter_group and status counts.
    """
    # Get merged data
    data = get_merged_resource_status(
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
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
