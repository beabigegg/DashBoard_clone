# -*- coding: utf-8 -*-
"""Route contract matrix for envelope runtime sweep.

Each entry describes one route:
  (endpoint_pattern, method, sample_params, expected_data_shape)

`expected_data_shape` values:
  'envelope'  — standard { success, data, meta } JSON response
  'error'     — standard { success:false, error, meta } JSON response
  'streaming' — CSV / NDJSON / file streaming response (not envelope)
  'non_json'  — HTML / redirect / binary

`sample_params` is a dict passed as query-string (GET) or JSON body (POST).
Use None when no params are required.

`SKIP_RUNTIME_SWEEP` lists routes (by endpoint_pattern) that cannot be called
in isolation via test_client (e.g. require complex session state or live DB).
These must be covered by dedicated per-feature tests instead.

`NON_ENVELOPED_ENDPOINTS` lists routes whose successful responses intentionally
do NOT use the standard success/data/meta envelope (health, streaming, HTML).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Non-envelope endpoints (intentionally outside the standard envelope)
# ---------------------------------------------------------------------------

NON_ENVELOPED_ENDPOINTS: list[str] = [
    "/health",
    "/health/deep",
    "/health/frontend-shell",
    "/api/spool/<namespace>/<query_id>.parquet",
    "/api/reject-history/export",
    "/api/reject-history/export-cached",
    "/api/production-history/export",
    "/api/resource/history/export",
    "/api/mid-section-defect/export",
    "/api/trace/job/<job_id>/stream",
    # Portal navigation uses direct jsonify (not migrated to envelope yet)
    "/api/portal/navigation",
]

# ---------------------------------------------------------------------------
# Routes that must be skipped during automated runtime sweep
# (require live Oracle/Redis, complex auth, or binary response)
# ---------------------------------------------------------------------------

SKIP_RUNTIME_SWEEP: list[str] = [
    # Requires live Oracle DB queries
    "/api/dashboard/detail",
    "/api/dashboard/kpi",
    "/api/dashboard/ou_trend",
    "/api/dashboard/utilization_heatmap",
    "/api/dashboard/workcenter_cards",
    "/api/get_table_info",
    "/api/get_table_columns",
    "/api/query_table",
    # Admin-only routes requiring admin session
    "/admin",
    # Async job result endpoints (job_id must exist)
    "/api/reject-history/job/<job_id>",
    "/api/production-history/job/<job_id>",
    "/api/material-trace/job/<job_id>",
    "/api/yield-alert/job/<job_id>",
    "/api/trace/job/<job_id>",
    "/api/trace/job/<job_id>/result",
    "/api/trace/lineage/job/<job_id>",
    "/api/trace/lineage/job/<job_id>/result",
    "/api/job-query/txn/<job_id>",
    # Streaming endpoints
    "/api/trace/job/<job_id>/stream",
    "/api/spool/<namespace>/<query_id>.parquet",
    # Export streaming (CSV)
    "/api/reject-history/export",
    "/api/reject-history/export-cached",
    "/api/production-history/export",
    "/api/resource/history/export",
    "/api/mid-section-defect/export",
    "/api/query-tool/export-csv",
]

# ---------------------------------------------------------------------------
# Route contract matrix
# Format: (endpoint_pattern, method, sample_params_or_body, expected_shape)
# ---------------------------------------------------------------------------

ROUTE_CONTRACT_MATRIX: list[tuple[str, str, dict | None, str]] = [
    # ---- Auth ----
    ("/api/auth/me", "GET", None, "envelope"),
    ("/api/auth/login", "POST", {"username": "testuser", "password": "wrong"}, "envelope"),
    ("/api/auth/logout", "POST", None, "envelope"),
    ("/api/auth/heartbeat", "PATCH", None, "envelope"),

    # ---- Portal navigation ----
    ("/api/portal/navigation", "GET", None, "non_json"),  # uses direct jsonify, not envelope

    # ---- WIP overview ----
    ("/api/wip/overview/summary", "GET", None, "envelope"),
    ("/api/wip/overview/matrix", "GET", {"status": "WIP"}, "envelope"),
    ("/api/wip/overview/hold", "GET", None, "envelope"),
    ("/api/wip/meta/filter-options", "GET", None, "envelope"),
    ("/api/wip/meta/packages", "GET", None, "envelope"),
    ("/api/wip/meta/workcenters", "GET", None, "envelope"),
    ("/api/wip/meta/search", "GET", {"q": "TEST"}, "envelope"),
    ("/api/wip/lot/<lotid>", "GET", None, "envelope"),  # 404 for fake lot — still envelope

    # ---- WIP detail ----
    ("/api/wip/detail/<workcenter>", "GET", None, "envelope"),
    ("/api/wip/hold-detail/summary", "GET", None, "envelope"),
    ("/api/wip/hold-detail/lots", "GET", None, "envelope"),
    ("/api/wip/hold-detail/distribution", "GET", None, "envelope"),

    # ---- Hold overview ----
    ("/api/hold-overview/summary", "GET", None, "envelope"),
    ("/api/hold-overview/matrix", "GET", None, "envelope"),
    ("/api/hold-overview/treemap", "GET", None, "envelope"),
    ("/api/hold-overview/lots", "GET", None, "envelope"),

    # ---- Hold history ----
    ("/api/hold-history/query", "POST", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, "envelope"),
    ("/api/hold-history/view", "GET", {"query_id": "nonexistent"}, "envelope"),

    # ---- Reject history ----
    ("/api/reject-history/options", "GET", None, "envelope"),
    ("/api/reject-history/query", "POST", {"start_date": "2024-01-01", "end_date": "2024-01-03"}, "envelope"),
    ("/api/reject-history/count", "GET", {"query_id": "test-id"}, "envelope"),
    ("/api/reject-history/list", "GET", {"query_id": "test-id"}, "envelope"),
    ("/api/reject-history/summary", "GET", {"query_id": "test-id"}, "envelope"),
    ("/api/reject-history/trend", "GET", {"query_id": "test-id"}, "envelope"),
    ("/api/reject-history/analytics", "GET", {"query_id": "test-id"}, "envelope"),
    ("/api/reject-history/reason-pareto", "GET", {"query_id": "test-id"}, "envelope"),
    ("/api/reject-history/batch-pareto", "GET", None, "envelope"),
    ("/api/reject-history/view", "GET", None, "envelope"),

    # ---- Production history ----
    ("/api/production-history/type-options", "GET", None, "envelope"),
    ("/api/production-history/options", "POST", {}, "envelope"),
    ("/api/production-history/query", "POST", {"start_date": "2024-01-01", "end_date": "2024-01-03"}, "envelope"),
    ("/api/production-history/count", "GET", {"start_date": "2024-01-01", "end_date": "2024-01-03"}, "envelope"),
    ("/api/production-history/page", "POST", {}, "envelope"),
    ("/api/production-history/matrix", "POST", {}, "envelope"),

    # ---- Resource ----
    ("/api/resource/by_status", "GET", None, "envelope"),
    ("/api/resource/by_workcenter", "GET", None, "envelope"),
    ("/api/resource/filter_options", "GET", None, "envelope"),
    ("/api/resource/status", "GET", None, "envelope"),
    ("/api/resource/status/summary", "GET", None, "envelope"),
    ("/api/resource/status/matrix", "GET", None, "envelope"),
    ("/api/resource/status/options", "GET", None, "envelope"),
    ("/api/resource/status_values", "GET", None, "envelope"),
    ("/api/resource/workcenter_status_matrix", "GET", None, "envelope"),

    # ---- Resource history ----
    ("/api/resource/history/options", "GET", None, "envelope"),
    ("/api/resource/history/query", "POST", {"start_date": "2024-01-01", "end_date": "2024-01-03"}, "envelope"),
    ("/api/resource/history/page", "GET", None, "envelope"),
    ("/api/resource/history/view", "GET", None, "envelope"),

    # ---- Yield alert ----
    ("/api/yield-alert/filter-options", "GET", None, "envelope"),
    ("/api/yield-alert/query", "POST", {"start_date": "2024-01-01", "end_date": "2024-01-03"}, "envelope"),
    ("/api/yield-alert/alerts", "GET", None, "envelope"),
    ("/api/yield-alert/summary", "GET", None, "envelope"),
    ("/api/yield-alert/trend", "GET", None, "envelope"),
    ("/api/yield-alert/view", "GET", None, "envelope"),
    ("/api/yield-alert/drilldown-context", "GET", None, "envelope"),
    ("/api/yield-alert/reason-detail", "GET", None, "envelope"),
    ("/api/yield-alert/analyze", "POST", {}, "envelope"),

    # ---- Material trace ----
    ("/api/material-trace/filter-options", "GET", None, "envelope"),
    ("/api/material-trace/query", "POST", {}, "envelope"),

    # ---- Trace / lineage ----
    ("/api/trace/lineage", "POST", {}, "envelope"),
    ("/api/trace/events", "POST", {}, "envelope"),
    ("/api/trace/seed-resolve", "POST", {}, "envelope"),

    # ---- Query tool ----
    ("/api/query-tool/workcenter-groups", "GET", None, "envelope"),
    ("/api/query-tool/equipment-list", "GET", None, "envelope"),
    ("/api/query-tool/lot-history", "GET", None, "envelope"),
    ("/api/query-tool/adjacent-lots", "GET", None, "envelope"),
    ("/api/query-tool/resolve", "POST", {}, "envelope"),
    ("/api/query-tool/equipment-period", "POST", {}, "envelope"),
    ("/api/query-tool/lot-associations", "GET", None, "envelope"),
    ("/api/query-tool/lot-equipment-lookup", "POST", {}, "envelope"),

    # ---- Job query ----
    ("/api/job-query/resources", "GET", None, "envelope"),
    ("/api/job-query/jobs", "POST", {}, "envelope"),

    # ---- Mid-section defect ----
    ("/api/mid-section-defect/station-options", "GET", None, "envelope"),
    ("/api/mid-section-defect/loss-reasons", "GET", None, "envelope"),
    ("/api/mid-section-defect/analysis", "GET", None, "envelope"),
    ("/api/mid-section-defect/analysis/detail", "GET", None, "envelope"),

    # ---- QC Gate ----
    ("/api/qc-gate/summary", "GET", None, "envelope"),

    # ---- Analytics ----
    ("/api/analytics/anomaly-summary", "GET", None, "envelope"),
    ("/api/analytics/yield-anomalies", "GET", None, "envelope"),
    ("/api/analytics/reject-spikes", "GET", None, "envelope"),
    ("/api/analytics/hold-outliers", "GET", None, "envelope"),
    ("/api/analytics/equipment-deviation", "GET", None, "envelope"),
    ("/api/analytics/yield-anomalies/drilldown", "GET", None, "envelope"),
    ("/api/analytics/reject-spikes/drilldown", "GET", None, "envelope"),
    ("/api/analytics/hold-outliers/drilldown", "GET", None, "envelope"),
    ("/api/analytics/equipment-deviation/drilldown", "GET", None, "envelope"),

    # ---- AI ----
    ("/api/ai/query", "POST", {"message": "test"}, "envelope"),

    # ---- Health (non-envelope) ----
    ("/health", "GET", None, "non_json"),
    ("/health/deep", "GET", None, "non_json"),
    ("/health/frontend-shell", "GET", None, "non_json"),
]
