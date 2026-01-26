# -*- coding: utf-8 -*-
"""Utility functions for MES Dashboard.

Common helper functions used across services.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.config.constants import (
    DEFAULT_DAYS_BACK,
    EQUIPMENT_FLAG_FILTERS,
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
)


# ============================================================
# Parameter Extraction
# ============================================================


def get_days_back(filters: Optional[Dict] = None, default: int = DEFAULT_DAYS_BACK) -> int:
    """Extract days_back parameter from filters dict."""
    if filters:
        return int(filters.get('days_back', default))
    return default


# ============================================================
# SQL Filter Building
# ============================================================


def build_filter_conditions(
    filters: Optional[Dict],
    field_mapping: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Build SQL WHERE conditions from filters dict."""
    if not filters:
        return []

    conditions = []

    if field_mapping:
        for filter_key, column_name in field_mapping.items():
            values = filters.get(filter_key)
            if values and len(values) > 0:
                if isinstance(values, list):
                    value_list = "', '".join(str(v) for v in values)
                    conditions.append(f"{column_name} IN ('{value_list}')")
                else:
                    conditions.append(f"{column_name} = '{values}'")

    return conditions


def build_equipment_filter_sql(filters: Optional[Dict]) -> List[str]:
    """Build SQL conditions for equipment flag filters."""
    if not filters:
        return []

    conditions = []

    for flag_key, sql_condition in EQUIPMENT_FLAG_FILTERS.items():
        if filters.get(flag_key):
            conditions.append(sql_condition)

    return conditions


def build_location_filter_sql(
    filters: Optional[Dict],
    column_name: str = 'LOCATIONNAME',
) -> Optional[str]:
    """Build SQL condition for location filtering."""
    if not filters:
        return None

    locations = filters.get('locations')
    if locations and len(locations) > 0:
        loc_list = "', '".join(locations)
        return f"{column_name} IN ('{loc_list}')"

    return None


def build_asset_status_filter_sql(
    filters: Optional[Dict],
    column_name: str = 'PJ_ASSETSSTATUS',
) -> Optional[str]:
    """Build SQL condition for asset status filtering."""
    if not filters:
        return None

    statuses = filters.get('assetsStatuses')
    if statuses and len(statuses) > 0:
        status_list = "', '".join(statuses)
        return f"{column_name} IN ('{status_list}')"

    return None


def build_exclusion_sql(
    locations: List[str] = None,
    asset_statuses: List[str] = None,
    location_column: str = 'LOCATIONNAME',
    status_column: str = 'PJ_ASSETSSTATUS',
) -> List[str]:
    """Build SQL conditions for excluding specific locations and statuses."""
    conditions = []

    loc_list = locations if locations is not None else EXCLUDED_LOCATIONS
    if loc_list:
        locs = "', '".join(loc_list)
        conditions.append(f"{location_column} NOT IN ('{locs}')")

    status_list = asset_statuses if asset_statuses is not None else EXCLUDED_ASSET_STATUSES
    if status_list:
        stats = "', '".join(status_list)
        conditions.append(f"{status_column} NOT IN ('{stats}')")

    return conditions


# ============================================================
# Data Transformation
# ============================================================


def convert_datetime_fields(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    format_str: str = '%Y-%m-%d %H:%M:%S',
) -> pd.DataFrame:
    """Convert datetime columns in DataFrame to formatted strings."""
    if df.empty:
        return df

    if columns is None:
        columns = df.select_dtypes(include=['datetime64']).columns.tolist()

    for col in columns:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: x.strftime(format_str) if pd.notna(x) and hasattr(x, 'strftime') else None
            )

    return df


def row_to_dict(row: Any, columns: List[str]) -> Dict[str, Any]:
    """Convert a database row to dictionary with datetime handling."""
    row_dict = {}
    for i, col in enumerate(columns):
        value = row[i]
        if isinstance(value, datetime):
            row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
        else:
            row_dict[col] = value
    return row_dict


# ============================================================
# API Response Formatting
# ============================================================


def format_api_response(
    success: bool,
    data: Any = None,
    error: Optional[str] = None,
    count: Optional[int] = None,
    **extra,
) -> Dict[str, Any]:
    """Create standardized API response dict."""
    response = {'success': success}

    if data is not None:
        response['data'] = data

    if error is not None:
        response['error'] = error

    if count is not None:
        response['count'] = count

    response.update(extra)

    return response


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default
