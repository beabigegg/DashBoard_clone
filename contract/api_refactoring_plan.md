# MES Dashboard — API Contract Migration Plan (v2.0)

> Updated by: api-contract-unification change (openspec/changes/api-contract-unification)
> Previous version: v1.0 (single-task plan)

---

## 1. Target State

All standard JSON API endpoints SHALL return the unified response envelope defined in
`api_development_contract.md`:

```json
// Success
{ "success": true, "data": <payload>, "meta": { "timestamp": "<iso>" } }

// Error
{ "success": false, "error": { "code": "<ERROR_CODE>", "message": "<human>" }, "meta": { "timestamp": "<iso>" } }
```

Helpers in `src/mes_dashboard/core/response.py` MUST be used for all standard endpoints.
Manual `jsonify(...)` calls are prohibited in the `standard-json` migration scope.

---

## 2. Endpoint Classification

| Class | Description | Contract Rule |
|-------|-------------|---------------|
| `standard-json` | Regular JSON API endpoints (all `*_routes.py` except health) | Must use envelope helpers |
| `health-exception` | `/health`, `/health/deep`, `/health/frontend-shell` | Keep top-level payload; NO envelope wrapping |
| `stream-download-exception` | CSV/NDJSON/file streaming endpoints | Success: keep stream; Error responses: use envelope |
| `legacy-transition` | `app.py` inline APIs (`/api/query_table`, etc.) | Documented as temporary exceptions; retire in Wave D |

---

## 3. Migration Waves

### Wave A — `wip_routes.py` ✅ COMPLETE

**Files changed:**
- `src/mes_dashboard/routes/wip_routes.py` — all 25 `jsonify` calls replaced with helpers
- `src/mes_dashboard/core/response.py` — added `CACHE_EXPIRED`, `CACHE_MISS` error codes + helpers
- `tests/test_wip_routes.py` — updated assertions to verify `error.code`/`error.message` envelope
- `tests/test_api_contract.py` — new contract guardrail tests (zero-jsonify, baseline regression, envelope shape, health exception)
- `src/mes_dashboard/routes/health_routes.py` — added contract exception notation

**Acceptance criteria met:**
- [x] Zero manual `jsonify` in `wip_routes.py`
- [x] All success responses via `success_response(...)`
- [x] All error responses via `validation_error(...)` / `not_found_error(...)` / `internal_error(...)`
- [x] Health endpoints protected with exception notation and contract tests
- [x] Rate-limit 429 already uses error envelope (via `rate_limit.py`)
- [x] Frontend `api.js` backward-compatible (handles both old string and new object error formats)
- [x] No regression in pages not using wip routes

---

### Wave B — High-flow standard-JSON routes (planned)

**Recommended order:** `resource_routes.py` → `dashboard_routes.py` → `hold_routes.py` + `hold_overview_routes.py`

**Start condition:** Wave A tests green, no frontend regression.

**Each file requires:**
1. Replace `jsonify({'success': True, 'data': ...})` → `success_response(...)`
2. Replace `jsonify({'success': False, 'error': '...'})` → `validation_error/not_found_error/internal_error`
3. Update corresponding tests
4. Update `_JSONIFY_BASELINE` in `test_api_contract.py` to reflect new lower counts

---

### Wave C — Cache-signal routes + coordinated frontend migration (planned)

**Scope:** Routes emitting `cache_expired`/`cache_miss` string signals:
- `hold_history_routes.py`
- `reject_history_routes.py`
- `resource_history_routes.py`
- `yield_alert_routes.py`

**Frontend pages to update simultaneously:**
- `frontend/src/reject-history/App.vue` — lines checking `resp?.error === 'cache_miss'` / `'cache_expired'`
- `frontend/src/hold-history/App.vue`
- `frontend/src/resource-history/App.vue`
- `frontend/src/yield-alert-center/App.vue`

**Migration:** Replace `{"error": "cache_expired"}` → use `cache_expired_error()` helper (code: `CACHE_EXPIRED`).
Frontend must switch string comparison to `error.errorCode === 'CACHE_EXPIRED'`.

**Start condition:** Wave B complete.

---

### Wave D — Legacy bridge APIs + remaining routes (planned)

**Scope:**
- `reject_history_routes.py`, `yield_alert_routes.py`, `query_tool_routes.py`, `admin_routes.py`
- `app.py` inline APIs: `/api/query_table`, `/api/get_table_columns`, `/api/get_table_info`, `/api/portal/navigation`

**Start condition:** Wave C complete.

---

## 4. Helper Quick Reference

See `src/mes_dashboard/core/response.py` module docstring for the full usage guide.

| Scenario | Helper |
|----------|--------|
| Success | `success_response(data)` |
| Validation / bad params | `validation_error(message)` |
| Not found | `not_found_error(message)` |
| Internal error | `internal_error(details)` |
| DB down | `db_connection_error(details)` |
| Rate limit | `too_many_requests_error()` |
| Cache expired | `cache_expired_error(details)` |
| Cache miss | `cache_miss_error(details)` |

---

## 5. Guardrails

- `tests/test_api_contract.py::TestWipRoutesContractCompliance` — zero jsonify in `wip_routes.py`
- `tests/test_api_contract.py::TestJsonifyBaselineRegression` — total jsonify count must not exceed baseline
- `tests/test_api_contract.py::TestHealthEndpointContractException` — health endpoints must NOT use envelope
- `tests/test_api_contract.py::TestStandardJsonEnvelopeShape` — success/error envelope shape verified

---

## 6. Rollback Strategy

- Each wave = one git commit group (route file + tests + frontend if applicable)
- Revert a wave by reverting its commit group
- Health endpoints are never touched; they cannot regress from this migration
