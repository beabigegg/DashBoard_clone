## 1. Migration Baseline and Contract Freeze

- [x] 1.1 Refresh migration baseline snapshots for drawer visibility (admin/non-admin), route availability, and critical query contracts.
- [x] 1.2 Build and commit a route parity matrix for all shell-target pages (`/wip-overview`, `/wip-detail`, `/hold-overview`, `/hold-detail`, `/hold-history`, `/resource`, `/resource-history`, `/qc-gate`, `/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`).
- [x] 1.3 Freeze migration contract doc: route id, render mode (`native|wrapper`), required query keys, owner, rollback strategy.
- [x] 1.4 Add contract validation for missing route definitions, duplicated mappings, and invalid render mode declarations.
- [x] 1.5 Capture pre-migration baseline evidence for each target page: table schema/sort/pagination, chart series/legend/tooltip, filter combinations, matrix selection states.

## 2. Shell Route-View Architecture Hardening

- [x] 2.1 Replace `PageBridgeView`-only routing with explicit shell render-mode registry (`native` component host, `wrapper` host).
- [x] 2.2 Implement deterministic dynamic route registration from backend drawer payload + local render-mode registry.
- [x] 2.3 Add unknown/hidden route fallback behavior (safe redirect + non-intrusive user notice).
- [x] 2.4 Ensure breadcrumb/title metadata resolves from route contracts for both native and wrapper modes.
- [x] 2.5 Add integration tests for router registration, fallback routing, and render-mode resolution.

## 3. Drawer Governance and Admin Entry Consistency

- [x] 3.1 Align drawer ordering and page ordering logic between backend navigation payload and shell rendering.
- [x] 3.2 Enforce deterministic filtering for `admin_only` drawers/pages in shell UI and router guards.
- [x] 3.3 Ensure admin entry points (`/admin/pages`, login/logout links) are visible and reachable under expected auth states.
- [x] 3.4 Add contract tests for drawer parity against baseline snapshots (admin and non-admin).
- [x] 3.5 Add diagnostics/logging for drawer-route mismatch events and invalid navigation payloads.

## 4. Health Check Summary/Detail UX Completion

- [x] 4.1 Refactor shell health widget to summary-first header presentation (status dot + concise text only).
- [x] 4.2 Keep detailed health diagnostics behind explicit interaction (click/toggle panel or modal).
- [x] 4.3 Ensure detail panel supports close-on-outside-click, keyboard escape, and stable focus behavior.
- [x] 4.4 Refine `/health/frontend-shell` contract to separate summary fields from detailed diagnostics payload.
- [x] 4.5 Add tests for healthy/degraded/unhealthy summary transitions and endpoint failure fallback behavior.

## 5. Native Route-View Integration Wave A (Already-Rewritten Pages)

- [x] 5.1 Integrate `/wip-overview` as native shell route-view and verify filter/query URL sync behavior.
- [x] 5.2 Integrate `/wip-detail` as native shell route-view and verify detail/list back-navigation query continuity.
- [x] 5.3 Integrate `/hold-overview` and `/hold-detail` as native shell route-views with reason/type query parity.
- [x] 5.4 Integrate `/hold-history` as native shell route-view with date/record-type filter parity.
- [x] 5.5 Integrate `/resource` and `/resource-history` as native shell route-views with summary/detail/export parity.
- [x] 5.6 Integrate `/qc-gate` as native shell route-view with chart-table linked interactions preserved.
- [x] 5.7 Add route-level smoke tests for Wave A pages in shell context (render, query, refresh, navigation).
- [x] 5.8 Add chart lifecycle checks for Wave A (route enter/re-enter, resize, tooltip, linked-highlight stability).

## 6. Wrapper Stabilization Wave B (Before Rewrite)

