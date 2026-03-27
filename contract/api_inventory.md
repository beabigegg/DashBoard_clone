# API Inventory (Governed Source List)

Updated: 2026-03-27

This file is the governed inventory for API contract classification and exception boundaries.

- Included: API entrypoints under `src/mes_dashboard/routes/*.py` and `/api/*` bridge endpoints in `src/mes_dashboard/app.py`
- Excluded: non-API routes, frontend caller logic, static/dist assets

## Endpoint Classification Inventory

### standard-json (must use response helpers and envelope)

| File | Scope |
| :--- | :--- |
| `wip_routes.py` | All JSON API endpoints |
| `dashboard_routes.py` | All JSON API endpoints |
| `hold_routes.py` | All JSON API endpoints |
| `hold_overview_routes.py` | All JSON API endpoints |
| `hold_history_routes.py` | All JSON API endpoints |
| `reject_history_routes.py` | All JSON API endpoints — includes `GET /api/reject-history/job/<job_id>` (async job status); `POST /api/reject-history/query` may return HTTP 202 with `{"async": true, "job_id": ..., "status_url": ...}` when query is enqueued as background job |
| `resource_routes.py` | All JSON API endpoints |
| `resource_history_routes.py` | All JSON API endpoints — `POST /api/resource/history/query` checks canonical base spool first (DuckDB filter at view time, task 7.2); falls through to Oracle path on spool miss; response shape unchanged: `{query_id, summary, detail}` |
| `yield_alert_routes.py` | All JSON API endpoints |
| `production_history_routes.py` | All JSON API endpoints — `POST /api/production-history/query` (primary Oracle query → spool, returns `{dataset_id, detail, matrix, filter_options}`; 400 validation, 503+Retry-After on `heavy_query_overloaded`/`memory_guard_rejected`), `POST /api/production-history/page` (DuckDB paged detail, filter: `{workcenter_group, spec, equipment_id}`; 410 `dataset_expired`), `POST /api/production-history/matrix` (DuckDB matrix with same filter; 410 `dataset_expired`), `POST /api/production-history/options` (DuckDB distinct filter option values; body: `{dataset_id}`; response data: `{work_orders, lot_ids, packages, bop_codes, workcenter_groups, equipment_ids}` each a sorted string array; 410 `dataset_expired`, 503 on memory pressure); gated by `PROD_HISTORY_ENABLED` feature flag |
| `admin_routes.py` | All JSON API endpoints — includes `POST /api/admin/analytics/recalculate` (manual anomaly detection trigger, admin auth required), `GET /admin/api/user-usage-kpi` (user usage KPI dashboard data, admin auth required; query params: `start_date`, `end_date`, `department`) |

### Admin Page Routes (non-API)

| File | Routes | Notes |
| :--- | :--- | :--- |
| `admin_routes.py` | `/admin/performance`, `/admin/user-usage-kpi`, `/admin/dashboard` | Admin-authenticated SPA HTML routes; CSRF token is injected into the served HTML |
| `job_query_routes.py` | All JSON API endpoints |
| `qc_gate_routes.py` | All JSON API endpoints |
| `trace_routes.py` | All JSON API endpoints — includes `GET /api/trace/lineage/job/<job_id>` / `GET /api/trace/lineage/job/<job_id>/result` for generic staged lineage polling; `POST /api/trace/lineage` is async-capable for all staged trace profiles and returns HTTP 202 `{async: true, job_id, status_url, query_id}` on spool miss, while completed lineage results are reused via canonical lineage query id; MSD events route returns `{spool_hit: true, trace_query_id, aggregation}` on canonical spool hit (task 6.2); `trace_query_id` is a stable hash-based canonical query id for MSD result reuse |
| `mid_section_defect_routes.py` | All JSON API endpoints — **compatibility adapter**: `GET /api/mid-section-defect/analysis` (compatibility summary endpoint, internally allowed to route to spool+DuckDB-backed logic but no longer exposes dedicated MSD job polling endpoints); `/analysis/detail` and `/export` accept optional `trace_query_id` param: spool hit uses DuckDB runtime, miss falls through to legacy Oracle path |
| `query_tool_routes.py` | All JSON API endpoints |
| `material_trace_routes.py` | JSON endpoints except CSV export (`/api/material-trace/export`) — `POST /api/material-trace/query` checks spool first (DuckDB page, returns `{rows, pagination, query_hash}`); on spool miss enqueues async RQ job and returns HTTP 202 `{async: true, job_id, status_url, query_hash}`; returns 503+Retry-After if background worker is unavailable; `GET /api/material-trace/job/<job_id>` (async job status polling); `POST /api/material-trace/export` requires `query_hash` from a completed query and streams CSV from DuckDB spool; returns 409 `QUERY_NOT_READY` if spool is not yet available |
| `analytics_routes.py` | All JSON API endpoints — GET /api/analytics/yield-anomalies, GET /api/analytics/reject-spikes, GET /api/analytics/hold-outliers, GET /api/analytics/equipment-deviation, GET /api/analytics/anomaly-summary, GET /api/analytics/yield-anomalies/drilldown, GET /api/analytics/reject-spikes/drilldown, GET /api/analytics/hold-outliers/drilldown, GET /api/analytics/equipment-deviation/drilldown; all gated by ANALYTICS_ANOMALY_DETECTION_ENABLED feature flag |
| `user_auth_routes.py` | `POST /api/auth/login` (public — rate limited, 5/5min; JSON body: `{username, password}`; response data: `{username, displayName, real_name, mail, department, telephoneNumber, is_admin}`), `POST /api/auth/logout` (public — clears session, records logout_time), `GET /api/auth/me` (public — returns `null` if not logged in), `PATCH /api/auth/heartbeat` (login_required — updates last_active) |
| `ai_routes.py` | POST /api/ai/query — natural language query; pipeline selected by AI_MODE env var (`text2sql` default: classify → generate SQL → execute → summarize; `function`: 3-round function call pipeline; `agent`: agentic loop with multi-tool orchestration); request body: `{question}`; response data: `{answer, chart_data, query_used, params_used, suggestions, sql_used, tool_trace, needs_clarification}` — `sql_used` (string\|null) contains the generated SQL, `tool_trace` (array of `{step, function, summary, error?}`) contains execution steps, `needs_clarification` (boolean) indicates whether the AI is asking the user for more information rather than returning a final answer (always `false` for `text2sql` and `function` modes); gated by AI_QUERY_ENABLED feature flag |

