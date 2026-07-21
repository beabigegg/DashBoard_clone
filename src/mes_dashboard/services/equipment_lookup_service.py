# -*- coding: utf-8 -*-
"""Equipment Lookup (機台查詢) service for MES Dashboard.

Quick-lookup filtering over the resource_cache master equipment list
(DWH.DW_MES_RESOURCE), scoped by 機台位置 (LOCATIONNAME) / 機型
(RESOURCEFAMILYNAME) / 編號 (RESOURCENAME).

The resource_cache module already bakes the equipment-scope filters
(EQUIPMENT_TYPE_FILTER / EXCLUDED_LOCATIONS / EXCLUDED_ASSET_STATUSES /
WORKCENTERNAME NOT NULL) into its Oracle sync query, so every function
here that reads from the cache already returns only the correct scope of
real equipment — no additional scope filtering is applied in this module.
"""

import logging
import math
from typing import Any, Dict, List, Optional

from mes_dashboard.services.resource_cache import (
    get_distinct_values,
    get_resources_by_filter,
)

logger = logging.getLogger('mes_dashboard.equipment_lookup_service')

# Columns the /list endpoint accepts for sort_by (aligned with the row payload).
SORTABLE_COLUMNS = ('RESOURCENAME', 'LOCATIONNAME', 'RESOURCEFAMILYNAME')
DEFAULT_SORT_BY = 'RESOURCENAME'
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20


def get_equipment_lookup_options() -> Dict[str, List[str]]:
    """Get filter dropdown options for the equipment lookup page.

    Options are the full universe of values (no cross-filter narrowing) —
    deliberately simple/independent filters, by design, for this page.

    Returns:
        Dict with 'locations', 'families', 'resource_names' lists.
    """
    return {
        'locations': get_distinct_values('LOCATIONNAME'),
        'families': get_distinct_values('RESOURCEFAMILYNAME'),
        'resource_names': get_distinct_values('RESOURCENAME'),
    }


def _sort_key(sort_by: str):
    def key_fn(record: Dict[str, Any]):
        value = record.get(sort_by)
        return value if value is not None else ''
    return key_fn


def get_equipment_lookup_list(
    locations: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_names: Optional[List[str]] = None,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = 'asc',
) -> Dict[str, Any]:
    """Get a filtered/sorted/paginated equipment list.

    Args:
        locations: Exact-match LOCATIONNAME values (or None/empty = no filter).
        families: Exact-match RESOURCEFAMILYNAME values (or None/empty = no filter).
        resource_names: Exact-match RESOURCENAME values, applied as a plain
            Python membership filter on top of get_resources_by_filter() —
            RESOURCENAME's near-1:1 cardinality is unsuited to that
            function's bucketed low-cardinality index design.
        page: 1-based page number (caller must pre-validate as a positive int).
        page_size: Rows per page (caller must pre-validate as a positive int).
        sort_by: One of SORTABLE_COLUMNS (caller must pre-validate).
        sort_dir: 'asc' or 'desc' (caller must pre-validate).

    Returns:
        Dict with 'rows' and 'pagination' keys.
    """
    resources = get_resources_by_filter(
        locations=locations or None,
        families=families or None,
    )

    if resource_names:
        name_set = set(resource_names)
        resources = [r for r in resources if r.get('RESOURCENAME') in name_set]

    sort_column = sort_by if sort_by in SORTABLE_COLUMNS else DEFAULT_SORT_BY
    reverse = str(sort_dir).lower() == 'desc'
    resources = sorted(resources, key=_sort_key(sort_column), reverse=reverse)

    total = len(resources)
    page_size = max(int(page_size), 1)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(int(page), 1)

    start = (page - 1) * page_size
    end = start + page_size
    page_rows = resources[start:end]

    rows = [
        {
            'RESOURCENAME': r.get('RESOURCENAME'),
            'LOCATIONNAME': r.get('LOCATIONNAME'),
            'RESOURCEFAMILYNAME': r.get('RESOURCEFAMILYNAME'),
            'VENDORNAME': r.get('VENDORNAME'),
            'VENDORMODEL': r.get('VENDORMODEL'),
            'WORKCENTERNAME': r.get('WORKCENTERNAME'),
        }
        for r in page_rows
    ]

    return {
        'rows': rows,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
        },
    }
