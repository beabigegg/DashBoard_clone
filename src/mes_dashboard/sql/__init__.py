"""
SQL Query Management Module

Provides safe SQL query loading, building, and common filters.

Architecture Overview:
    This module provides three main components for SQL query management:

    1. SQLLoader - Load SQL templates from .sql files with LRU caching
    2. QueryBuilder - Build parameterized WHERE conditions safely
    3. CommonFilters - Reusable filter patterns for common queries

Directory Structure:
    src/mes_dashboard/sql/
    ├── __init__.py          # Public API exports
    ├── loader.py            # SQLLoader implementation
    ├── builder.py           # QueryBuilder implementation
    ├── filters.py           # CommonFilters implementation
    ├── dashboard/           # Dashboard-related SQL files
    │   ├── kpi.sql
    │   ├── heatmap.sql
    │   ├── workcenter_cards.sql
    │   └── resource_detail_with_job.sql
    ├── resource/            # Resource status SQL files
    │   ├── latest_status.sql
    │   ├── by_status.sql
    │   ├── by_workcenter.sql
    │   ├── detail.sql
    │   └── workcenter_status_matrix.sql
    ├── resource_history/    # Resource history SQL files
    │   ├── kpi.sql
    │   ├── trend.sql
    │   ├── heatmap.sql
    │   └── detail.sql
    └── wip/                 # WIP (Work In Progress) SQL files
        ├── summary.sql
        ├── matrix.sql
        └── detail.sql

SQL File Format:
    SQL files use placeholders for dynamic parts:

    - {{ PLACEHOLDER }} - Replaced via str.replace() before execution
    - :param_name - Oracle bind variables (filled by params dict)

    Example SQL file (resource/by_status.sql):
        -- Resource count by status
        -- Placeholders:
        --   {{ LATEST_STATUS_SUBQUERY }} - Base CTE for latest status
        -- Parameters:
        --   (from QueryBuilder)
        SELECT NEWSTATUSNAME, COUNT(*) as COUNT
        FROM ({{ LATEST_STATUS_SUBQUERY }}) rs
        WHERE 1=1 {{ WHERE_CLAUSE }}
        GROUP BY NEWSTATUSNAME

Usage Example:
    >>> from mes_dashboard.sql import SQLLoader, QueryBuilder
    >>> from mes_dashboard.core.database import read_sql_df
    >>>
    >>> # Load SQL template
    >>> sql = SQLLoader.load("resource/by_status")
    >>>
    >>> # Build parameterized conditions
    >>> builder = QueryBuilder()
    >>> builder.add_in_condition("LOCATIONNAME", ["FAB1", "FAB2"])
    >>> builder.add_like_condition("WORKCENTERNAME", "ASSY", position="start")
    >>> where_clause, params = builder.build_where_only()
    >>>
    >>> # Replace placeholders and execute
    >>> sql = sql.replace("{{ LATEST_STATUS_SUBQUERY }}", base_cte)
    >>> sql = sql.replace("{{ WHERE_CLAUSE }}", where_clause)
    >>> df = read_sql_df(sql, params)

SQL Injection Prevention:
    - Always use QueryBuilder for user-provided values
    - Use :param_name bind variables for all dynamic values
    - Placeholders {{ }} are only for static, pre-defined SQL fragments
    - Never interpolate user input directly into SQL strings
"""

from .loader import SQLLoader
from .builder import QueryBuilder
from .filters import CommonFilters

__all__ = [
    "SQLLoader",
    "QueryBuilder",
    "CommonFilters",
]
