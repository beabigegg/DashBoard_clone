# -*- coding: utf-8 -*-
"""Test case definitions for SQL optimization parity verification.

Each TestCase defines an original-vs-optimized SQL pair with the parameters
needed to execute against Oracle.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from mes_dashboard.sql.filters import CommonFilters

from sql_optimization_verify import TestCase

_NQ_REASONS = CommonFilters.get_non_quality_reasons_sql()


def get_test_cases() -> List[TestCase]:
    """Return all test cases for SQL optimization verification."""
    return [
        # ── CRITICAL ─────────────────────────────────────────────────────

        TestCase(
            name="C1: hold_history/trend",
            severity="CRITICAL",
            module="hold_history",
            original="hold_history/trend",
            optimized="hold_history/trend_optimized",
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
            placeholders={"NON_QUALITY_REASONS": _NQ_REASONS},
            sort_columns=["TXN_DATE", "HOLD_TYPE"],
            description="Eliminate ON 1=1 Cartesian + add HOLDTXNDATE WHERE pushdown",
            impact={
                "service_files": ["hold_dataset_cache.py"],
                "route_files": ["hold_history_routes.py"],
                "output_schema_changed": False,
                "risk_level": "HIGH",
            },
        ),
        TestCase(
            name="C2: hold_history/reason_pareto",
            severity="CRITICAL",
            module="hold_history",
            original="hold_history/reason_pareto",
            optimized="hold_history/reason_pareto_optimized",
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "hold_type": "all",
                "include_new": 1,
                "include_on_hold": 1,
                "include_released": 1,
            },
            placeholders={"NON_QUALITY_REASONS": _NQ_REASONS},
            sort_columns=["REASON"],
            description="Add HOLDTXNDATE WHERE to history_base CTE",
            impact={
                "service_files": ["hold_history_service.py"],
                "route_files": ["hold_history_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="C3: hold_history/duration",
            severity="CRITICAL",
            module="hold_history",
            original="hold_history/duration",
            optimized="hold_history/duration_optimized",
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "hold_type": "all",
                "include_new": 1,
                "include_on_hold": 1,
                "include_released": 1,
            },
            placeholders={"NON_QUALITY_REASONS": _NQ_REASONS},
            sort_columns=["ORDER_KEY"],
            description="Add HOLDTXNDATE WHERE to history_base CTE",
            impact={
                "service_files": ["hold_history_service.py"],
                "route_files": ["hold_history_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="C4: hold_history/list",
            severity="CRITICAL",
            module="hold_history",
            original="hold_history/list",
            optimized="hold_history/list_optimized",
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "hold_type": "all",
                "reason": None,
                "include_new": 1,
                "include_on_hold": 1,
                "include_released": 1,
                "duration_range": None,
                "offset": 0,
                "limit": 50,
            },
            placeholders={"NON_QUALITY_REASONS": _NQ_REASONS},
            sort_columns=["HOLD_DATE", "LOT_ID"],
            description="Compute hold_hours once + add HOLDTXNDATE WHERE pushdown",
            impact={
                "service_files": ["hold_history_service.py"],
                "route_files": ["hold_history_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="C6: dashboard/resource_detail_with_job",
            severity="CRITICAL",
            module="dashboard",
            original="dashboard/resource_detail_with_job",
            optimized="dashboard/resource_detail_with_job_optimized",
            params={"start_row": 1, "end_row": 50},
            placeholders={
                "DAYS_BACK": "7",
                "LOCATION_FILTER": "",
                "ASSET_STATUS_FILTER": "",
                "WHERE_CLAUSE": "1=1",
            },
            sort_columns=["RESOURCENAME"],
            ignore_columns=["RN"],
            description="Replace exact timestamp JOIN with range + merge latest_txn CTE",
            impact={
                "service_files": ["dashboard_service.py"],
                "route_files": ["dashboard_routes.py"],
                "output_schema_changed": False,
                "risk_level": "MEDIUM",
            },
        ),

        # ── HIGH ─────────────────────────────────────────────────────────

        TestCase(
            name="H2: dashboard/kpi_standalone",
            severity="HIGH",
            module="dashboard",
            original="dashboard/kpi_standalone",
            optimized="dashboard/kpi_standalone_optimized",
            params={},
            placeholders={
                "DAYS_BACK": "7",
                "LOCATION_FILTER": "",
                "ASSET_STATUS_FILTER": "",
                "WHERE_CLAUSE": "",
            },
            sort_columns=[],
            description="Narrow SELECT * to only needed columns",
            impact={
                "service_files": ["dashboard_service.py"],
                "route_files": ["dashboard_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="H3: resource/latest_status",
            severity="HIGH",
            module="resource",
            original="resource/latest_status",
            optimized="resource/latest_status_optimized",
            params={},
            placeholders={
                "days_back": "7",
                "LOCATION_FILTER": "",
                "ASSET_STATUS_FILTER": "",
            },
            sort_columns=["RESOURCEID"],
            ignore_columns=["RN"],
            description="Replace COALESCE in WHERE with OR-based predicate",
            impact={
                "service_files": ["resource_service.py"],
                "route_files": ["resource_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="H4: reject_history/performance_daily",
            severity="HIGH",
            module="reject_history",
            original="reject_history/performance_daily",
            optimized="reject_history/performance_daily_optimized",
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
            placeholders={
                "BASE_WHERE": "r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1",
            },
            sort_columns=["TXN_DAY", "WORKCENTER_GROUP", "SPECNAME", "LOSSREASONNAME"],
            description="Replace REGEXP_SUBSTR with SUBSTR/INSTR",
            impact={
                "service_files": ["reject_history_service.py"],
                "route_files": ["reject_history_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="H5: query_tool/lot_rejects",
            severity="HIGH",
            module="query_tool",
            original="query_tool/lot_rejects",
            optimized="query_tool/lot_rejects_optimized",
            params={"container_id": "48810380002a40a9"},
            placeholders={},
            sort_columns=["TXN_DAY", "WORKCENTERSEQUENCE_GROUP", "WORKCENTERNAME"],
            description="ORDER BY projected alias instead of re-computing expression",
            impact={
                "service_files": ["event_fetcher.py"],
                "route_files": ["query_tool_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="H8: mid_section_defect/station_detection",
            severity="HIGH",
            module="mid_section_defect",
            original="mid_section_defect/station_detection",
            optimized="mid_section_defect/station_detection_optimized",
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
            placeholders={
                "STATION_FILTER": "UPPER(h.WORKCENTERNAME) LIKE '%AOI%'",
                "STATION_FILTER_REJECTS": "UPPER(r.WORKCENTERNAME) LIKE '%AOI%'",
            },
            sort_columns=["CONTAINERID", "TRACKINTIMESTAMP"],
            description="Replace SELECT DISTINCT with ROW_NUMBER for deterministic workflow join",
            impact={
                "service_files": ["mid_section_defect_service.py"],
                "route_files": ["mid_section_defect_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),

        # ── MEDIUM ───────────────────────────────────────────────────────

        TestCase(
            name="M2: wip/detail",
            severity="MEDIUM",
            module="wip",
            original="wip/detail",
            optimized="wip/detail_optimized",
            params={"offset": 0, "limit": 50},
            placeholders={"WHERE_CLAUSE": ""},
            sort_columns=["LOTID"],
            ignore_columns=["RN"],
            description="Replace ROW_NUMBER pagination with OFFSET...FETCH NEXT",
            impact={
                "service_files": ["wip_service.py"],
                "route_files": ["wip_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="M4: query_tool/lot_jobs",
            severity="MEDIUM",
            module="query_tool",
            original="query_tool/lot_jobs",
            optimized="query_tool/lot_jobs_optimized",
            params={
                "equipment_id": "4880168000030f37",
                "time_start": datetime(2026, 3, 1),
                "time_end": datetime(2026, 3, 13),
            },
            placeholders={},
            sort_columns=["CREATEDATE"],
            description="Simplify 3-way OR to overlap condition",
            impact={
                "service_files": ["query_tool_service.py"],
                "route_files": ["query_tool_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="M6: query_tool/lot_split_merge_history",
            severity="MEDIUM",
            module="query_tool",
            original="query_tool/lot_split_merge_history",
            optimized="query_tool/lot_split_merge_history_optimized",
            params={},
            placeholders={
                "WORK_ORDER_FILTER": "1=0",  # placeholder; needs real work order
                "TIME_WINDOW": "",
                "ROW_LIMIT": "FETCH FIRST 500 ROWS ONLY",
            },
            sort_columns=["TXNDATE"],
            description="Convert OR IN to UNION ALL",
            impact={
                "service_files": ["query_tool_service.py"],
                "route_files": ["query_tool_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="M7: yield_alert/summary",
            severity="MEDIUM",
            module="yield_alert",
            original="yield_alert/summary",
            optimized="yield_alert/summary_optimized",
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
            placeholders={"WHERE_CLAUSE": ""},
            sort_columns=[],
            description="Remove UPPER(NVL(TRIM(...))) wrapping",
            impact={
                "service_files": ["yield_alert_service.py"],
                "route_files": ["yield_alert_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
        TestCase(
            name="M9: query_tool/adjacent_lots",
            severity="MEDIUM",
            module="query_tool",
            original="query_tool/adjacent_lots",
            optimized="query_tool/adjacent_lots_optimized",
            params={
                "equipment_id": "4880168000030fd4",
                "target_trackin_time": datetime(2026, 3, 13, 8, 54, 7),
                "time_window_hours": 24,
            },
            placeholders={},
            sort_columns=["RELATIVE_POSITION"],
            description="Add MATERIALIZE hint to ranked_lots CTE",
            impact={
                "service_files": ["query_tool_service.py"],
                "route_files": ["query_tool_routes.py"],
                "output_schema_changed": False,
                "risk_level": "LOW",
            },
        ),
    ]