- [x] 6.1 Keep wrapper-mode operability for `/job-query` with query/search/export smoke coverage.
- [x] 6.2 Keep wrapper-mode operability for `/excel-query` with upload/detect/query/export smoke coverage.
- [x] 6.3 Keep wrapper-mode operability for `/query-tool` with resolve/history/association workflows.
- [x] 6.4 Keep wrapper-mode operability for `/tmtt-defect` with range query and CSV export workflow.
- [x] 6.5 Instrument wrapper telemetry for load success/error/latency and fallback usage count.
- [x] 6.6 Define per-page rewrite entry criteria and block native cutover when criteria are incomplete.

## 7. Wrapper-to-Native Rewrite Completion (Full Migration Target)

- [x] 7.1 Rewrite `/tmtt-defect` as canonical native shell route-view module using shared UI/composables.
- [x] 7.2 Rewrite `/job-query` as native shell route-view module with workflow parity and no wrapper dependency.
- [x] 7.3 Rewrite `/excel-query` as native shell route-view module with upload-query-export parity.
- [x] 7.4 Rewrite `/query-tool` as native shell route-view module with full workflow parity.
- [x] 7.5 Replace wrapper mapping with native mapping in shell route registry for all Wave B pages.
- [x] 7.6 Decommission wrapper runtime paths and remove wrapper-only fallback code once parity gates pass.
- [x] 7.7 Validate table/chart/filter/matrix parity for each rewritten Wave B page before marking rewrite complete.

## 8. Per-Page Rewrite Smoke Acceptance (Mandatory)

- [x] 8.1 Build a smoke checklist artifact per rewritten page (entry path, required query params, key interaction, error path, export path).
- [x] 8.2 Execute and record smoke evidence for Wave A native pages under shell route-view.
- [x] 8.3 Execute and record smoke evidence for Wave B rewritten pages before wrapper decommission.
- [x] 8.4 Block release when any page lacks complete smoke evidence or has unresolved critical failures.
- [x] 8.5 Extend smoke checklist fields to include mandatory table/chart/filter/interaction/matrix checkpoints and expected outcomes.
- [x] 8.6 Add explicit zero-value and empty-state checks for KPI/table/matrix rendering parity.

## 9. Test and Quality Gate Enforcement

- [x] 9.1 Extend backend tests for `/api/portal/navigation` contract parity (drawer/page ordering, visibility, admin metadata).
- [x] 9.2 Extend shell frontend tests for route-mode rendering, health summary/detail behavior, and admin entry visibility.
- [x] 9.3 Add regression tests ensuring no iframe elements are used for shell page content paths.
- [x] 9.4 Add contract tests for route/query compatibility across list-detail workflows.
- [x] 9.5 Add cutover gate tests validating G1-G7 readiness signals and failure-block semantics.
- [x] 9.6 Add table parity tests (column keys/types/order, sorting semantics, pagination continuity).
- [x] 9.7 Add chart parity tests (series key/type, legend toggles, tooltip behavior, chart-table linked scope).
- [x] 9.8 Add matrix interaction tests (selection/highlight persistence, drill behavior, filter-linked state transitions).
- [x] 9.9 Add visual regression snapshots for critical chart/table/matrix states and block on critical diffs.

## 10. Rollout, Rollback, and Operations

- [x] 10.1 Define phased rollout plan for shell route-view cutover (canary scope, thresholds, hold points).
- [x] 10.2 Rehearse rollback playbook for both full rollback and page-level partial rollback.
- [x] 10.3 Define kill-switch operation for quickly reverting affected pages while keeping shell accessible.
- [x] 10.4 Capture migration observability dashboard/report for route errors, health regressions, and wrapper fallback usage.

## 11. Cleanup and Closure

- [x] 11.1 Remove obsolete `PageBridgeView` redirect-only logic after all pages are native-integrated.
- [x] 11.2 Remove wrapper-specific code, flags, and stale docs after verified decommission.
- [x] 11.3 Update migration docs/spec references to reflect completed no-iframe full migration state.
- [x] 11.4 Run final parity audit and archive-readiness checklist before change closure.
- [x] 11.5 Produce final pre/post parity report summarizing page-by-page outcomes for table/chart/filter/interaction/matrix.
