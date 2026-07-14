#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask test-client response capture script for contract validation.

Captures a real (test-client) response for every endpoint declared in
api-contract.md. Endpoints backed by Oracle/Redis return their offline
error envelope — that IS the contracted offline shape (StandardErrorResponse).

Auth-required endpoints: login first via /api/auth/login with LOCAL_AUTH
credentials, then issue requests in the same session.

Usage:
    python tests/contract/capture_samples.py
    # or: conda run -n mes-dashboard python tests/contract/capture_samples.py

Outputs:
    tests/contract/samples/<endpoint_key>.json  (one per endpoint)
    tests/contract/response-samples.json        (manifest)
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

# Ensure src/ is on PYTHONPATH when run directly
REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# Configure offline environment BEFORE importing the app
os.environ.setdefault("TESTING", "True")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("ORACLE_DB_ENABLED", "false")
os.environ.setdefault("LDAP_API_URL", "")
os.environ.setdefault("LOCAL_AUTH_ENABLED", "true")
os.environ.setdefault("LOCAL_AUTH_USERNAME", "testuser")
os.environ.setdefault("LOCAL_AUTH_PASSWORD", "testpass")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-capture")
os.environ.setdefault("AI_QUERY_ENABLED", "false")
os.environ.setdefault("ANALYTICS_ANOMALY_DETECTION_ENABLED", "false")
os.environ.setdefault("PROD_HISTORY_ENABLED", "true")
os.environ.setdefault("DOWNTIME_BROWSER_DUCKDB", "false")
os.environ.setdefault("DOWNTIME_ASYNC_ENABLED", "false")
os.environ.setdefault("HOLD_ASYNC_ENABLED", "false")
os.environ.setdefault("RESOURCE_ASYNC_ENABLED", "false")

from mes_dashboard.app import create_app  # noqa: E402

SAMPLES_DIR = pathlib.Path(__file__).parent / "samples"
MANIFEST_PATH = pathlib.Path(__file__).parent / "response-samples.json"

