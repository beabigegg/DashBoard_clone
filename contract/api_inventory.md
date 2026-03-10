# API Inventory (Governed Source List)

Updated: 2026-03-11

This file is the governed inventory for API contract classification and exception boundaries.

- Included: API entrypoints under `src/mes_dashboard/routes/*.py` and `/api/*` bridge endpoints in `src/mes_dashboard/app.py`
- Excluded: non-API routes, frontend caller logic, static/dist assets

## Endpoint Classification Inventory

### standard-json (must use response helpers and envelope)

| File | Scope |
| :--- | :--- |
| `wip_routes.py` | All JSON API endpoints |
| `dashboard_routes.py` | All JSON API endpoints |
| `excel_query_routes.py` | JSON endpoints except CSV export (`/export-csv`) |
| `hold_routes.py` | All JSON API endpoints |
| `hold_overview_routes.py` | All JSON API endpoints |
| `hold_history_routes.py` | All JSON API endpoints |
| `reject_history_routes.py` | All JSON API endpoints |
| `resource_routes.py` | All JSON API endpoints |
| `resource_history_routes.py` | All JSON API endpoints |
| `yield_alert_routes.py` | All JSON API endpoints |
| `admin_routes.py` | All JSON API endpoints |
| `job_query_routes.py` | All JSON API endpoints |
| `qc_gate_routes.py` | All JSON API endpoints |
| `trace_routes.py` | All JSON API endpoints |
| `mid_section_defect_routes.py` | All JSON API endpoints |
| `query_tool_routes.py` | All JSON API endpoints |
| `material_trace_routes.py` | JSON endpoints except CSV export (`/api/material-trace/export`) |

### health-exception (keep stable top-level payload; no forced envelope wrapping)

| File | Endpoints | Reason |
| :--- | :--- | :--- |
| `health_routes.py` | `/health`, `/health/deep`, `/health/frontend-shell` | Consumed by monitoring systems and shell health UI |

### stream-download-exception (success can be non-JSON stream; JSON errors still use envelope)

| File | Scope |
| :--- | :--- |
| `excel_query_routes.py` | CSV export endpoints |
| `job_query_routes.py` | CSV export/stream endpoints |
| `material_trace_routes.py` | CSV trace export endpoints |
| `mid_section_defect_routes.py` | CSV export endpoints |
| `query_tool_routes.py` | CSV export/stream endpoints |
| `reject_history_routes.py` | CSV export endpoints |
| `resource_history_routes.py` | CSV export endpoints |
| `trace_routes.py` | NDJSON stream endpoint (`/api/trace/job/<job_id>/stream`) |

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
