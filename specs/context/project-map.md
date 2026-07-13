---
artifact: project-map
generated-by: cdd-kit context-scan
schema-version: 1
root: DashBoard_clone
visible-dirs: 193
visible-files: 1017
omitted-dirs: 67
truncated-dirs: 5
inputs-digest: 58ec80699f498bf40074f81de6138b321f2d3ecc03137b33052a2dd7345722a2
---

# Project Map

Use this deterministic map to choose candidate context paths before reading files.

## Excluded Paths
- .claude
- .git
- node_modules
- dist
- build
- assets
- specs/archive
- specs/changes
- .cdd/.refresh-backup
- .cdd/migrate-backup
- .cdd/runtime
- .claude/worktrees

## Tree

```
DashBoard_clone/
|-- .cdd/
|   |-- code-graph.index.json
|   |-- code-map.index.json
|   |-- code-map.yml
|   |-- conformance.json
|   |-- context-policy.json
|   |-- model-policy.json
|   \-- tier-policy.json
|-- .github/
|   \-- workflows/
|       |-- backend-tests.yml
|       |-- contract-driven-gates.yml
|       |-- e2e-tests.yml
|       |-- frontend-tests.yml
|       |-- measure-stability.yml
|       |-- openapi-sync.yml
|       |-- released-pages-hardening-gates.yml
|       |-- soak-tests.yml
|       \-- stress-tests.yml
|-- .hypothesis/
|   |-- constants/
|   |   |-- 00731426b90af740
|   |   |-- 00a00398186063f4
|   |   |-- 00e4935d1440a2ca
|   |   |-- 01cb19e636d04082
|   |   |-- 02bca2c9d2f8566d
|   |   |-- 039f8a28fa91d19f
|   |   |-- 05224b1f50d4c8e2
|   |   |-- 06e37be44b7c2558
|   |   |-- 0860b7ce1f462945
|   |   |-- 096794da29b0a5fe
|   |   |-- 09af02b32eace3be
|   |   |-- 0a24b457adbbced2
|   |   |-- 0db51a1a0f9a9046
|   |   |-- 0f3094f4c41337a3
|   |   |-- 0f584482e7d3db29
|   |   |-- 11326b1300e7c559
|   |   |-- 122fc4d943da0a54
|   |   |-- 1968d36e3319a49f
|   |   |-- 1a701b0588e51868
|   |   |-- 1b488e9c0e7c5031
|   |   |-- 1c079de4646a8d8b
|   |   |-- 1c2919ea2d0d7b6f
|   |   |-- 21753c2266950be2
|   |   |-- 236be33c19706e06
|   |   |-- 2487e0dd67ee4005
|   |   |-- 25db02c884e47e34
|   |   |-- 263226a93d9fd720
|   |   |-- 267688019eacc507
|   |   |-- 284335a248b2d321
|   |   |-- 28d9bc818b741a80
|   |   |-- 2a2e79adea51da33
|   |   |-- 2a82a499c11a5de8
|   |   |-- 2b2923cb2e7b99f7
|   |   |-- 2b39e13cddad788d
|   |   |-- 2f2ae64af48e93fe
|   |   |-- 2f46fe56abf81670
|   |   |-- 301da8f67d265917
|   |   |-- 327c52ae13744797
|   |   |-- 345e5165f13cae58
|   |   |-- 34f845ad3468bfeb
|   |   |-- 35342e8dd172004d
|   |   |-- 392d6328bece7db8
|   |   |-- 3955e8710f8ecaa2
|   |   |-- 397bc9bcb3adb4ac
|   |   |-- 3b7bbdff8600e45e
|   |   |-- 3d2b36835512d57e
|   |   |-- 4093a4056e3ed640
|   |   |-- 40bd549cffe1dc41
|   |   |-- 41472cf65ca17068
|   |   |-- 41d662f99bd58f37
|   |   \-- ... (134 more entries truncated; cap=50)
|   |-- unicode_data/
|   |   \-- 14.0.0/
|   |       |-- charmap.json.gz
|   |       \-- codec-utf-8.json.gz
|   \-- .gitignore
|-- ci/
|   |-- gate-policy.md
|   |-- playwright-nightly.md
|   \-- required-check-policy.md
|-- ci-templates/
|   |-- bun.yml
|   |-- conda.yml
|   |-- go.yml
|   |-- npm.yml
|   |-- pip.yml
|   |-- pnpm.yml
|   |-- poetry.yml
|   |-- rust.yml
|   |-- unknown.yml
|   |-- uv.yml
|   \-- yarn.yml
|-- contracts/
|   |-- api/
|   |   |-- api-contract.md
|   |   |-- api-inventory.md
|   |   |-- error-format.md
|   |   \-- openapi.json
|   |-- business/
|   |   \-- business-rules.md
|   |-- ci/
|   |   \-- ci-gate-contract.md
|   |-- css/
|   |   |-- css-contract.md
|   |   |-- css-inventory.md
|   |   \-- design-tokens.md
|   |-- data/
|   |   \-- data-shape-contract.md
|   |-- env/
|   |   |-- .env.example.template
|   |   |-- env-contract.md
|   |   \-- env.schema.json
|   |-- CHANGELOG.md
|   \-- openapi.json
|-- data/
|   |-- page_status.json
|   \-- table_schema_info.json
|-- deploy/
|   |-- mes-dashboard-downtime-worker.service
|   |-- mes-dashboard-eap-alarm-worker.service
|   |-- mes-dashboard-hold-history-worker.service
|   |-- mes-dashboard-material-consumption-worker.service
|   |-- mes-dashboard-msd-worker.service
|   |-- mes-dashboard-production-achievement-worker.service
|   |-- mes-dashboard-production-history-worker.service
|   |-- mes-dashboard-reject-worker.service
|   |-- mes-dashboard-trace-worker.service
|   |-- mes-dashboard-watchdog.service
|   |-- mes-dashboard-wip-worker.service
|   \-- mes-dashboard.service
|-- docs/
|   |-- adr/
|   |   |-- 0001-material-consumption-summary-spool-granularity-key.md
|   |   |-- 0002-downtime-analysis-spool-namespace.md
|   |   |-- 0003-downtime-rowcount-chunking-exclusion.md
|   |   |-- 0004-gunicorn-preload-app-fork-safety.md
|   |   |-- 0005-resource-history-canonical-spool-key.md
|   |   |-- 0006-duckdb-prewarm-via-rq-queue.md
|   |   |-- 0007-downtime-browser-duckdb-compute-relocation.md
|   |   |-- 0008-eap-alarm-coarse-spool-detail-join.md
|   |   |-- 0009-eap-alarm-cross-chunk-pairing-in-post-aggregate.md
|   |   |-- 0010-downtime-duckdb-time-overlap-join.md
|   |   |-- 0011-global-concurrency-semaphore-rq-oracle-bound.md
|   |   |-- 0012-navigation-source-of-truth-code-manifest.md
|   |   |-- 0013-db-scheduling-reuse-wip-cache-no-dedicated-query.md
|   |   |-- 0014-msd-forward-lineage-seed-anchor.md
|   |   |-- 0015-eap-alarm-dual-shape-event-inclusion.md
|   |   \-- 0016-production-achievement-async-spool-seam-reduction.md
|   |-- architecture/
|   |   |-- base-job-semaphore-wiring-stress-soak-report.md
|   |   |-- cache-spool-patterns.md
|   |   |-- ci-workflow.md
|   |   |-- css-patterns.md
|   |   |-- eap-event-alarm-semantics-investigation.md
|   |   |-- eap-event-uph-collection-investigation.md
|   |   |-- filter-convergence-plan.md
|   |   |-- frontend-patterns.md
|   |   |-- modernization-policy.md
|   |   |-- query-arch-admin-optimization-plan.md
|   |   |-- query-dataflow-unification.md
|   |   |-- service-patterns.md
|   |   \-- test-discipline.md
|   |-- migration/
|   |   \-- full-modernization-architecture-blueprint/
|   |       |-- asset_readiness_manifest.json
|   |       |-- route_contracts.json
|   |       \-- route_scope_matrix.json
|   |-- cache-strategy.md
|   |-- cdd-kit-patterns.md
|   |-- ci_real_infra_gate_policy.md
|   |-- dynamic-rq-migration-plan.md
|   |-- hold_history.md
|   \-- real_infra_stability_report.md
|-- frontend/
|   |-- .cdd/
|   |   \-- code-map.yml
|   |-- scripts/
|   |   |-- css-governance-check.js
|   |   \-- ts-resolver-loader.mjs
|   |-- src/
|   |   |-- admin-dashboard/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- tabs/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- admin-pages/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- admin-shared/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- utils/
|   |   |   |   \-- ... (max depth)
|   |   |   \-- index.ts
|   |   |-- anomaly-overview/
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- assets/
|   |   |   \-- fonts/
|   |   |       \-- ... (max depth)
|   |   |-- core/
|   |   |   |-- api.ts
|   |   |   |-- app-version-check.ts
|   |   |   |-- autocomplete.ts
|   |   |   |-- compute.ts
|   |   |   |-- datetime.ts
|   |   |   |-- dev-warnings.ts
|   |   |   |-- duckdb-activation-policy.ts
|   |   |   |-- duckdb-client.ts
|   |   |   |-- endpoint-schemas.ts
|   |   |   |-- field-contracts.ts
|   |   |   |-- hold-navigation-state.ts
|   |   |   |-- index.ts
|   |   |   |-- pending-jobs-registry.ts
|   |   |   |-- post-export.ts
|   |   |   |-- reject-history-filters.ts
|   |   |   |-- resource-history-filters.ts
|   |   |   |-- risk-score.ts
|   |   |   |-- schema-guard.ts
|   |   |   |-- shell-navigation.ts
|   |   |   |-- table-tree.ts
|   |   |   |-- types.ts
|   |   |   |-- unwrap-api-result.ts
|   |   |   |-- wip-derive.ts
|   |   |   \-- wip-navigation-state.ts
|   |   |-- db-scheduling/
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- downtime-analysis/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- constants.ts
|   |   |   |-- formatDowntimeDate.ts
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   |-- style.css
|   |   |   \-- types.ts
|   |   |-- eap-alarm/
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- DetailTable.vue
|   |   |   |-- FilterBar.vue
|   |   |   |-- FineFilterBar.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   |-- ParetoChart.vue
|   |   |   |-- style.css
|   |   |   |-- SummaryCards.vue
|   |   |   \-- TrendChart.vue
|   |   |-- hold-detail/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- hold-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   |-- style.css
|   |   |   |-- useAutoRefresh.ts
|   |   |   \-- useHoldHistoryDuckDB.ts
|   |   |-- hold-overview/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- csvExport.ts
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- job-query/
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- material-consumption/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- material-trace/
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- mid-section-defect/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- portal/
|   |   |   |-- main.js
|   |   |   \-- portal.css
|   |   |-- portal-shell/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- views/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- ai-chat.css
|   |   |   |-- App.vue
|   |   |   |-- healthSummary.js
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   |-- nativeModuleRegistry.js
|   |   |   |-- navigationManifest.d.ts
|   |   |   |-- navigationManifest.js
|   |   |   |-- navigationState.js
|   |   |   |-- routeContracts.js
|   |   |   |-- routeQuery.js
|   |   |   |-- router.js
|   |   |   |-- sidebarState.js
|   |   |   \-- style.css
|   |   |-- production-achievement/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   |-- style.css
|   |   |   \-- utils.ts
|   |   |-- production-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- qc-gate/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- query-tool/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- utils/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- reject-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   |-- style.css
|   |   |   \-- useRejectHistoryDuckDB.ts
|   |   |-- resource-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   |-- style.css
|   |   |   \-- useResourceHistoryDuckDB.ts
|   |   |-- resource-shared/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- constants.ts
|   |   |   |-- index.ts
|   |   |   \-- styles.css
|   |   |-- resource-status/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- shared-composables/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- index.ts
|   |   |   |-- TraceProgressBar.vue
|   |   |   |-- useAiChat.ts
|   |   |   |-- useAsyncJobPolling.ts
|   |   |   |-- useAutocomplete.ts
|   |   |   |-- useAutoRefresh.ts
|   |   |   |-- useFilterOrchestrator.ts
|   |   |   |-- usePageUpdateBadge.ts
|   |   |   |-- usePaginationState.ts
|   |   |   |-- useQueryState.ts
|   |   |   |-- useRequestGuard.ts
|   |   |   |-- useSortableTable.ts
|   |   |   |-- useTraceProgress.ts
|   |   |   |-- useUrlSync.ts
|   |   |   \-- useViewStaleness.ts
|   |   |-- shared-ui/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   \-- index.ts
|   |   |-- styles/
|   |   |   \-- tailwind.css
|   |   |-- wip-detail/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- wip-overview/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- wip-shared/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- constants.ts
|   |   |   |-- index.ts
|   |   |   |-- pareto-styles.css
|   |   |   \-- styles.css
|   |   |-- workers/
|   |   |   \-- duckdb-worker.js
|   |   \-- yield-alert-center/
|   |       |-- App.vue
|   |       |-- index.html
|   |       |-- main.ts
|   |       |-- style.css
|   |       |-- useYieldAlertDuckDB.ts
|   |       |-- utils.ts
|   |       |-- YieldHeatmap.vue
|   |       |-- YieldPackageChart.vue
|   |       |-- YieldStationChart.vue
|   |       \-- YieldTrendChart.vue
|   |-- tests/
|   |   |-- abort/
|   |   |   |-- production-history-abort.test.js
|   |   |   |-- query-tool-abort.test.js
|   |   |   |-- reject-history-abort.test.js
|   |   |   \-- yield-alert-abort.test.js
|   |   |-- components/
|   |   |   |-- ActionButton.test.js
|   |   |   |-- AsyncQueryProgress.test.js
|   |   |   |-- DataTable.test.js
|   |   |   |-- DateRangePicker.test.js
|   |   |   |-- FilterPanel.test.js
|   |   |   |-- ForwardReasonMatrix.test.js
|   |   |   |-- HoldMatrix.test.js
|   |   |   |-- LoadingOverlay.test.js
|   |   |   |-- LoadingSpinner.test.js
|   |   |   |-- LotDetailTable.test.js
|   |   |   |-- MatrixTable.test.js
|   |   |   |-- ParetoGrid.test.js
|   |   |   \-- ProductionDetailTable.test.js
|   |   |-- core/
|   |   |   \-- api-dedup.test.js
|   |   |-- hold-overview/
|   |   |   \-- csv-export.test.js
|   |   |-- legacy/
|   |   |   |-- admin-dashboard-permissions-css-scope.test.js
|   |   |   |-- admin-dashboard.test.js
|   |   |   |-- anomaly-overview.test.js
|   |   |   |-- AUDIT.md
|   |   |   |-- autocomplete.test.js
|   |   |   |-- datetime.test.js
|   |   |   |-- loading-standardization.test.js
|   |   |   |-- local-compute-activation-policy.test.js
|   |   |   |-- material-trace-composables.test.js
|   |   |   |-- mid-section-defect-composables.test.js
|   |   |   |-- msd-completeness-warning.test.js
|   |   |   |-- portal-shell-app-contract.test.js
|   |   |   |-- portal-shell-health-summary.test.js
|   |   |   |-- portal-shell-navigation.test.js
|   |   |   |-- portal-shell-no-iframe.test.js
|   |   |   |-- portal-shell-parity-table-chart-matrix.test.js
|   |   |   |-- portal-shell-route-query-compat.test.js
|   |   |   |-- portal-shell-route-query.test.js
|   |   |   |-- portal-shell-sidebar.test.js
|   |   |   |-- portal-shell-wave-a-chart-lifecycle.test.js
|   |   |   |-- portal-shell-wave-a-smoke.test.js
|   |   |   |-- portal-shell-wave-b-native-smoke.test.js
|   |   |   |-- production-history.test.js
|   |   |   |-- query-tool-composables.test.js
|   |   |   |-- reject-history-date-range-limit.test.js
|   |   |   |-- report-filter-strategy.test.js
|   |   |   |-- resource-history.test.js
|   |   |   |-- resource-status.test.js
|   |   |   |-- shell-navigation.test.js
|   |   |   |-- wip-derive.test.js
|   |   |   |-- yield-alert-center-shell-contract.test.js
|   |   |   \-- yield-alert-center-utils.test.js
|   |   |-- playwright/
|   |   |   |-- data-boundary/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- resilience/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- _api-mode.ts
|   |   |   |-- _auth.js
|   |   |   |-- admin-dashboard.spec.ts
|   |   |   |-- admin-pages.spec.ts
|   |   |   |-- ai-query-panel.spec.ts
|   |   |   |-- anomaly-overview.spec.ts
|   |   |   |-- db-scheduling.spec.ts
|   |   |   |-- downtime-analysis.spec.js
|   |   |   |-- downtime-analysis.spec.ts
|   |   |   |-- eap-alarm-filters.spec.ts
|   |   |   |-- eap-alarm.spec.js
|   |   |   |-- hold-detail.spec.ts
|   |   |   |-- hold-history-filter.spec.ts
|   |   |   |-- hold-history-flat-table.spec.js
|   |   |   |-- hold-overview.spec.js
|   |   |   |-- job-abandon-on-unload.spec.js
|   |   |   |-- job-query.spec.ts
|   |   |   |-- material-consumption-data-boundary.spec.ts
|   |   |   |-- material-consumption-resilience.spec.ts
|   |   |   |-- material-consumption.spec.ts
|   |   |   |-- material-trace.spec.ts
|   |   |   |-- mid-section-defect.spec.ts
|   |   |   |-- portal-shell-login.spec.ts
|   |   |   |-- production-achievement-async.spec.ts
|   |   |   |-- production-achievement-monkey.spec.ts
|   |   |   |-- production-achievement.spec.js
|   |   |   |-- production-history-cross-filter.spec.ts
|   |   |   |-- production-history-filter-options-error.spec.ts
|   |   |   |-- production-history-multi-line-input.spec.ts
|   |   |   |-- production-history-pruning-feedback.spec.ts
|   |   |   |-- production-history-query-mode-tabs.spec.ts
|   |   |   |-- production-history-wildcard-paste.spec.ts
|   |   |   |-- qc-gate.spec.ts
|   |   |   |-- query-tool-filters.spec.ts
|   |   |   |-- query-tool-url-state.spec.js
|   |   |   |-- query-tool.spec.js
|   |   |   |-- reject-history-filter.spec.ts
|   |   |   |-- reject-history.spec.js
|   |   |   |-- reject-material-flat-table.spec.js
|   |   |   |-- resource-history-async.spec.ts
|   |   |   |-- resource-status.spec.ts
|   |   |   |-- wip-detail.spec.ts
|   |   |   |-- wip-matrix-drilldown.spec.js
|   |   |   |-- wip-overview.spec.ts
|   |   |   \-- yield-alert-center.spec.ts
|   |   |-- query-tool/
|   |   |   |-- App.url-state.test.js
|   |   |   |-- EquipmentRejectsTable.test.js
|   |   |   |-- useLotDetail.pagination.test.js
|   |   |   \-- useLotEquipmentQuery.test.js
|   |   |-- resource-status/
|   |   |   |-- App.cross-filter.test.ts
|   |   |   \-- useCrossFilter.test.ts
|   |   |-- shared-composables/
|   |   |   |-- useAsyncJobPolling.test.js
|   |   |   |-- useAutoRefresh.test.js
|   |   |   \-- useRequestGuard.test.js
|   |   |-- unit/
|   |   |   \-- eap-alarm-filter.test.js
|   |   |-- validation/
|   |   |   |-- useHoldOverview.validation.test.js
|   |   |   |-- useMaterialTrace.validation.test.js
|   |   |   |-- useProductionHistory.validation.test.js
|   |   |   |-- useRejectHistory.validation.test.js
|   |   |   |-- useYieldAlert.validation.test.js
|   |   |   \-- wip-url-params.test.js
|   |   |-- yield-alert/
|   |   |   |-- App.cross-filter.test.js
|   |   |   |-- App.csv-export.test.js
|   |   |   \-- useYieldAlertDuckDB.departments.test.js
|   |   |-- pending-jobs-registry.test.js
|   |   |-- schema-guard.test.js
|   |   \-- unwrap-api-result.test.js
|   |-- .gitignore
|   |-- package-lock.json
|   |-- package.json
|   |-- playwright.config.js
|   |-- postcss.config.js
|   |-- tailwind.config.js
|   |-- tsconfig.json
|   |-- vite.config.ts
|   \-- vitest.config.js
|-- logs/
|   |-- archive/
|   |   |-- access_20260709_104124.log
|   |   |-- error_20260709_104124.log
|   |   |-- rq_downtime_worker_20260709_104124.log
|   |   |-- rq_eap_alarm_worker_20260709_104124.log
|   |   |-- rq_hold_hist_worker_20260709_104124.log
|   |   |-- rq_msd_worker_20260709_104124.log
|   |   |-- rq_prod_hist_worker_20260709_104124.log
|   |   |-- rq_reject_worker_20260709_104124.log
|   |   |-- rq_resource_worker_20260709_104124.log
|   |   |-- rq_warmup_worker_20260709_104124.log
|   |   |-- rq_worker_20260709_104124.log
|   |   |-- rq_yield_alert_worker_20260709_104124.log
|   |   \-- watchdog_20260709_104124.log
|   |-- access.log
|   |-- admin_logs.sqlite
|   |-- admin_logs.sqlite-shm
|   |-- admin_logs.sqlite-wal
|   |-- error.log
|   |-- login_sessions.sqlite
|   |-- login_sessions.sqlite-shm
|   |-- login_sessions.sqlite-wal
|   |-- metrics_history.sqlite
|   |-- metrics_history.sqlite-shm
|   |-- metrics_history.sqlite-wal
|   |-- rq_downtime_worker.log
|   |-- rq_eap_alarm_worker.log
|   |-- rq_hold_hist_worker.log
|   |-- rq_msd_worker.log
|   |-- rq_prod_ach_verify.log
|   |-- rq_prod_ach_verify2.log
|   |-- rq_prod_ach_worker.log
|   |-- rq_prod_hist_worker.log
|   |-- rq_query_tool_worker.log
|   |-- rq_reject_worker.log
|   |-- rq_resource_worker.log
|   |-- rq_warmup_worker.log
|   |-- rq_worker.log
|   |-- rq_yield_alert_worker.log
|   |-- startup.log
|   \-- watchdog.log
|-- scripts/
|   |-- sql/
|   |   \-- production_achievement_tables.sql
|   |-- capture_spool_snapshot.py
|   |-- deploy.sh
|   |-- extract_sql_schema.py
|   |-- measure_real_infra_stability.py
|   |-- reap_orphan_jobs.py
|   |-- run_cache_benchmarks.py
|   |-- run_e2e.sh
|   |-- run_stress_tests.py
|   |-- soak_local.sh
|   |-- start_server.sh
|   \-- worker_watchdog.py
|-- shared/
|   \-- field_contracts.json
|-- specs/
|   |-- context/
|   |   |-- contracts-index.md
|   |   \-- project-map.md
|   \-- templates/
|       |-- archive.md
|       |-- change-classification.md
|       |-- change-request.md
|       |-- ci-gates.md
|       |-- context-manifest.md
|       |-- contracts.md
|       |-- current-behavior.md
|       |-- design.md
|       |-- implementation-plan.md
|       |-- monkey-test-report.md
|       |-- project-profile.md
|       |-- proposal.md
|       |-- qa-report.md
|       |-- regression-report.md
|       |-- spec.md
|       |-- stress-soak-report.md
|       |-- tasks.yml
|       |-- test-evidence.yml
|       |-- test-plan.md
|       \-- visual-review-report.md
|-- src/
|   \-- mes_dashboard/
|       |-- config/
|       |   |-- __init__.py
|       |   |-- constants.py
|       |   |-- database.py
|       |   |-- field_contracts.py
|       |   |-- settings.py
|       |   |-- tables.py
|       |   \-- workcenter_groups.py
|       |-- core/
|       |   |-- __init__.py
|       |   |-- base_chunked_duckdb_job.py
|       |   |-- cache_plane.py
|       |   |-- cache_updater.py
|       |   |-- cache.py
|       |   |-- circuit_breaker.py
|       |   |-- csrf.py
|       |   |-- database.py
|       |   |-- duckdb_runtime.py
|       |   |-- exceptions.py
|       |   |-- feature_flags.py
|       |   |-- global_concurrency.py
|       |   |-- heavy_query_telemetry.py
|       |   |-- interactive_memory_guard.py
|       |   |-- log_store.py
|       |   |-- login_session_store.py
|       |   |-- metrics_history.py
|       |   |-- metrics.py
|       |   |-- modernization_policy.py
|       |   |-- mysql_client.py
|       |   |-- oracle_arrow_reader.py
|       |   |-- partial_failure_contract.py
|       |   |-- permissions.py
|       |   |-- query_cost_policy.py
|       |   |-- query_quality_contract.py
|       |   |-- query_spool_store.py
|       |   |-- rate_limit.py
|       |   |-- redis_client.py
|       |   |-- redis_df_store.py
|       |   |-- request_validation.py
|       |   |-- resilience.py
|       |   |-- response.py
|       |   |-- route_helpers.py
|       |   |-- runtime_contract.py
|       |   |-- spool_dir_check.py
|       |   |-- spool_pipeline.py
|       |   |-- spool_warmup_scheduler.py
|       |   |-- sync_worker.py
|       |   |-- utils.py
|       |   |-- watchdog_logging.py
|       |   |-- worker_memory_guard.py
|       |   |-- worker_pool_manager.py
|       |   \-- worker_recovery_policy.py
|       |-- routes/
|       |   |-- __init__.py
|       |   |-- admin_routes.py
|       |   |-- ai_routes.py
|       |   |-- analytics_routes.py
|       |   |-- dashboard_routes.py
|       |   |-- db_scheduling_routes.py
|       |   |-- downtime_analysis_routes.py
|       |   |-- eap_alarm_routes.py
|       |   |-- health_routes.py
|       |   |-- hold_history_routes.py
|       |   |-- hold_overview_routes.py
|       |   |-- hold_routes.py
|       |   |-- internal_routes.py
|       |   |-- job_query_routes.py
|       |   |-- job_routes.py
|       |   |-- material_consumption_routes.py
|       |   |-- material_trace_routes.py
|       |   |-- mid_section_defect_routes.py
|       |   |-- production_achievement_routes.py
|       |   |-- production_history_routes.py
|       |   |-- qc_gate_routes.py
|       |   |-- query_tool_routes.py
|       |   |-- reject_history_routes.py
|       |   |-- resource_history_routes.py
|       |   |-- resource_routes.py
|       |   |-- spool_routes.py
|       |   |-- trace_routes.py
|       |   |-- user_auth_routes.py
|       |   |-- wip_routes.py
|       |   \-- yield_alert_routes.py
|       |-- services/
|       |   |-- __init__.py
|       |   |-- ai_agent_loop.py
|       |   |-- ai_business_context.py
|       |   |-- ai_function_registry.py
|       |   |-- ai_functions.yaml
|       |   |-- ai_leader_orchestrator.py
|       |   |-- ai_query_service.py
|       |   |-- ai_query_understanding.py
|       |   |-- ai_schema_context.py
|       |   |-- ai_tool_definitions.py
|       |   |-- ai_tool_executor.py
|       |   |-- anomaly_detection_scheduler.py
|       |   |-- anomaly_detection_sql_runtime.py
|       |   |-- async_query_job_service.py
|       |   |-- auth_service.py
|       |   |-- batch_query_engine.py
|       |   |-- container_filter_cache.py
|       |   |-- container_resolution_policy.py
|       |   |-- dashboard_service.py
|       |   |-- db_scheduling_service.py
|       |   |-- downtime_analysis_cache.py
|       |   |-- downtime_analysis_duckdb_cache.py
|       |   |-- downtime_analysis_service.py
|       |   |-- downtime_query_job_service.py
|       |   |-- eap_alarm_cache.py
|       |   |-- eap_alarm_service.py
|       |   |-- event_fetcher.py
|       |   |-- filter_cache.py
|       |   |-- hold_dataset_cache.py
|       |   |-- hold_history_service.py
|       |   |-- hold_history_sql_runtime.py
|       |   |-- hold_query_job_service.py
|       |   |-- hold_today_snapshot_service.py
|       |   |-- internal_metrics_service.py
|       |   |-- job_query_service.py
|       |   |-- job_registry.py
|       |   |-- lineage_engine.py
|       |   |-- material_consumption_duckdb_runtime.py
|       |   |-- material_consumption_service.py
|       |   |-- material_trace_duckdb_runtime.py
|       |   |-- material_trace_service.py
|       |   |-- mid_section_defect_service.py
|       |   |-- msd_duckdb_runtime.py
|       |   |-- msd_lineage_job_service.py
|       |   |-- msd_seed_job_service.py
|       |   |-- navigation_contract.py
|       |   |-- page_registry.py
|       |   |-- production_achievement_permission_service.py
|       |   |-- production_achievement_service.py
|       |   |-- production_achievement_target_service.py
|       |   \-- ... (33 more entries truncated; cap=50)
|       |-- sql/
|       |   |-- analytics/
|       |   |   \-- ... (max depth)
|       |   |-- dashboard/
|       |   |   \-- ... (max depth)
|       |   |-- downtime_analysis/
|       |   |   \-- ... (max depth)
|       |   |-- hold_history/
|       |   |   \-- ... (max depth)
|       |   |-- job_query/
|       |   |   \-- ... (max depth)
|       |   |-- lineage/
|       |   |   \-- ... (max depth)
|       |   |-- material_consumption/
|       |   |   \-- ... (max depth)
|       |   |-- material_trace/
|       |   |   \-- ... (max depth)
|       |   |-- mid_section_defect/
|       |   |   \-- ... (max depth)
|       |   |-- production_history/
|       |   |   \-- ... (max depth)
|       |   |-- query_tool/
|       |   |   \-- ... (max depth)
|       |   |-- reject_history/
|       |   |   \-- ... (max depth)
|       |   |-- resource/
|       |   |   \-- ... (max depth)
|       |   |-- resource_history/
|       |   |   \-- ... (max depth)
|       |   |-- validation/
|       |   |   \-- ... (max depth)
|       |   |-- wip/
|       |   |   \-- ... (max depth)
|       |   |-- yield_alert/
|       |   |   \-- ... (max depth)
|       |   |-- __init__.py
|       |   |-- builder.py
|       |   |-- filters.py
|       |   |-- loader.py
|       |   |-- production_achievement.sql
|       |   \-- wildcards.py
|       |-- static/
|       |   |-- js/
|       |   |   \-- ... (max depth)
|       |   |-- favicon.svg
|       |   |-- icon-512.png
|       |   \-- PANJIT.png
|       |-- templates/
|       |   |-- _base.html
|       |   |-- 403.html
|       |   |-- 404.html
|       |   |-- 500.html
|       |   |-- job_query.html
|       |   \-- query_tool.html
|       |-- workers/
|       |   |-- __init__.py
|       |   |-- downtime_worker.py
|       |   |-- eap_alarm_worker.py
|       |   |-- production_achievement_worker.py
|       |   |-- production_history_worker.py
|       |   |-- reject_history_worker.py
|       |   |-- resource_history_base_worker.py
|       |   \-- resource_history_oee_worker.py
|       |-- __init__.py
|       |-- __main__.py
|       |-- app.py
|       \-- rq_worker_preload.py
|-- tests/
|   |-- contract/
|   |   |-- samples/
|   |   |   |-- .gitkeep
|   |   |   |-- get_admin_logs.json
|   |   |   |-- get_admin_metrics.json
|   |   |   |-- get_admin_pages.json
|   |   |   |-- get_admin_performance_detail.json
|   |   |   |-- get_admin_performance_history.json
|   |   |   |-- get_admin_production_achievement_permissions.json
|   |   |   |-- get_admin_storage_info.json
|   |   |   |-- get_admin_system_status.json
|   |   |   |-- get_admin_user_usage_kpi.json
|   |   |   |-- get_admin_worker_status.json
|   |   |   |-- get_analytics_anomaly_summary.json
|   |   |   |-- get_analytics_equipment_deviation_drilldown.json
|   |   |   |-- get_analytics_equipment_deviation.json
|   |   |   |-- get_analytics_hold_outliers_drilldown.json
|   |   |   |-- get_analytics_hold_outliers.json
|   |   |   |-- get_analytics_reject_spikes_drilldown.json
|   |   |   |-- get_analytics_reject_spikes.json
|   |   |   |-- get_analytics_yield_anomalies_drilldown.json
|   |   |   |-- get_analytics_yield_anomalies.json
|   |   |   |-- get_auth_me.json
|   |   |   |-- get_db_scheduling_queue.json
|   |   |   |-- get_downtime_analysis_equipment_detail.json
|   |   |   |-- get_downtime_analysis_event_detail.json
|   |   |   |-- get_downtime_analysis_export_equipment_detail.json
|   |   |   |-- get_downtime_analysis_export_event_detail.json
|   |   |   |-- get_downtime_analysis_options.json
|   |   |   |-- get_downtime_analysis_view.json
|   |   |   |-- get_get_table_info.json
|   |   |   |-- get_health_deep.json
|   |   |   |-- get_health.json
|   |   |   |-- get_hold_history_config.json
|   |   |   |-- get_hold_history_view.json
|   |   |   |-- get_hold_overview_lots_export.json
|   |   |   |-- get_hold_overview_lots.json
|   |   |   |-- get_hold_overview_matrix.json
|   |   |   |-- get_hold_overview_summary.json
|   |   |   |-- get_hold_overview_treemap.json
|   |   |   |-- get_job_id.json
|   |   |   |-- get_job_query_resources.json
|   |   |   |-- get_job_query_txn.json
|   |   |   |-- get_material_consumption_detail_job.json
|   |   |   |-- get_material_consumption_detail_page.json
|   |   |   |-- get_material_consumption_filter_options.json
|   |   |   |-- get_material_consumption_view.json
|   |   |   |-- get_material_trace_filter_options.json
|   |   |   |-- get_material_trace_job.json
|   |   |   |-- get_mid_section_defect_analysis_detail.json
|   |   |   |-- get_mid_section_defect_analysis.json
|   |   |   |-- get_mid_section_defect_container_filter_options.json
|   |   |   \-- ... (133 more entries truncated; cap=50)
|   |   |-- capture_samples.py
|   |   |-- README.md
|   |   |-- response-samples.example.json
|   |   |-- response-samples.json
|   |   |-- test_capture_samples.py
|   |   |-- test_doctor_clean.py
|   |   |-- test_env_async_threshold_removal.py
|   |   |-- test_env_downtime_unified_flag.py
|   |   |-- test_env_duckdb_job_dir.py
|   |   |-- test_env_material_trace_flag.py
|   |   |-- test_env_production_achievement_unified_flag.py
|   |   |-- test_gate_wiring.py
|   |   |-- test_manifest_completeness.py
|   |   |-- test_openapi_schema_resolution.py
|   |   \-- test_schema_coverage.py
|   |-- e2e/
|   |   |-- __init__.py
|   |   |-- browser_helpers.py
|   |   |-- conftest.py
|   |   |-- test_admin_auth_e2e.py
|   |   |-- test_admin_dashboard_e2e.py
|   |   |-- test_anomaly_overview_e2e.py
|   |   |-- test_cache_e2e.py
|   |   |-- test_downtime_analysis_e2e.py
|   |   |-- test_eap_alarm_e2e.py
|   |   |-- test_global_connection.py
|   |   |-- test_hold_history_e2e.py
|   |   |-- test_hold_overview_e2e.py
|   |   |-- test_job_query_e2e.py
|   |   |-- test_material_trace_e2e.py
|   |   |-- test_mid_section_defect_e2e.py
|   |   |-- test_production_history_e2e.py
|   |   |-- test_qc_gate_e2e.py
|   |   |-- test_query_race_condition_e2e.py
|   |   |-- test_query_tool_e2e.py
|   |   |-- test_query_tool_ui_ux_e2e.py
|   |   |-- test_realtime_equipment_e2e.py
|   |   |-- test_reject_history_e2e.py
|   |   |-- test_resource_cache_e2e.py
|   |   |-- test_resource_history_browser_e2e.py
|   |   |-- test_resource_history_e2e.py
|   |   |-- test_trace_pipeline_e2e.py
|   |   |-- test_unified_ux_verification_e2e.py
|   |   |-- test_url_length_guard_e2e.py
|   |   |-- test_wip_hold_pages_e2e.py
|   |   \-- test_yield_alert_e2e.py
|   |-- fixtures/
|   |   |-- cache_benchmark_fixture.json
|   |   |-- frontend_compute_parity.json
|   |   \-- route_contract_matrix.py
|   |-- integration/
|   |   |-- __init__.py
|   |   |-- _infra_topology.py
|   |   |-- _metrics_probe.py
|   |   |-- _multi_worker_harness.py
|   |   |-- _multi_worker_jobs.py
|   |   |-- _oracle_xe_fixture.py
|   |   |-- conftest.py
|   |   |-- test_base_job_semaphore_wiring.py
|   |   |-- test_downtime_rq_async.py
|   |   |-- test_eap_alarm_coarse_filter.py
|   |   |-- test_eap_alarm_data_boundary.py
|   |   |-- test_eap_alarm_resilience.py
|   |   |-- test_eap_alarm_rq_async.py
|   |   |-- test_fixtures_smoke.py
|   |   |-- test_hold_history_rq_async.py
|   |   |-- test_material_trace_rq_async.py
|   |   |-- test_multi_worker_concurrency.py
|   |   |-- test_oracle_arrow_pool_lifecycle.py
|   |   |-- test_oracle_error_codes.py
|   |   |-- test_oracle_error_path.py
|   |   |-- test_preload_fork_safety.py
|   |   |-- test_production_achievement_filter_cache_reuse.py
|   |   |-- test_production_achievement_mysql_roundtrip.py
|   |   |-- test_production_achievement_resilience.py
|   |   |-- test_production_achievement_rq_async.py
|   |   |-- test_production_history_rq_async.py
|   |   |-- test_query_tool_rq_async.py
|   |   |-- test_race_conditions.py
|   |   |-- test_real_multi_worker.py
|   |   |-- test_real_oracle_fault_injection.py
|   |   |-- test_redis_chaos.py
|   |   |-- test_redis_timeout_fallback.py
|   |   |-- test_reject_history_rq_async.py
|   |   |-- test_resource_history_rq_async.py
|   |   |-- test_rowcount_flag_parity.py
|   |   |-- test_rq_semaphore_wiring.py
|   |   |-- test_soak_workload.py
|   |   \-- test_wip_rowcount_rq_routing.py
|   |-- manual/
|   |   \-- test_job_owner_auth_live.py
|   |-- property/
|   |   |-- __init__.py
|   |   |-- conftest.py
|   |   |-- README.md
|   |   |-- strategies.py
|   |   |-- test_cross_filter.py
|   |   |-- test_filter_idempotence.py
|   |   |-- test_filter_subset_invariant.py
|   |   |-- test_hold_history_duration_invariants.py
|   |   |-- test_hold_today_snapshot_invariants.py
|   |   |-- test_pagination_safe_defaults.py
|   |   |-- test_request_validation_idempotence.py
|   |   |-- test_request_validation_integers.py
|   |   |-- test_request_validation_robustness.py
|   |   |-- test_sort_allowlist.py
|   |   |-- test_url_state_decode_robustness.py
|   |   |-- test_url_state_roundtrip.py
|   |   \-- test_wildcard_parser.py
|   |-- routes/
|   |   |-- _fuzz_payloads.py
|   |   |-- test_fuzz_routes.py
|   |   \-- test_internal_routes.py
|   |-- stress/
|   |   |-- __init__.py
|   |   |-- async_helpers.py
|   |   |-- conftest.py
|   |   |-- integrity_helpers.py
|   |   |-- load_collector.py
|   |   |-- stress_registry.py
|   |   |-- test_api_load.py
|   |   |-- test_async_job_stress.py
|   |   |-- test_base_job_semaphore_stress.py
|   |   |-- test_chunk_boundary.py
|   |   |-- test_cross_module_stress.py
|   |   |-- test_data_integrity.py
|   |   |-- test_downtime_analysis_stress.py
|   |   |-- test_frontend_stress.py
|   |   |-- test_hold_overview_export_stress.py
|   |   |-- test_hold_today_snapshot_stress.py
|   |   |-- test_load_collector_unit.py
|   |   |-- test_material_consumption_stress.py
|   |   |-- test_material_trace_stress.py
|   |   |-- test_mid_section_defect_stress.py
|   |   |-- test_production_achievement_stress.py
|   |   |-- test_production_history_stress.py
|   |   |-- test_query_tool_stress.py
|   |   |-- test_reject_history_stress.py
|   |   |-- test_resource_history_stress.py
|   |   |-- test_rq_semaphore_stress.py
|   |   |-- test_wip_worker_stress.py
|   |   \-- test_yield_alert_stress.py
|   |-- templates/
|   |   |-- data-boundary/
|   |   |   \-- malformed-data.spec.md
|   |   |-- e2e/
|   |   |   \-- critical-journey.spec.md
|   |   |-- monkey/
|   |   |   \-- operation-sequence.spec.md
|   |   |-- resilience/
|   |   |   \-- api-failure.spec.md
|   |   |-- soak/
|   |   |   |-- k6-example.js
|   |   |   |-- locust-example.py
|   |   |   \-- soak-profile.md
|   |   \-- stress/
|   |       |-- artillery-example.yml
|   |       |-- k6-example.js
|   |       |-- load-profile.md
|   |       \-- locust-example.py
|   |-- __init__.py
|   |-- conftest.py
|   |-- README.md
|   |-- test_admin_routes_logs.py
|   |-- test_admin_routes_perf.py
|   |-- test_admin_routes.py
|   |-- test_ai_agent_loop.py
|   |-- test_ai_business_context.py
|   |-- test_ai_function_registry.py
|   |-- test_ai_leader_orchestrator.py
|   |-- test_ai_query_service.py
|   |-- test_ai_query_understanding.py
|   |-- test_ai_routes.py
|   |-- test_ai_schema_context.py
|   |-- test_ai_tool_definitions.py
|   |-- test_ai_tool_executor.py
|   |-- test_analytics_routes.py
|   |-- test_anomaly_detection_scheduler.py
|   |-- test_anomaly_detection_sql_runtime.py
|   |-- test_api_contract.py
|   |-- test_api_integration.py
|   |-- test_app_factory.py
|   |-- test_app_startup.py
|   |-- test_async_job_timeout.py
|   |-- test_async_query_job_service.py
|   |-- test_auth_integration.py
|   |-- test_auth_service.py
|   |-- test_base_chunked_duckdb_job.py
|   |-- test_base_job_semaphore_wiring.py
|   |-- test_batch_query_engine.py
|   |-- test_cache_integration.py
|   |-- test_cache_lifecycle.py
|   |-- test_cache_plane.py
|   |-- test_cache_updater_lock_behavior.py
|   |-- test_cache_updater.py
|   |-- test_cache.py
|   |-- test_circuit_breaker_integration.py
|   |-- test_circuit_breaker.py
|   |-- test_common_filters.py
|   |-- test_container_filter_cache.py
|   |-- test_container_resolution_policy.py
|   \-- ... (199 more entries truncated; cap=50)
|-- tmp/
|   |-- duckdb_jobs/
|   |   |-- eap_alarm/
|   |   |-- production_achievement/
|   |   |   \-- production-achievement-36dd782bc31c/
|   |   |       \-- ... (max depth)
|   |   |-- production_history/
|   |   |-- reject_dataset/
|   |   \-- test_ns/
|   |-- query_spool/
|   |   |-- anomaly_hold_dataset/
|   |   |   \-- 7c193f4e1ec6e300.parquet
|   |   |-- anomaly_reject_dataset/
|   |   |   \-- 858f092b53042f96.parquet
|   |   |-- anomaly_resource_dataset/
|   |   |   \-- daa76e309ed12ee6.parquet
|   |   |-- anomaly_yield_dataset/
|   |   |   \-- 301649741a76a9aa.parquet
|   |   |-- hold_dataset/
|   |   |   \-- c125b5de22268fb6.parquet
|   |   |-- reject_dataset/
|   |   |   \-- ab2164b57726d1aa.parquet
|   |   |-- resource_dataset/
|   |   |   \-- 2c755a071eb865dd.parquet
|   |   |-- resource_oee/
|   |   |   \-- c186447492fb51f4.parquet
|   |   |-- yield_alert_dataset/
|   |   |   \-- 6ad768c74a6a1782.parquet
|   |   |-- probe_1006070.json
|   |   |-- probe_1024367.json
|   |   |-- probe_103606.json
|   |   |-- probe_104090.json
|   |   |-- probe_104859.json
|   |   |-- probe_105315.json
|   |   |-- probe_106617.json
|   |   |-- probe_106916.json
|   |   |-- probe_107457.json
|   |   |-- probe_108141.json
|   |   |-- probe_108854.json
|   |   |-- probe_109685.json
|   |   |-- probe_109999.json
|   |   |-- probe_111796.json
|   |   |-- probe_112205.json
|   |   |-- probe_112672.json
|   |   |-- probe_113314.json
|   |   |-- probe_113740.json
|   |   |-- probe_113938.json
|   |   |-- probe_114639.json
|   |   |-- probe_1192488.json
|   |   |-- probe_12085.json
|   |   |-- probe_127692.json
|   |   |-- probe_128330.json
|   |   |-- probe_1493808.json
|   |   |-- probe_1493861.json
|   |   |-- probe_1503125.json
|   |   |-- probe_1503152.json
|   |   |-- probe_1515046.json
|   |   |-- probe_1525449.json
|   |   |-- probe_154932.json
|   |   |-- probe_154979.json
|   |   |-- probe_1555393.json
|   |   |-- probe_1555927.json
|   |   |-- probe_1556030.json
|   |   |-- probe_1556813.json
|   |   |-- probe_1556924.json
|   |   |-- probe_1557180.json
|   |   |-- probe_1557236.json
|   |   |-- probe_1564989.json
|   |   |-- probe_1565010.json
|   |   \-- ... (106 more entries truncated; cap=50)
|   |-- downtime_analysis.duckdb
|   |-- gunicorn.pid
|   |-- mes_dashboard_restart_state.json
|   |-- resource_history.duckdb
|   |-- rq_downtime_worker.pid
|   |-- rq_eap_alarm_worker.pid
|   |-- rq_hold_hist_worker.pid
|   |-- rq_msd_worker.pid
|   |-- rq_prod_ach_worker.pid
|   |-- rq_prod_hist_worker.pid
|   |-- rq_query_tool_worker.pid
|   |-- rq_reject_worker.pid
|   |-- rq_resource_worker.pid
|   |-- rq_trace_worker.pid
|   |-- rq_warmup_worker.pid
|   |-- rq_yield_alert_worker.pid
|   \-- worker_watchdog.pid
|-- .coverage
|-- .dockerignore
|-- .env
|-- .env.dev
|-- .env.example
|-- .env.prd
|-- .gitignore
|-- Check.md
|-- CLAUDE.md
|-- docker-compose.prd.yml
|-- docker-compose.test.yml
|-- docker-compose.yml
|-- Dockerfile
|-- environment.yml
|-- gunicorn.conf.py
|-- PRD.md
|-- pyproject.toml
|-- pytest.ini
|-- README.md
|-- requirements-dev.txt
|-- requirements.txt
|-- SDD.md
|-- supervisord.conf
\-- TDD.md
```