# ---------------------------------------------------------------------------
# Endpoint definitions: (method, path, key, auth_required, body, qs)
# Each tuple: (method, url, key, needs_auth, json_body, query_string)
# ---------------------------------------------------------------------------
ENDPOINTS = [
    # ── Auth ──────────────────────────────────────────────────────────────
    ("POST", "/api/auth/login", "post_auth_login", False,
     {"username": "testuser", "password": "testpass"}, None),
    ("POST", "/api/auth/logout", "post_auth_logout", False, None, None),
    ("GET",  "/api/auth/me", "get_auth_me", False, None, None),
    ("PATCH", "/api/auth/heartbeat", "patch_auth_heartbeat", True, None, None),
    # ── Health ────────────────────────────────────────────────────────────
    ("GET", "/health", "get_health", False, None, None),
    ("GET", "/health/deep", "get_health_deep", False, None, None),
    # ── Job ───────────────────────────────────────────────────────────────
    ("GET",  "/api/job/test-job-id", "get_job_id", True, None, "prefix=test"),
    ("POST", "/api/job/test-job-id/abandon", "post_job_abandon", True,
     {"reason": "test"}, None),
    # ── Spool (binary) ────────────────────────────────────────────────────
    ("GET", "/api/spool/yield_alert_dataset/test-query-id.parquet",
     "get_spool_parquet", True, None, None),
    # ── WIP ───────────────────────────────────────────────────────────────
    ("GET",  "/api/wip/overview/summary", "get_wip_overview_summary", True,
     None, "workcenter=TEST"),
    ("POST", "/api/wip/overview/summary", "post_wip_overview_summary", True,
     {"workcenter": "TEST"}, None),
    ("POST", "/api/wip/overview/matrix", "post_wip_overview_matrix", True,
     {"workcenter": "TEST"}, None),
    ("GET",  "/api/wip/overview/matrix", "get_wip_overview_matrix", True,
     None, "workcenter=TEST"),
    ("GET",  "/api/wip/overview/hold", "get_wip_overview_hold", True,
     None, "workcenter=TEST"),
    ("POST", "/api/wip/overview/hold", "post_wip_overview_hold", True,
     {"workcenter": "TEST"}, None),
    ("GET",  "/api/wip/detail/TEST", "get_wip_detail_workcenter", True,
     None, None),
    ("POST", "/api/wip/detail/TEST", "post_wip_detail_workcenter", True,
     {}, None),
    ("GET",  "/api/wip/lot/TEST-LOT-001", "get_wip_lot", True, None, None),
    ("GET",  "/api/wip/meta/workcenters", "get_wip_meta_workcenters", True,
     None, None),
    ("GET",  "/api/wip/meta/packages", "get_wip_meta_packages", True,
     None, None),
    ("GET",  "/api/wip/meta/filter-options", "get_wip_meta_filter_options", True,
     None, None),
    ("POST", "/api/wip/meta/filter-options", "post_wip_meta_filter_options", True,
     {}, None),
    ("GET",  "/api/wip/meta/search", "get_wip_meta_search", True,
     None, "q=TEST"),
    # ── Hold Overview ─────────────────────────────────────────────────────
    ("GET",  "/api/hold-overview/summary", "get_hold_overview_summary", True,
     None, None),
    ("POST", "/api/hold-overview/summary", "post_hold_overview_summary", True,
     {}, None),
    ("GET",  "/api/hold-overview/matrix", "get_hold_overview_matrix", True,
     None, None),
    ("POST", "/api/hold-overview/matrix", "post_hold_overview_matrix", True,
     {}, None),
    ("GET",  "/api/hold-overview/treemap", "get_hold_overview_treemap", True,
     None, None),
    ("POST", "/api/hold-overview/treemap", "post_hold_overview_treemap", True,
     {}, None),
    ("GET",  "/api/hold-overview/lots", "get_hold_overview_lots", True,
     None, None),
    ("POST", "/api/hold-overview/lots", "post_hold_overview_lots", True,
     {}, None),
    # ── WIP Hold Detail ───────────────────────────────────────────────────
    ("GET", "/api/wip/hold-detail/summary", "get_wip_hold_detail_summary", True,
     None, None),
    ("GET", "/api/wip/hold-detail/distribution", "get_wip_hold_detail_distribution",
     True, None, None),
    ("GET", "/api/wip/hold-detail/lots", "get_wip_hold_detail_lots", True,
     None, None),
    # ── Hold History ──────────────────────────────────────────────────────
    ("GET",  "/api/hold-history/config", "get_hold_history_config", True,
     None, None),
    ("POST", "/api/hold-history/query", "post_hold_history_query", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("POST", "/api/hold-history/today-snapshot", "post_hold_history_today_snapshot",
     True, {"hold_type": "all", "record_type": "all"}, None),
    ("GET",  "/api/hold-history/view", "get_hold_history_view", True,
     None, "query_id=test-id"),
    # ── QC Gate ───────────────────────────────────────────────────────────
    ("GET", "/api/qc-gate/summary", "get_qc_gate_summary", True, None, None),
    # ── Resource ──────────────────────────────────────────────────────────
    ("GET", "/api/resource/by_status", "get_resource_by_status", True,
     None, None),
    ("GET", "/api/resource/by_workcenter", "get_resource_by_workcenter", True,
     None, None),
    ("GET", "/api/resource/workcenter_status_matrix",
     "get_resource_workcenter_status_matrix", True, None, None),
    ("POST", "/api/resource/detail", "post_resource_detail", True,
     {"resource_id": "TEST"}, None),
    ("GET", "/api/resource/filter_options", "get_resource_filter_options", True,
     None, None),
    ("GET", "/api/resource/status_values", "get_resource_status_values", True,
     None, None),
    ("GET", "/api/resource/status", "get_resource_status", True,
     None, None),
    ("GET", "/api/resource/status/options", "get_resource_status_options", True,
     None, None),
    ("GET", "/api/resource/status/summary", "get_resource_status_summary", True,
     None, None),
    ("GET", "/api/resource/status/matrix", "get_resource_status_matrix", True,
     None, None),
    # ── Resource History ──────────────────────────────────────────────────
    ("GET",  "/api/resource/history/options", "get_resource_history_options", True,
     None, None),
    ("POST", "/api/resource/history/query", "post_resource_history_query", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("GET",  "/api/resource/history/view", "get_resource_history_view", True,
     None, "query_id=test-id"),
    ("GET",  "/api/resource/history/page", "get_resource_history_page", True,
     None, None),
    ("GET",  "/api/resource/history/export", "get_resource_history_export", True,
     None, "query_id=test-id"),
    ("POST", "/api/resource/history/export", "post_resource_history_export", True,
     {"query_id": "test-id"}, None),
    ("GET",  "/api/resource/history/query/progress",
     "get_resource_history_query_progress", True, None, "query_id=test-id"),
    # ── Reject History ────────────────────────────────────────────────────
    ("GET",  "/api/reject-history/options", "get_reject_history_options", True,
     None, None),
    ("GET",  "/api/reject-history/summary", "get_reject_history_summary", True,
     None, "query_id=test-id"),
    ("GET",  "/api/reject-history/trend", "get_reject_history_trend", True,
     None, "query_id=test-id"),
    ("GET",  "/api/reject-history/reason-pareto", "get_reject_history_reason_pareto",
     True, None, "query_id=test-id"),
    ("POST", "/api/reject-history/batch-pareto", "post_reject_history_batch_pareto",
     True, {"query_id": "test-id"}, None),
    ("GET",  "/api/reject-history/batch-pareto", "get_reject_history_batch_pareto",
     True, None, "query_id=test-id"),
    ("GET",  "/api/reject-history/list", "get_reject_history_list", True,
     None, "query_id=test-id&page=1"),
    ("GET",  "/api/reject-history/export", "get_reject_history_export", True,
     None, "query_id=test-id"),
    ("GET",  "/api/reject-history/export-cached", "get_reject_history_export_cached",
     True, None, "query_id=test-id"),
    ("POST", "/api/reject-history/export-cached", "post_reject_history_export_cached",
     True, {"query_id": "test-id"}, None),
    ("GET",  "/api/reject-history/analytics", "get_reject_history_analytics", True,
     None, "query_id=test-id"),
    ("POST", "/api/reject-history/query", "post_reject_history_query", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07", "workcenter": "TEST"},
     None),
    ("GET",  "/api/reject-history/count", "get_reject_history_count", True,
     None, "query_id=test-id"),
    ("GET",  "/api/reject-history/job/test-job-id", "get_reject_history_job", True,
     None, None),
    ("GET",  "/api/reject-history/view", "get_reject_history_view", True,
     None, "query_id=test-id"),
    ("POST", "/api/reject-history/view", "post_reject_history_view", True,
     {"query_id": "test-id"}, None),
    # ── Yield Alert ───────────────────────────────────────────────────────
    ("POST", "/api/yield-alert/query", "post_yield_alert_query", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("GET",  "/api/yield-alert/job/test-job-id", "get_yield_alert_job", True,
     None, None),
    ("POST", "/api/yield-alert/analyze", "post_yield_alert_analyze", True,
     {"query_id": "test-id"}, None),
    ("GET",  "/api/yield-alert/view", "get_yield_alert_view", True,
     None, "query_id=test-id"),
    ("GET",  "/api/yield-alert/summary", "get_yield_alert_summary", True,
     None, "query_id=test-id"),
    ("GET",  "/api/yield-alert/trend", "get_yield_alert_trend", True,
     None, "query_id=test-id"),
    ("GET",  "/api/yield-alert/alerts", "get_yield_alert_alerts", True,
     None, "query_id=test-id"),
    ("GET",  "/api/yield-alert/reason-detail", "get_yield_alert_reason_detail", True,
     None, "query_id=test-id&reason=TEST"),
    ("GET",  "/api/yield-alert/drilldown-context", "get_yield_alert_drilldown_context",
     True, None, "query_id=test-id"),
    ("GET",  "/api/yield-alert/filter-options", "get_yield_alert_filter_options", True,
     None, None),
    ("GET",  "/api/yield-alert/cross-filter-options",
     "get_yield_alert_cross_filter_options", True, None, "query_id=test-id"),
    # ── Production History ────────────────────────────────────────────────
    ("GET",  "/api/production-history/type-options",
     "get_production_history_type_options", True, None, None),
    ("GET",  "/api/production-history/filter-options",
     "get_production_history_filter_options", True, None, None),
    ("POST", "/api/production-history/options", "post_production_history_options",
     True, {}, None),
    ("POST", "/api/production-history/query", "post_production_history_query", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07", "pj_types": ["TEST"]},
     None),
    ("GET",  "/api/production-history/job/test-job-id",
     "get_production_history_job", True, None, None),
    ("POST", "/api/production-history/page", "post_production_history_page", True,
     {"query_id": "test-id", "page": 1}, None),
    ("POST", "/api/production-history/matrix", "post_production_history_matrix", True,
     {"query_id": "test-id"}, None),
    ("GET",  "/api/production-history/count", "get_production_history_count", True,
     None, "query_id=test-id"),
    ("GET",  "/api/production-history/export", "get_production_history_export", True,
     None, "query_id=test-id"),
    ("POST", "/api/production-history/export", "post_production_history_export", True,
     {"query_id": "test-id"}, None),
    # ── Material Trace ────────────────────────────────────────────────────
    ("POST", "/api/material-trace/query", "post_material_trace_query", True,
     {"lot_id": "TEST"}, None),
    ("GET",  "/api/material-trace/job/test-job-id", "get_material_trace_job", True,
     None, None),
    ("POST", "/api/material-trace/export", "post_material_trace_export", True,
     {"query_hash": "test-hash"}, None),
    ("GET",  "/api/material-trace/filter-options", "get_material_trace_filter_options",
     True, None, None),
    # ── Trace ─────────────────────────────────────────────────────────────
    ("POST", "/api/trace/seed-resolve", "post_trace_seed_resolve", True,
     {"lot_id": "TEST"}, None),
    ("POST", "/api/trace/lineage", "post_trace_lineage", True,
     {"lot_id": "TEST"}, None),
    ("GET",  "/api/trace/lineage/job/test-job-id", "get_trace_lineage_job", True,
     None, None),
    ("GET",  "/api/trace/lineage/job/test-job-id/result",
     "get_trace_lineage_job_result", True, None, None),
    ("POST", "/api/trace/events", "post_trace_events", True,
     {"lot_id": "TEST"}, None),
    ("GET",  "/api/trace/job/test-job-id", "get_trace_job", True, None, None),
    ("GET",  "/api/trace/job/test-job-id/result", "get_trace_job_result", True,
     None, None),
    ("GET",  "/api/trace/job/test-job-id/stream", "get_trace_job_stream", True,
     None, None),
    ("GET",  "/api/trace/seed/job/test-job-id", "get_trace_seed_job", True,
     None, None),
    ("GET",  "/api/trace/seed/job/test-job-id/result", "get_trace_seed_job_result",
     True, None, None),
    # ── Mid Section Defect ────────────────────────────────────────────────
    ("GET", "/api/mid-section-defect/station-options",
     "get_mid_section_defect_station_options", True, None, None),
    ("GET", "/api/mid-section-defect/analysis", "get_mid_section_defect_analysis",
     True, None, "start_date=2024-01-01&end_date=2024-01-07&direction=forward"),
    ("GET", "/api/mid-section-defect/analysis/detail",
     "get_mid_section_defect_analysis_detail", True, None,
     "start_date=2024-01-01&end_date=2024-01-07&direction=forward"),
    ("GET", "/api/mid-section-defect/loss-reasons",
     "get_mid_section_defect_loss_reasons", True, None, None),
    ("GET", "/api/mid-section-defect/export", "get_mid_section_defect_export", True,
     None, "start_date=2024-01-01&end_date=2024-01-07"),
    # ── Analytics ─────────────────────────────────────────────────────────
    ("GET", "/api/analytics/anomaly-summary", "get_analytics_anomaly_summary", True,
     None, None),
    ("GET", "/api/analytics/yield-anomalies", "get_analytics_yield_anomalies", True,
     None, None),
    ("GET", "/api/analytics/reject-spikes", "get_analytics_reject_spikes", True,
     None, None),
    ("GET", "/api/analytics/hold-outliers", "get_analytics_hold_outliers", True,
     None, None),
    ("GET", "/api/analytics/equipment-deviation", "get_analytics_equipment_deviation",
     True, None, None),
    ("GET", "/api/analytics/yield-anomalies/drilldown",
     "get_analytics_yield_anomalies_drilldown", True, None, "query_id=test-id"),
    ("GET", "/api/analytics/reject-spikes/drilldown",
     "get_analytics_reject_spikes_drilldown", True, None, "query_id=test-id"),
    ("GET", "/api/analytics/hold-outliers/drilldown",
     "get_analytics_hold_outliers_drilldown", True, None, "query_id=test-id"),
    ("GET", "/api/analytics/equipment-deviation/drilldown",
     "get_analytics_equipment_deviation_drilldown", True, None, "query_id=test-id"),
    # ── Query Tool ────────────────────────────────────────────────────────
    ("POST", "/api/query-tool/resolve", "post_query_tool_resolve", True,
     {"lot_id": "TEST"}, None),
    ("GET",  "/api/query-tool/lot-history", "get_query_tool_lot_history", True,
     None, "lot_id=TEST"),
    ("GET",  "/api/query-tool/adjacent-lots", "get_query_tool_adjacent_lots", True,
     None, "lot_id=TEST"),
    ("GET",  "/api/query-tool/lot-associations", "get_query_tool_lot_associations",
     True, None, "lot_id=TEST"),
    ("POST", "/api/query-tool/equipment-period", "post_query_tool_equipment_period",
     True, {"equipment_ids": ["TEST"], "start_date": "2024-01-01",
             "end_date": "2024-01-07", "query_type": "lots"}, None),
    ("GET",  "/api/query-tool/equipment-list", "get_query_tool_equipment_list", True,
     None, None),
    ("GET",  "/api/query-tool/workcenter-groups", "get_query_tool_workcenter_groups",
     True, None, None),
    ("POST", "/api/query-tool/lot-equipment-lookup",
     "post_query_tool_lot_equipment_lookup", True,
     {"lot_ids": ["TEST"]}, None),
    ("GET",  "/api/query-tool/equipment-recent-jobs/TEST-EQ-001",
     "get_query_tool_equipment_recent_jobs", True, None, None),
    ("POST", "/api/query-tool/export-csv", "post_query_tool_export_csv", True,
     {"export_type": "lot_history", "lot_id": "TEST"}, None),
    # ── Job Query ─────────────────────────────────────────────────────────
    ("GET",  "/api/job-query/resources", "get_job_query_resources", True, None, None),
    ("POST", "/api/job-query/jobs", "post_job_query_jobs", True,
     {"resource_id": "TEST", "start_date": "2024-01-01", "end_date": "2024-01-07"},
     None),
    ("GET",  "/api/job-query/txn/TEST-JOB-001", "get_job_query_txn", True, None, None),
    ("POST", "/api/job-query/export", "post_job_query_export", True,
     {"resource_id": "TEST", "start_date": "2024-01-01", "end_date": "2024-01-07"},
     None),
    # ── Dashboard ─────────────────────────────────────────────────────────
    ("POST", "/api/dashboard/kpi", "post_dashboard_kpi", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("POST", "/api/dashboard/workcenter_cards", "post_dashboard_workcenter_cards",
     True, {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("POST", "/api/dashboard/detail", "post_dashboard_detail", True,
     {"workcenter": "TEST", "start_date": "2024-01-01", "end_date": "2024-01-07"},
     None),
    ("POST", "/api/dashboard/ou_trend", "post_dashboard_ou_trend", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("POST", "/api/dashboard/utilization_heatmap",
     "post_dashboard_utilization_heatmap", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    # ── AI ────────────────────────────────────────────────────────────────
    ("POST", "/api/ai/query", "post_ai_query", True,
     {"query": "test query"}, None),
    # ── Admin ─────────────────────────────────────────────────────────────
    ("GET",  "/admin/api/system-status", "get_admin_system_status", True, None, None),
    ("GET",  "/admin/api/metrics", "get_admin_metrics", True, None, None),
    ("GET",  "/admin/api/logs", "get_admin_logs", True, None, None),
    ("POST", "/admin/api/logs/cleanup", "post_admin_logs_cleanup", True, None, None),
    ("POST", "/admin/api/log-files/cleanup", "post_admin_log_files_cleanup", True,
     None, None),
    ("GET",  "/admin/api/performance-detail", "get_admin_performance_detail", True,
     None, None),
    ("GET",  "/admin/api/performance-history", "get_admin_performance_history", True,
     None, "start_date=2024-01-01&end_date=2024-01-07"),
    ("POST", "/admin/api/performance-history/purge",
     "post_admin_performance_history_purge", True, None, None),
    ("GET",  "/admin/api/storage-info", "get_admin_storage_info", True, None, None),
    ("POST", "/admin/api/worker/restart", "post_admin_worker_restart", True,
     None, None),
    ("GET",  "/admin/api/worker/status", "get_admin_worker_status", True, None, None),
    ("GET",  "/admin/api/user-usage-kpi", "get_admin_user_usage_kpi", True,
     None, "start_date=2024-01-01&end_date=2024-01-07"),
    ("GET",  "/admin/api/pages", "get_admin_pages", True, None, None),
    ("POST", "/admin/api/analytics/recalculate", "post_admin_analytics_recalculate",
     True, None, None),
    # ── Downtime Analysis ─────────────────────────────────────────────────
    ("GET",  "/api/downtime-analysis/options", "get_downtime_analysis_options", True,
     None, None),
    ("POST", "/api/downtime-analysis/query", "post_downtime_analysis_query", True,
     {"start_date": "2024-01-01", "end_date": "2024-01-07"}, None),
    ("GET",  "/api/downtime-analysis/view", "get_downtime_analysis_view", True,
     None, "query_id=test-id"),
    ("GET",  "/api/downtime-analysis/equipment-detail",
     "get_downtime_analysis_equipment_detail", True, None, "query_id=test-id"),
    ("GET",  "/api/downtime-analysis/event-detail",
     "get_downtime_analysis_event_detail", True, None, "query_id=test-id&page=1"),
    ("GET",  "/api/downtime-analysis/export-equipment-detail",
     "get_downtime_analysis_export_equipment_detail", True, None, "query_id=test-id"),
    ("GET",  "/api/downtime-analysis/export-event-detail",
     "get_downtime_analysis_export_event_detail", True, None, "query_id=test-id"),
    # ── Portal ────────────────────────────────────────────────────────────
    ("GET", "/api/portal/navigation", "get_portal_navigation", True, None, None),
    # ── Material Consumption ──────────────────────────────────────────────
    ("GET",  "/api/material-consumption/filter-options",
     "get_material_consumption_filter_options", True, None, None),
    ("POST", "/api/material-consumption/query", "post_material_consumption_query",
     True, {"material_parts": ["TEST"], "start_date": "2024-01-01",
             "end_date": "2024-01-07", "granularity": "week"}, None),
    ("GET",  "/api/material-consumption/view", "get_material_consumption_view", True,
     None, "query_id=test-id&granularity=week"),
    ("POST", "/api/material-consumption/detail", "post_material_consumption_detail",
     True, {"query_id": "test-id"}, None),
    ("GET",  "/api/material-consumption/detail/page",
     "get_material_consumption_detail_page", True, None,
     "query_id=test-id&page=1"),
    ("GET",  "/api/material-consumption/detail/job/test-job-id",
     "get_material_consumption_detail_job", True, None, None),
    ("POST", "/api/material-consumption/export", "post_material_consumption_export",
     True, {"query_id": "test-id"}, None),
    # ── Query Table ───────────────────────────────────────────────────────
    ("GET",  "/api/get_table_info", "get_get_table_info", True, None, None),
    ("POST", "/api/get_table_columns", "post_get_table_columns", True,
     {"table_name": "TEST_TABLE"}, None),
    ("POST", "/api/query_table", "post_query_table", True,
     {"table_name": "TEST_TABLE"}, None),
    # ── DB Scheduling ─────────────────────────────────────────────────────
    ("GET",  "/api/db-scheduling/queue", "get_db_scheduling_queue", True,
     None, None),
    # ── Production Achievement ───────────────────────────────────────────
    ("GET",  "/api/production-achievement/report", "get_production_achievement_report",
     True, None, "start_date=2026-04-01&end_date=2026-04-02"),
    ("GET",  "/api/production-achievement/filter-options",
     "get_production_achievement_filter_options", True, None, None),
    ("GET",  "/api/production-achievement/targets", "get_production_achievement_targets",
     True, None, None),
    ("PUT",  "/api/production-achievement/targets",
     "put_production_achievement_targets_forbidden", True,
     {"shift_code": "D", "workcenter_group": "切割", "target_qty": 1000}, None),
    ("GET",  "/admin/api/production-achievement/permissions",
     "get_admin_production_achievement_permissions", True, None, None),
    ("PUT",  "/admin/api/production-achievement/permissions/testuser",
     "put_admin_production_achievement_permissions", True,
     {"can_edit_targets": True}, None),
    # ── Production Achievement Overhaul: 10 new endpoints ──────────────────
    ("GET",    "/api/production-achievement/package-lf-map",
     "get_production_achievement_package_lf_map", True, None, None),
    ("PUT",    "/api/production-achievement/package-lf-map",
     "put_production_achievement_package_lf_map_forbidden", True,
     {"raw_package_lf": "SOT23-5L", "merged_group": "SOT23-5L/6L"}, None),
    ("DELETE", "/api/production-achievement/package-lf-map/test-raw-value",
     "delete_production_achievement_package_lf_map_forbidden", True, None, None),
    ("GET",    "/api/production-achievement/workcenter-merge-map",
     "get_production_achievement_workcenter_merge_map", True, None, None),
    ("PUT",    "/api/production-achievement/workcenter-merge-map",
     "put_production_achievement_workcenter_merge_map_forbidden", True,
     {"raw_workcenter_group": "焊接_DW", "merged_workcenter_group": "焊接_WB"}, None),
    ("DELETE", "/api/production-achievement/workcenter-merge-map/test-raw-value",
     "delete_production_achievement_workcenter_merge_map_forbidden", True, None, None),
    ("GET",    "/api/production-achievement/daily-plans",
     "get_production_achievement_daily_plans", True, None, None),
    ("PUT",    "/api/production-achievement/daily-plans",
     "put_production_achievement_daily_plans_forbidden", True,
     {"workcenter_group": "焊接_DB", "package_lf_group": "SOD-123FL", "daily_plan_qty": 300}, None),
    ("GET",    "/api/production-achievement/known-package-lf-values",
     "get_production_achievement_known_package_lf_values", True, None, None),
    ("GET",    "/api/production-achievement/known-workcenter-groups",
     "get_production_achievement_known_workcenter_groups", True, None, None),
]


def _make_key(endpoint_tuple):
    return endpoint_tuple[2]


def _need_admin(key):
    """Return True if the endpoint key is an admin endpoint."""
    if key.startswith(("get_admin_", "post_admin_", "put_admin_",
                        "delete_admin_")):
        return True
    # health/deep also requires admin auth
    if key == "get_health_deep":
        return True
    return False



import re as _re


def _canonical_manifest_key(endpoint_tuple):
    """Build the 'METHOD /canonical-path' manifest key for a captured endpoint."""
    method, url, key = endpoint_tuple[0], endpoint_tuple[1], endpoint_tuple[2]
    path = url.split("?")[0]  # strip query string
    # Replace test placeholder IDs with path-param notation
    path = _re.sub(r"/test-job-id(?=/|$)", "/{job_id}", path)
    path = _re.sub(r"/test-query-id\.parquet", "/{query_id}.parquet", path)
    path = _re.sub(r"/TEST-LOT-001(?=/|$)", "/{lotid}", path)
    path = _re.sub(r"/TEST-EQ-001(?=/|$)", "/{equipment_id}", path)
    path = _re.sub(r"/TEST-JOB-001(?=/|$)", "/{job_id}", path)
    path = _re.sub(r"/TEST(?=/|$)", "/{workcenter}", path)
    path = _re.sub(r"/testuser(?=/|$)", "/{user_identifier}", path)
    path = _re.sub(r"/test-raw-value(?=/|$)", "/{raw}", path)
    return f"{method} {path}"

def capture(client, authenticated_client, admin_client, endpoint_tuple):
    """Capture a single endpoint sample. Returns (body_bytes, status_code)."""
    method, url, key, needs_auth, body, qs = endpoint_tuple

    if qs:
        url = f"{url}?{qs}"

    is_admin_ep = _need_admin(key)

    if is_admin_ep:
        c = admin_client
    elif needs_auth:
        c = authenticated_client
    else:
        c = client

    try:
        if method == "GET":
            resp = c.get(url)
        elif method == "POST":
            resp = c.post(url, json=body or {})
        elif method == "PATCH":
            resp = c.patch(url, json=body or {})
        elif method == "PUT":
            resp = c.put(url, json=body or {})
        elif method == "DELETE":
            resp = c.delete(url)
        else:
            raise ValueError(f"Unknown method: {method}")
    except Exception as exc:
        # Return a synthetic error envelope so the manifest entry still exists
        body_json = {
            "success": False,
            "error": {"code": "CAPTURE_ERROR", "message": str(exc)},
            "meta": {"timestamp": "capture-error"},
        }
        return json.dumps(body_json).encode(), 500

    data = resp.data
    status = resp.status_code

    # Try to decode JSON; if binary (csv/parquet), wrap in a descriptor
    try:
        body_json = resp.get_json(force=True, silent=True)
        if body_json is None:
            # Binary or non-JSON (csv stream, parquet, redirect)
            content_type = resp.headers.get("Content-Type", "")
            if "text/csv" in content_type or resp.status_code == 302:
                # CSV stream or redirect: capture the offline error shape or
                # a synthetic descriptor
                body_json = {
                    "_capture_note": "binary/stream/redirect response",
                    "content_type": content_type,
                    "status_code": status,
                }
            else:
                body_json = {
                    "_capture_note": "non-json response",
                    "content_type": content_type,
                    "status_code": status,
                }
        return json.dumps(body_json).encode(), status
    except Exception:
        return data, status


def main():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    app = create_app("testing")

    manifest = {}

    # Use a single app context to avoid nested context issues
    anon_client = app.test_client()
    auth_client = app.test_client()
    admin_client = app.test_client()

    with app.app_context():
        # Authenticate auth_client
        with anon_client:
            pass  # just initialize

        with app.test_request_context():
            pass  # warm up

    # Re-create clients for actual use
    anon_client = app.test_client()
    auth_client = app.test_client()
    admin_client = app.test_client()

    # Authenticate the auth_client with local credentials
    login_resp = auth_client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpass"},
    )
    if login_resp.status_code not in (200, 401, 429):
        print(
            f"WARNING: login returned {login_resp.status_code}",
            file=sys.stderr,
        )

    # Authenticate admin_client (same user — admin flag from env)
    admin_client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpass"},
    )

    errors = []
    for ep in ENDPOINTS:
        key = ep[2]
        body_bytes, status = capture(
            anon_client, auth_client, admin_client, ep
        )

        sample_path = SAMPLES_DIR / f"{key}.json"
        try:
            # Ensure it's valid JSON
            if isinstance(body_bytes, bytes):
                data_str = body_bytes.decode("utf-8", errors="replace")
            else:
                data_str = str(body_bytes)
            # Re-serialize to normalize formatting
            try:
                parsed = json.loads(data_str)
                out = json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                out = json.dumps({
                    "_capture_note": "raw response (non-json)",
                    "raw": data_str[:2000],
                    "status_code": status,
                }, ensure_ascii=False, indent=2)

            sample_path.write_text(out, encoding="utf-8")

            # Manifest entry — all entries are plain string paths.
            # Schemas describe the full response envelope (success/data/meta or
            # error/meta), so no dataPath drilling is needed; the validator
            # receives the complete captured JSON and validates it directly.
            manifest_key = _canonical_manifest_key(ep)
            manifest[manifest_key] = f"samples/{key}.json"
            print(f"  [{status:3d}] {ep[0]} {ep[1][:60]:<60} → {key}")
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            print(f"  [ERR] {key}: {exc}", file=sys.stderr)

    if errors:
        print(
            f"\n{len(errors)} capture error(s):",
            file=sys.stderr,
        )
        for e in errors:
            print(f"  {e}", file=sys.stderr)

    # Write manifest
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total = len(manifest)
    print(f"\nCapture complete: {total} endpoints → {MANIFEST_PATH}")
    print(f"Samples dir: {SAMPLES_DIR}")

    expected = 158
    if total != expected:
        print(
            f"NOTE: expected {expected} endpoints at plan time; captured {total}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
