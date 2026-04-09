## 1. Hold Detail Back Navigation Fix

- [x] 1.1 In `frontend/src/hold-detail/App.vue`, change the back link at line 395 from `<a :href="backToOverviewHref">` to `<a :href="backToOverviewHref" @click.prevent="goBackToOverview">` to intercept clicks while preserving href for right-click
- [x] 1.2 Add `goBackToOverview()` function that calls `navigateToRuntimeRoute('/hold-overview')` (import already exists at line 5)
- [x] 1.3 Verify navigation works in portal-shell context (SPA bridge, no full reload)

## 2. Reject History WORKFLOWNAME in DuckDB Mode

- [x] 2.1 In `frontend/src/reject-history/useRejectHistoryDuckDB.js`, add `'WORKFLOWNAME'` to the `detailCols` array in `queryDetail()` (after `'SPECNAME'` at line 208, matching backend column order)
- [x] 2.2 Add row mapping `WORKFLOWNAME: row.WORKFLOWNAME != null ? String(row.WORKFLOWNAME).trim() : null` in the `items` mapper (after `SPECNAME` mapping, around line 231)
- [x] 2.3 Verify WORKFLOW column displays data in reject-history detail table when DuckDB mode is active

## 3. Docker Spool Registration Diagnosis & Fix

- [x] 3.1 Check SQLite log store or `docker logs` for exact "failed to register" error message and exception type
- [x] 3.2 Based on diagnosis, apply the appropriate fix (path creation, cross-device move, Redis availability, or permissions)
- [x] 3.3 Verify spool registration succeeds in Docker container after fix
