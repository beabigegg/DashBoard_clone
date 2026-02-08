"""
Common SQL Filters

Provides reusable filter building methods for common query patterns.
"""

from typing import Any, Dict, List, Optional, Union

from mes_dashboard.config import EXCLUDED_ASSET_STATUSES, EXCLUDED_LOCATIONS
from mes_dashboard.config.constants import EQUIPMENT_FLAG_FILTERS

from .builder import QueryBuilder


# Non-quality hold reasons (canonical source, used by wip_service.py)
# All other hold reasons are considered quality holds
NON_QUALITY_HOLD_REASONS = {
    "IQC檢驗(久存品驗證)(QC)",
    "大中/安波幅50pcs樣品留樣(PD)",
    "工程驗證(PE)",
    "工程驗證(RD)",
    "指定機台生產",
    "特殊需求(X-Ray全檢)",
    "特殊需求管控",
    "第一次量產QC品質確認(QC)",
    "需綁尾數(PD)",
    "樣品需求留存打樣(樣品)",
    "盤點(收線)需求",
}


class CommonFilters:
    """Common SQL filter builders."""

    # =========================================================
    # Location & Asset Status Filters
    # =========================================================

    @staticmethod
    def add_location_exclusion(
        builder: QueryBuilder,
        column: str = "LOCATIONNAME",
    ) -> QueryBuilder:
        """
        Add location exclusion filter.

        Excludes locations defined in EXCLUDED_LOCATIONS config.
        Allows NULL values.

        Args:
            builder: QueryBuilder instance
            column: Column name (default: LOCATIONNAME)

        Returns:
            QueryBuilder for method chaining
        """
        if EXCLUDED_LOCATIONS:
            builder.add_not_in_condition(column, EXCLUDED_LOCATIONS, allow_null=True)
        return builder

    @staticmethod
    def add_asset_status_exclusion(
        builder: QueryBuilder,
        column: str = "PJ_ASSETSSTATUS",
    ) -> QueryBuilder:
        """
        Add asset status exclusion filter.

        Excludes statuses defined in EXCLUDED_ASSET_STATUSES config.
        Allows NULL values.

        Args:
            builder: QueryBuilder instance
            column: Column name (default: PJ_ASSETSSTATUS)

        Returns:
            QueryBuilder for method chaining
        """
        if EXCLUDED_ASSET_STATUSES:
            builder.add_not_in_condition(
                column, EXCLUDED_ASSET_STATUSES, allow_null=True
            )
        return builder

    # =========================================================
    # WIP Base Filters
    # =========================================================

    @staticmethod
    def add_wip_base_filters(
        builder: QueryBuilder,
        workorder: Optional[str] = None,
        lotid: Optional[str] = None,
        package: Optional[str] = None,
        pj_type: Optional[str] = None,
    ) -> QueryBuilder:
        """
        Add WIP base filters (fuzzy search).

        Args:
            builder: QueryBuilder instance
            workorder: Workorder filter (LIKE %value%)
            lotid: Lot ID filter (LIKE %value%)
            package: Package filter (LIKE %value%)
            pj_type: PJ type filter (LIKE %value%)

        Returns:
            QueryBuilder for method chaining
        """
        if workorder:
            builder.add_like_condition("WORKORDER", workorder)
        if lotid:
            builder.add_like_condition("LOTID", lotid)
        if package:
            builder.add_like_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_like_condition("PJ_TYPE", pj_type)
        return builder

    # =========================================================
    # Status Filters
    # =========================================================

    @staticmethod
    def add_status_filter(
        builder: QueryBuilder,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        column: str = "STATUS",
    ) -> QueryBuilder:
        """
        Add status filter.

        Args:
            builder: QueryBuilder instance
            status: Single status value
            statuses: List of status values
            column: Column name (default: STATUS)

        Returns:
            QueryBuilder for method chaining
        """
        if status:
            builder.add_param_condition(column, status)
        elif statuses:
            builder.add_in_condition(column, statuses)
        return builder

    # =========================================================
    # Hold Type Filters
    # =========================================================

    @staticmethod
    def add_hold_type_filter(
        builder: QueryBuilder,
        hold_type: Optional[str] = None,
        column: str = "HOLDREASONNAME",
    ) -> QueryBuilder:
        """
        Add hold type filter (quality vs non-quality).

        Args:
            builder: QueryBuilder instance
            hold_type: "quality" or "non_quality"
            column: Column name (default: HOLDREASONNAME)

        Returns:
            QueryBuilder for method chaining
        """
        if hold_type == "quality":
            # Quality holds: exclude non-quality reasons
            builder.add_not_in_condition(column, list(NON_QUALITY_HOLD_REASONS))
        elif hold_type == "non_quality":
            # Non-quality holds: only non-quality reasons
            builder.add_in_condition(column, list(NON_QUALITY_HOLD_REASONS))
        return builder

    @staticmethod
    def is_quality_hold(reason: Optional[str]) -> bool:
        """Check if a hold reason is quality-related."""
        return reason not in NON_QUALITY_HOLD_REASONS

    @staticmethod
    def get_non_quality_reasons_sql() -> str:
        """Get non-quality hold reasons as SQL-safe literal list.

        Used for embedding in SQL CASE expressions where bind parameters
        cannot be used. Values are from a constant set (not user input).

        Returns:
            SQL-safe string for IN clause, e.g., "'reason1', 'reason2', ..."
        """
        # Escape single quotes in values (replace ' with '')
        escaped = [f"'{r.replace(chr(39), chr(39)+chr(39))}'" for r in NON_QUALITY_HOLD_REASONS]
        return ", ".join(escaped)

    # =========================================================
    # Equipment/Resource Filters
    # =========================================================

    @staticmethod
    def add_equipment_filter(
        builder: QueryBuilder,
        resource_ids: Optional[List[str]] = None,
        workcenters: Optional[List[str]] = None,
    ) -> QueryBuilder:
        """
        Add equipment/resource filters.

        Args:
            builder: QueryBuilder instance
            resource_ids: List of resource IDs
            workcenters: List of workcenter names

        Returns:
            QueryBuilder for method chaining
        """
        if resource_ids:
            builder.add_in_condition("RESOURCEID", resource_ids)
        if workcenters:
            builder.add_in_condition("WORKCENTERNAME", workcenters)
        return builder

    @staticmethod
    def add_equipment_flag_filters(
        builder: QueryBuilder,
        filters: Optional[Dict] = None,
    ) -> QueryBuilder:
        """
        Add equipment flag filters (isProduction, isKey, isMonitor).

        These are safe boolean conditions from EQUIPMENT_FLAG_FILTERS config.

        Args:
            builder: QueryBuilder instance
            filters: Dict with flag keys (isProduction, isKey, isMonitor)

        Returns:
            QueryBuilder for method chaining
        """
        if not filters:
            return builder

        for flag_key, sql_condition in EQUIPMENT_FLAG_FILTERS.items():
            if filters.get(flag_key):
                builder.add_condition(sql_condition)

        return builder

    # =========================================================
    # Legacy Compatibility (for core/utils.py wrapper)
    # =========================================================

    @staticmethod
    def build_location_filter_legacy(
        locations: Optional[List[str]] = None,
        excluded_locations: Optional[List[str]] = None,
    ) -> str:
        """
        Build location filter SQL string (legacy format).

        Deprecated: Use add_location_exclusion() with QueryBuilder instead.
        """
        conditions = []
        if locations:
            loc_list = ", ".join(f"'{loc}'" for loc in locations)
            conditions.append(f"LOCATIONNAME IN ({loc_list})")
        if excluded_locations:
            exc_list = ", ".join(f"'{loc}'" for loc in excluded_locations)
            conditions.append(
                f"(LOCATIONNAME IS NULL OR LOCATIONNAME NOT IN ({exc_list}))"
            )
        return " AND ".join(conditions) if conditions else ""

    @staticmethod
    def build_asset_status_filter_legacy(
        excluded_statuses: Optional[List[str]] = None,
    ) -> str:
        """
        Build asset status filter SQL string (legacy format).

        Deprecated: Use add_asset_status_exclusion() with QueryBuilder instead.
        """
        if not excluded_statuses:
            return ""
        exc_list = ", ".join(f"'{s}'" for s in excluded_statuses)
        return f"(PJ_ASSETSSTATUS IS NULL OR PJ_ASSETSSTATUS NOT IN ({exc_list}))"