### health-exception (keep stable top-level payload; no forced envelope wrapping)

| File | Endpoints | Reason |
| :--- | :--- | :--- |
| `health_routes.py` | `/health`, `/health/deep`, `/health/frontend-shell` | Consumed by monitoring systems and shell health UI |

**Compatibility note (2026-03-11):** `/health` and `/health/deep` responses now include additive `system_memory` (`{total_mb, available_mb, used_pct, pressure}`) and `async_workers` (`{rq_available, workers, queues, slots}`) blocks. These are backward-compatible additions (contract §6.4: additive fields are allowed). `/admin/api/performance-detail` also includes `async_workers` in the response. Monitoring integrations that parse these endpoints by strict schema must be updated if they reject unknown keys.

### stream-download-exception (success can be non-JSON stream; JSON errors still use envelope)

| File | Scope |
| :--- | :--- |
| `job_query_routes.py` | CSV export/stream endpoints |
| `material_trace_routes.py` | CSV trace export endpoints |
| `mid_section_defect_routes.py` | CSV export endpoints |
| `query_tool_routes.py` | CSV export/stream endpoints |
| `reject_history_routes.py` | CSV export endpoints |
| `resource_history_routes.py` | CSV export endpoints |
| `trace_routes.py` | NDJSON stream endpoint (`/api/trace/job/<job_id>/stream`) |
| `spool_routes.py` | `GET /api/spool/{namespace}/{query_id}.parquet` — Parquet binary download; JSON errors use envelope |
| `production_history_routes.py` | `GET /api/production-history/export` — full CSV stream download; JSON errors use envelope |

### legacy-transition (temporary bridge endpoints; retirement pending)

| File | Endpoints | Notes |
| :--- | :--- | :--- |
| `app.py` | `/api/query_table` | Legacy bridge endpoint |
| `app.py` | `/api/get_table_columns` | Legacy bridge endpoint |
| `app.py` | `/api/get_table_info` | Legacy bridge endpoint |
| `app.py` | `/api/portal/navigation` | Legacy bridge endpoint |

## Excluded (Non-API Route Modules)

| File | Reason |
| :--- | :--- |
| `auth_routes.py` | Admin login/logout pages (`/admin/*`), not `/api/*` contract scope |

## Contract Change Checklist

- [ ] Endpoint add/remove/rename/move has been reflected in the correct classification section above.
- [ ] New or changed standard JSON endpoint confirms `success_response(...)` / `error_response(...)` helper usage (no manual `jsonify`).
- [ ] Any exception endpoint update includes reason and compatibility note.
- [ ] Related API tests/contract checks were updated in the same change.

## Synchronization Rule

Any change that adds/removes/renames/moves API endpoints or changes endpoint classification MUST update this inventory in the same change.
