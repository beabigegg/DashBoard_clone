# -*- coding: utf-8 -*-
"""Workcenter grouping configuration for MES Dashboard.

Defines how individual workcenters are grouped and their display order.
This configuration is used across WIP reports, resource status, and dashboard.
"""

from typing import Tuple, Optional

# ============================================================
# Workcenter Group Definitions
# ============================================================
# Order determines display sequence (left to right in tables, top to bottom in charts)
# Patterns are matched case-insensitively
# Exclude patterns take precedence over include patterns

WORKCENTER_GROUPS = {
    '切割': {
        'order': 0,
        'patterns': ['切割'],
        'exclude': ['元件切割', 'PKG_SAW']  # 元件切割 is a separate group
    },
    '焊接_DB': {
        'order': 1,
        'patterns': ['焊接_DB', '焊_DB_料', '焊_DB']
    },
    '焊接_WB': {
        'order': 2,
        'patterns': ['焊接_WB', '焊_WB_料', '焊_WB']
    },
    '焊接_DW': {
        'order': 3,
        'patterns': ['焊接_DW', '焊_DW', '焊_DW_料']
    },
    '成型': {
        'order': 4,
        'patterns': ['成型', '成型_料']
    },
    '去膠': {
        'order': 5,
        'patterns': ['去膠']
    },
    '水吹砂': {
        'order': 6,
        'patterns': ['水吹砂']
    },
    '電鍍': {
        'order': 7,
        'patterns': ['掛鍍', '滾鍍', '條鍍', '電鍍', '補鍍', 'TOTAI', 'BANDL']
    },
    '移印': {
        'order': 8,
        'patterns': ['移印']
    },
    '切彎腳': {
        'order': 9,
        'patterns': ['切彎腳']
    },
    '元件切割': {
        'order': 10,
        'patterns': ['元件切割', 'PKG_SAW']
    },
    '測試': {
        'order': 11,
        'patterns': ['TMTT', '測試']
    }
}

# Group order for sorting (exported for frontend use)
GROUP_ORDER = {name: config['order'] for name, config in WORKCENTER_GROUPS.items()}


def get_workcenter_group(workcenter_name: Optional[str]) -> Tuple[Optional[str], int]:
    """Map workcenter name to its group name and order.

    Args:
        workcenter_name: The original workcenter name from database

    Returns:
        Tuple of (group_name, order) where:
        - group_name: The merged group name (e.g., '焊接_DB') or None if unmatched
        - order: The display order (0-11 for defined groups, 999 for unmatched)

    Examples:
        >>> get_workcenter_group('焊接_DB')
        ('焊接_DB', 1)
        >>> get_workcenter_group('焊_DB_料')
        ('焊接_DB', 1)
        >>> get_workcenter_group('切割')
        ('切割', 0)
        >>> get_workcenter_group('元件切割')
        ('元件切割', 10)
        >>> get_workcenter_group('Unknown_WC')
        (None, 999)
    """
    if not workcenter_name:
        return None, 999

    wc_upper = workcenter_name.upper()

    for group_name, config in WORKCENTER_GROUPS.items():
        # Check exclusions first (important for '切割' vs '元件切割')
        if 'exclude' in config:
            excluded = False
            for excl in config['exclude']:
                if excl.upper() in wc_upper:
                    excluded = True
                    break
            if excluded:
                continue

        # Check patterns
        for pattern in config['patterns']:
            if pattern.upper() in wc_upper:
                return group_name, config['order']

    return None, 999  # Unmatched workcenters


def get_all_group_names() -> list:
    """Get all group names in order.

    Returns:
        List of group names sorted by their order.
    """
    return sorted(WORKCENTER_GROUPS.keys(), key=lambda x: WORKCENTER_GROUPS[x]['order'])


def get_group_order(group_name: str) -> int:
    """Get the order number for a group name.

    Args:
        group_name: The group name to look up

    Returns:
        Order number (0-11) or 999 if not found
    """
    return GROUP_ORDER.get(group_name, 999)
