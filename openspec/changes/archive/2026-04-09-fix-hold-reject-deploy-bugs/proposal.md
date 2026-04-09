## Why

Three active bugs are impacting usability and deployment:
1. Hold detail's back button navigates to WIP overview instead of Hold overview, breaking the drill-down → return flow.
2. Reject history detail table shows blank WORKFLOW column when DuckDB-WASM mode is active (datasets ≥ 5,000 rows), because the frontend DuckDB query omits `WORKFLOWNAME`.
3. Docker deployment fails with "failed to register..." errors, suspected to be a DuckDB/spool path resolution issue in the container environment.

## What Changes

- **Bug 1 — Hold detail back navigation**: Investigate and fix the back-to-overview link in `hold-detail/App.vue`. The current implementation uses `<a :href="backToOverviewHref">` with `toRuntimeRoute('/hold-overview')` (line 136). In portal-shell SPA context, this causes a full page reload instead of using the shell router bridge (`navigateToRuntimeRoute`). During reload, if route resolution timing or fallback logic misdirects, the user lands on WIP overview (the default first drawer page). Fix: convert to programmatic navigation via `navigateToRuntimeRoute` or add a click handler that uses the bridge.
- **Bug 2 — Reject history WORKFLOWNAME missing in DuckDB mode**: Add `WORKFLOWNAME` to the `detailCols` array in `useRejectHistoryDuckDB.js` `queryDetail()` (line 206) and include it in the row mapping (line 225). The backend `reject_cache_sql_runtime.py` (line 789) already includes this column, and the parquet spool file contains it — only the frontend DuckDB SQL omits it.
- **Bug 3 — Docker "failed to register" error**: Investigate the `register_spool_file` failure path in `query_spool_store.py:509` and `spool_pipeline.py:109/137`. Check MySQL/SQLite logs via admin dashboard. Likely causes: spool directory path not writable in Docker, Redis unavailable at container startup, or DuckDB temp directory missing. Verify `QUERY_SPOOL_DIR` (`tmp/query_spool`) resolves correctly inside container and that Dockerfile `mkdir` covers all required paths.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
_(none — these are bug fixes within existing capabilities, no spec-level requirement changes)_

## Impact

- **Frontend**: `frontend/src/hold-detail/App.vue` (back navigation), `frontend/src/reject-history/useRejectHistoryDuckDB.js` (detail query columns)
- **Infrastructure**: `Dockerfile`, `supervisord.conf`, `src/mes_dashboard/core/query_spool_store.py`, `src/mes_dashboard/core/spool_pipeline.py`
- **No API changes**: All fixes are within existing components
- **No breaking changes**: All fixes are backwards-compatible
