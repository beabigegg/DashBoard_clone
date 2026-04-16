## 1. Shared Infrastructure

- [x] 1.1 Add length-guarded `replaceRuntimeHistory` in `core/shell-navigation.js`: measure URL, spill query to sessionStorage under `url-state:<pathname>` when > 2000 chars, write `?_s=1` marker
- [x] 1.2 Add `restoreUrlState()` in `core/shell-navigation.js`: on page load, check for `_s=1`, restore query from sessionStorage, strip marker
- [x] 1.3 Create `core/wip-navigation-state.js`: `storeWipNavigationState(filters, status)`, `loadWipNavigationState()`, `clearWipNavigationState()` with 5-min expiry
- [x] 1.4 Create `core/post-export.js`: `postExport(url, body, filename)` — POST JSON, receive blob, trigger download; handle 410 expiry error

## 2. WIP Overview ↔ Detail Navigation Fix

- [x] 2.1 Fix `wip-overview/App.vue` `navigateToDetail`: call `storeWipNavigationState(filters, activeStatusFilter)`, navigate with only `?workcenter={name}` (+ `&status` if active)
- [x] 2.2 Fix `wip-overview/App.vue` `initializePage`: try `loadWipNavigationState()` first, fall back to URL params
- [x] 2.3 Fix `wip-detail/App.vue` `initializePage`: try `loadWipNavigationState()` for filters, fall back to URL params; `workcenter` always from URL
- [x] 2.4 Fix `wip-detail/App.vue` back link: replace `<a :href="backUrl">` with `<button @click="navigateBack">` using `storeWipNavigationState` + `navigateToRuntimeRoute('/wip-overview')`
- [x] 2.5 Remove unused `backUrl` computed property and `toRuntimeRoute` import from wip-detail

## 3. Export Endpoints — Backend POST Support

- [x] 3.1 Add `POST` method to `resource_history_routes.py` `/export` endpoint (keep GET for backward compat), parse filters from JSON body
- [x] 3.2 Add `POST` method to `reject_history_routes.py` `/api/reject-history/export-cached` endpoint, parse filters from JSON body
- [x] 3.3 Add `POST` method to `production_history_routes.py` `/api/production-history/export` endpoint, parse filters from JSON body

## 4. Export — Frontend POST Migration

- [x] 4.1 Migrate `reject-history/App.vue` `exportCsv` from GET fetch to `postExport()` with JSON body; preserve 410 handling
- [x] 4.2 Migrate `resource-history/App.vue` `exportCsv` from GET `<a>` link to `postExport()` with JSON body
- [x] 4.3 Migrate `production-history/composables/useProductionHistory.js` `buildExportUrl` from GET URL to `postExport()` call

## 5. restoreUrlState Integration

- [x] 5.1 Call `restoreUrlState()` in each native module's entry (`main.js`) before app mount, for all pages using `replaceRuntimeHistory`: wip-overview, wip-detail, hold-overview, hold-detail, hold-history, reject-history, yield-alert-center, resource-history, job-query, query-tool

## 6. E2E Tests

- [x] 6.1 Test: wip-overview multi-select → drilldown to wip-detail → filters arrive correctly → click back → filters preserved on overview (no 400 error)
- [x] 6.2 Test: wip-overview with large filter set → page refresh → state restored from sessionStorage (no 400 error)
- [x] 6.3 Test: hold-overview with many filters → replaceRuntimeHistory spills to sessionStorage → page refresh restores state
- [x] 6.4 Test: reject-history export with large filter set via POST → CSV downloads successfully
- [x] 6.5 Test: resource-history export with many workcenter_groups/families/resource_ids via POST → CSV downloads successfully

## 7. Cleanup & Verification

- [x] 7.1 Remove the previously created but unused `core/wip-navigation-state.js` file (was written in an interrupted session — recreate per spec in task 1.3)
- [x] 7.2 Run full existing E2E test suite to verify no regressions
- [ ] 7.3 Manually verify in browser: wip-overview → select 50+ lotids → drilldown → back → refresh cycle with no errors
