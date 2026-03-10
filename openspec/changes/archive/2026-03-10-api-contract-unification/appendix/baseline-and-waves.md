# API Contract Unification — Baseline & Wave Registry

## 1. Endpoint Classification Inventory

### standard-json (migration scope)
| File | Endpoints |
|------|-----------|
| `wip_routes.py` | `/api/wip/overview/summary`, `/api/wip/overview/matrix`, `/api/wip/overview/hold`, `/api/wip/detail/<wc>`, `/api/wip/lot/<lotid>`, `/api/wip/meta/workcenters`, `/api/wip/meta/packages`, `/api/wip/meta/filter-options`, `/api/wip/meta/search` |
| `dashboard_routes.py` | All dashboard API endpoints |
| `hold_routes.py` | All hold API endpoints |
| `hold_overview_routes.py` | All hold overview API endpoints |
| `hold_history_routes.py` | All hold history JSON endpoints |
| `reject_history_routes.py` | All reject history JSON endpoints |
| `resource_routes.py` | All resource API endpoints |
| `resource_history_routes.py` | All resource history JSON endpoints |
| `yield_alert_routes.py` | All yield alert JSON endpoints |
| `admin_routes.py` | All admin API endpoints |
| `job_query_routes.py` | All job query JSON endpoints |
| `qc_gate_routes.py` | All qc gate API endpoints |
| `trace_routes.py` | All trace API endpoints |
| `mid_section_defect_routes.py` | All mid-section defect JSON endpoints |
| `query_tool_routes.py` | All query tool JSON endpoints |

### health-exception (contract exception — DO NOT envelope)
| File | Endpoints | Reason |
|------|-----------|--------|
| `health_routes.py` | `/health`, `/health/deep`, `/health/frontend-shell` | Consumed by monitoring systems and shell health UI; top-level structure is stable contract |

### stream-download-exception (success = non-JSON stream, errors = envelope)
| File | Endpoints |
|------|-----------|
| `excel_query_routes.py` | CSV export endpoints |
| `job_query_routes.py` | CSV streaming endpoints |
| `material_trace_routes.py` | CSV trace export endpoints |
| `mid_section_defect_routes.py` | CSV export endpoints |
| `query_tool_routes.py` | CSV streaming export endpoints |
| `reject_history_routes.py` | CSV export endpoints |
| `resource_history_routes.py` | CSV export endpoints |

### legacy-transition (app.py bridge, governance in progress)
| File | Endpoints | Transition Strategy |
|------|-----------|---------------------|
| `app.py` | `/api/query_table` | Retain for now; document as temporary exception; add envelope in Phase D |
| `app.py` | `/api/get_table_columns` | Same as above |
| `app.py` | `/api/get_table_info` | Same as above |
| `app.py` | `/api/portal/navigation` | Same as above |

---

## 2. Migration Baseline Report (as of Wave A start)

### Manual `jsonify` call counts
| File | `jsonify` count |
|------|----------------|
| `wip_routes.py` | 25 |
| `admin_routes.py` | 36 |
| `dashboard_routes.py` | 11 |
| `excel_query_routes.py` | 39 |
| `hold_history_routes.py` | 12 |
| `hold_overview_routes.py` | 14 |
| `hold_routes.py` | 11 |
| `job_query_routes.py` | 19 |
| `material_trace_routes.py` | 12 |
| `mid_section_defect_routes.py` | 13 |
| `qc_gate_routes.py` | 3 |
| `query_tool_routes.py` | 55 |
| `reject_history_routes.py` | 66 |
| `resource_history_routes.py` | 12 |
| `resource_routes.py` | 25 |
| `trace_routes.py` | 14 |
| `yield_alert_routes.py` | 54 |
| `app.py` (legacy) | 8 |
| **TOTAL** | **429** |

### Old-style string error responses (`'error': '...'` string format)
Routes still emitting `{"success": false, "error": "<string>"}`:
- `wip_routes.py`: 9 occurrences (all to be fixed in Wave A)
- `hold_history_routes.py`: includes `cache_expired` signal
- `reject_history_routes.py`: includes `cache_miss` and `cache_expired` signals
- `resource_history_routes.py`: includes `cache_expired` signal
- `yield_alert_routes.py`: includes `cache_expired` signal
- Many others across all routes files

### Cache signal strings (special flow-control errors)
The following string signals are used as flow control in frontend:
- `"cache_expired"` — used in hold_history, reject_history, resource_history, yield_alert
- `"cache_miss"` — used in reject_history

These will be migrated to error codes (`CACHE_EXPIRED`, `CACHE_MISS`) in Wave C/D, after backend + frontend are updated together.

---

## 3. Migration Waves

### Wave A: `wip_routes.py` (current change)
**Scope**: `src/mes_dashboard/routes/wip_routes.py`
**Acceptance criteria**:
- Zero manual `jsonify` calls in `wip_routes.py`
- All success responses via `success_response(...)`
- All error responses via `validation_error(...)` / `not_found_error(...)` / `internal_error(...)`
- Tests updated to verify new `error.code`/`error.message` envelope
- Frontend `api.js` verified to handle both old and new error format (backward compatible)
- No regression in admin/portal/report pages

### Wave B: High-flow standard-JSON routes
**Recommended order**:
1. `resource_routes.py` (25 jsonify)
2. `dashboard_routes.py` (11 jsonify)
3. `hold_routes.py` + `hold_overview_routes.py` (11+14 jsonify)
**Wave B start condition**: Wave A tests green, no frontend regression reported.

### Wave C: Cache-signal routes + frontend migration
**Scope**: Routes emitting `cache_expired`/`cache_miss` + corresponding frontend pages
**Notes**: Requires coordinated frontend + backend change in same PR.
**Start condition**: CACHE_EXPIRED / CACHE_MISS error codes added to response.py (done in Wave A baseline).

### Wave D: Legacy bridge + remaining routes
**Scope**: `reject_history_routes.py`, `yield_alert_routes.py`, `query_tool_routes.py`, `admin_routes.py`, app.py legacy APIs
**Start condition**: Wave B complete, Wave C complete.

---

## 4. Rollback Points
- Wave A rollback unit: `wip_routes.py` + `tests/test_wip_routes.py`
- If frontend error parsing breaks, revert `wip_routes.py` to pre-Wave A state (tracked in git)
- Health endpoints are not touched and cannot regress
