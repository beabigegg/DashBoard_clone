# -*- coding: utf-8 -*-
"""Constants and configuration values for MES Dashboard.

Centralized location for all constant values used across the application.
"""

# ============================================================
# Location / Area Exclusions
# ============================================================

# Locations to exclude from equipment queries
EXCLUDED_LOCATIONS = [
    'ATEC',
    'F區',
    'F區焊接站',
    '報廢',
    '實驗室',
    '山東',
    '成型站_F區',
    '焊接F區',
    '無錫',
    '熒茂',
]

# Asset statuses to exclude
EXCLUDED_ASSET_STATUSES = ['Disapproved']


# ============================================================
# Equipment Type Filters
# ============================================================

# SQL condition for filtering valid equipment types
EQUIPMENT_TYPE_FILTER = """
((OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY')
 OR (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT'))
"""

# Equipment flag filter templates
EQUIPMENT_FLAG_FILTERS = {
    'isProduction': "NVL(PJ_ISPRODUCTION, 0) = 1",
    'isKey': "NVL(PJ_ISKEY, 0) = 1",
    'isMonitor': "NVL(PJ_ISMONITOR, 0) = 1",
}


# ============================================================
# Cache TTL Settings (in seconds)
# ============================================================

CACHE_TTL_DEFAULT = 60           # Default cache TTL: 1 minute
CACHE_TTL_FILTER_OPTIONS = 600   # Filter options: 10 minutes
CACHE_TTL_PIVOT_COLUMNS = 300    # Pivot columns: 5 minutes
CACHE_TTL_KPI = 60               # KPI data: 1 minute
CACHE_TTL_TREND = 300            # Trend data: 5 minutes


# ============================================================
# Query Defaults
# ============================================================

DEFAULT_DAYS_BACK = 365          # Default days to look back for queries
DEFAULT_WIP_DAYS_BACK = 90       # Default days for WIP queries
DEFAULT_PAGE_SIZE = 100          # Default pagination size
MAX_PAGE_SIZE = 500              # Maximum allowed page size


# ============================================================
# Status Definitions
# ============================================================

# Equipment status codes and their display names
STATUS_DISPLAY_NAMES = {
    'PRD': '生產中',
    'SBY': '待機',
    'UDT': '非計畫停機',
    'SDT': '計畫停機',
    'EGT': '工程時間',
    'NST': '未排單',
}

# WIP status codes to exclude (completed/scrapped)
WIP_EXCLUDED_STATUS = (8, 128)
