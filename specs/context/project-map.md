---
artifact: project-map
generated-by: cdd-kit context-scan
schema-version: 1
root: DashBoard_vite
visible-dirs: 165
visible-files: 846
omitted-dirs: 59
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
DashBoard_vite/
|-- .cdd/
|   |-- .hooks-installed
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
|       |-- released-pages-hardening-gates.yml
|       |-- soak-tests.yml
|       \-- stress-tests.yml
|-- .hypothesis/
|   |-- constants/
|   |   |-- 00731426b90af740
|   |   |-- 00e4935d1440a2ca
|   |   |-- 0199bae5456ba1ac
|   |   |-- 01cb19e636d04082
|   |   |-- 02bca2c9d2f8566d
|   |   |-- 03d72be617fe07b9
|   |   |-- 0478f49b48ee4a27
|   |   |-- 04e26e6472111f2c
|   |   |-- 04f75a340f5aee98
|   |   |-- 06e37be44b7c2558
|   |   |-- 09af02b32eace3be
|   |   |-- 0ac8c61031ebb16b
|   |   |-- 0bb0d7320a5cea09
|   |   |-- 0c14e8a6e0dfaa9a
|   |   |-- 0e749cfd569a40b7
|   |   |-- 0f2d4ac438e36262
|   |   |-- 0fb4599ed66628f4
|   |   |-- 1131d28f548032e7
|   |   |-- 11326b1300e7c559
|   |   |-- 11d2c913de0cba90
|   |   |-- 137aac6b65143dec
|   |   |-- 15a2721810beed32
|   |   |-- 17a6952f61650689
|   |   |-- 1cc56ed5fc92eb40
|   |   |-- 1fa576bc7d285941
|   |   |-- 1fcb892092629696
|   |   |-- 2079893a07ce42c4
|   |   |-- 209aa30bab8411f2
|   |   |-- 20a29d650996dc03
|   |   |-- 22775c7be38c0fc8
|   |   |-- 2487e0dd67ee4005
|   |   |-- 2513622121cc3cd3
|   |   |-- 253e6c94fab987bc
|   |   |-- 25d84cf88b9bff0e
|   |   |-- 25db02c884e47e34
|   |   |-- 263226a93d9fd720
|   |   |-- 267688019eacc507
|   |   |-- 27091f72d62819f4
|   |   |-- 296b4f265252c452
|   |   |-- 2b2923cb2e7b99f7
|   |   |-- 2bfc933af50d6a1b
|   |   |-- 2f2ae64af48e93fe
|   |   |-- 2f46fe56abf81670
|   |   |-- 2fb614e1df1ae85f
|   |   |-- 314c411df6192c80
|   |   |-- 327c52ae13744797
|   |   |-- 3399b41644e40c25
|   |   |-- 3453e8fac951ce5c
|   |   |-- 37d084e6562ef65a
|   |   |-- 392d6328bece7db8
|   |   \-- ... (151 more entries truncated; cap=50)
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
|   |   \-- error-format.md
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
|   \-- CHANGELOG.md
|-- data/
|   |-- page_status.json
|   \-- table_schema_info.json
|-- deploy/
|   |-- mes-dashboard-material-consumption-worker.service
|   |-- mes-dashboard-msd-worker.service
|   |-- mes-dashboard-reject-worker.service
|   |-- mes-dashboard-trace-worker.service
|   |-- mes-dashboard-watchdog.service
|   \-- mes-dashboard.service
|-- docs/
|   |-- adr/
|   |   |-- 0001-material-consumption-summary-spool-granularity-key.md
|   |   |-- 0002-downtime-analysis-spool-namespace.md
|   |   |-- 0003-downtime-rowcount-chunking-exclusion.md
|   |   \-- 0004-gunicorn-preload-app-fork-safety.md
|   |-- migration/
|   |   |-- full-modernization-architecture-blueprint/
|   |   |   |-- asset_readiness_manifest.json
|   |   |   |-- bug_revalidation_records.json
|   |   |   |-- exception_registry.json
|   |   |   |-- known_bug_baseline.json
|   |   |   |-- manual_acceptance_records.json
|   |   |   |-- quality_gate_policy.json
|   |   |   |-- quality_gate_report.json
|   |   |   |-- route_contracts.json
|   |   |   |-- route_scope_matrix.json
|   |   |   \-- style_inventory.json
|   |   \-- portal-no-iframe/
|   |       |-- baseline_api_payload_contracts.json
|   |       |-- baseline_drawer_contract_validation.json
|   |       |-- baseline_drawer_visibility.json
|   |       \-- baseline_route_query_contracts.json
|   |-- cache-strategy.md
|   |-- ci_real_infra_gate_policy.md
|   |-- hold_history.md
|   \-- real_infra_stability_report.md
|-- frontend/
|   |-- .cdd/
|   |   \-- code-map.yml
|   |-- logs/
|   |   \-- admin_logs.sqlite
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
|   |   |-- downtime-analysis/
|   |   |   |-- __tests__/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- formatDowntimeDate.ts
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   |-- style.css
|   |   |   \-- types.ts
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
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- portal/
|   |   |   |-- main.js
|   |   |   \-- portal.css
|   |   |-- portal-shell/
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
|   |   |   |-- navigationState.js
|   |   |   |-- routeContracts.js
|   |   |   |-- routeQuery.js
|   |   |   |-- router.js
|   |   |   |-- sidebarState.js
|   |   |   \-- style.css
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
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.ts
|   |   |   \-- style.css
|   |   |-- shared-composables/
|   |   |   |-- index.ts
|   |   |   |-- TraceProgressBar.vue
|   |   |   |-- useAiChat.ts
|   |   |   |-- useAsyncJobPolling.ts
|   |   |   |-- useAutocomplete.ts
|   |   |   |-- useAutoRefresh.ts
|   |   |   |-- useFilterOrchestrator.ts
|   |   |   |-- usePaginationState.ts
|   |   |   |-- useQueryState.ts
|   |   |   |-- useRequestGuard.ts
|   |   |   |-- useSortableTable.ts
|   |   |   |-- useTraceProgress.ts
|   |   |   \-- useUrlSync.ts
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
|   |   |   |-- DataTable.test.js
|   |   |   |-- DateRangePicker.test.js
|   |   |   |-- FilterPanel.test.js
|   |   |   |-- HoldMatrix.test.js
|   |   |   |-- LoadingOverlay.test.js
|   |   |   |-- LoadingSpinner.test.js
|   |   |   |-- LotDetailTable.test.js
|   |   |   |-- MatrixTable.test.js
|   |   |   |-- ParetoGrid.test.js
|   |   |   \-- ProductionDetailTable.test.js
|   |   |-- core/
|   |   |   \-- api-dedup.test.js
|   |   |-- legacy/
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
|   |   |   |-- _auth.js
|   |   |   |-- downtime-analysis.spec.js
|   |   |   |-- hold-history-flat-table.spec.js
|   |   |   |-- hold-overview.spec.js
|   |   |   |-- job-abandon-on-unload.spec.js
|   |   |   |-- material-consumption-data-boundary.spec.ts
|   |   |   |-- material-consumption-resilience.spec.ts
|   |   |   |-- material-consumption.spec.ts
|   |   |   |-- production-history-cross-filter.spec.ts
|   |   |   |-- production-history-filter-options-error.spec.ts
|   |   |   |-- production-history-multi-line-input.spec.ts
|   |   |   |-- production-history-pruning-feedback.spec.ts
|   |   |   |-- production-history-query-mode-tabs.spec.ts
|   |   |   |-- production-history-wildcard-paste.spec.ts
|   |   |   |-- query-tool-url-state.spec.js
|   |   |   |-- query-tool.spec.js
|   |   |   |-- reject-history.spec.js
|   |   |   |-- reject-material-flat-table.spec.js
|   |   |   \-- wip-matrix-drilldown.spec.js
|   |   |-- query-tool/
|   |   |   |-- App.url-state.test.js
|   |   |   |-- EquipmentRejectsTable.test.js
|   |   |   \-- useLotDetail.pagination.test.js
|   |   |-- shared-composables/
|   |   |   |-- useAsyncJobPolling.test.js
|   |   |   |-- useAutoRefresh.test.js
|   |   |   \-- useRequestGuard.test.js
|   |   |-- validation/
|   |   |   |-- useHoldOverview.validation.test.js
|   |   |   |-- useMaterialTrace.validation.test.js
|   |   |   |-- useProductionHistory.validation.test.js
|   |   |   |-- useRejectHistory.validation.test.js
|   |   |   |-- useYieldAlert.validation.test.js
|   |   |   \-- wip-url-params.test.js
|   |   |-- yield-alert/
|   |   |   \-- App.cross-filter.test.js
|   |   |-- pending-jobs-registry.test.js
|   |   |-- schema-guard.test.js
|   |   \-- unwrap-api-result.test.js
|   |-- tmp/
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
|   |   |-- access_20260603_152534.log
|   |   |-- access_20260603_172418.log
|   |   |-- access_20260603_180940.log
|   |   |-- access_20260603_183313.log
|   |   |-- access_20260603_185357.log
|   |   |-- access_20260604_172108.log
|   |   |-- access_20260604_172435.log
|   |   |-- access_20260604_173558.log
|   |   |-- access_20260605_190831.log
|   |   |-- access_20260605_203928.log
|   |   |-- error_20260603_152534.log
|   |   |-- error_20260603_172418.log
|   |   |-- error_20260603_180940.log
|   |   |-- error_20260603_183313.log
|   |   |-- error_20260603_185357.log
|   |   |-- error_20260604_172108.log
|   |   |-- error_20260604_172435.log
|   |   |-- error_20260604_173558.log
|   |   |-- error_20260605_190831.log
|   |   |-- error_20260605_203928.log
|   |   |-- rq_msd_worker_20260603_152534.log
|   |   |-- rq_msd_worker_20260603_172418.log
|   |   |-- rq_msd_worker_20260603_180940.log
|   |   |-- rq_msd_worker_20260603_183313.log
|   |   |-- rq_msd_worker_20260603_185357.log
|   |   |-- rq_msd_worker_20260604_172108.log
|   |   |-- rq_msd_worker_20260604_172435.log
|   |   |-- rq_msd_worker_20260604_173558.log
|   |   |-- rq_msd_worker_20260605_190831.log
|   |   |-- rq_msd_worker_20260605_203928.log
|   |   |-- rq_prod_hist_worker_20260603_152534.log
|   |   |-- rq_prod_hist_worker_20260603_172418.log
|   |   |-- rq_prod_hist_worker_20260603_180940.log
|   |   |-- rq_prod_hist_worker_20260603_183313.log
|   |   |-- rq_prod_hist_worker_20260603_185357.log
|   |   |-- rq_prod_hist_worker_20260604_172108.log
|   |   |-- rq_prod_hist_worker_20260604_172435.log
|   |   |-- rq_prod_hist_worker_20260604_173558.log
|   |   |-- rq_prod_hist_worker_20260605_190831.log
|   |   |-- rq_prod_hist_worker_20260605_203928.log
|   |   |-- rq_reject_worker_20260603_152534.log
|   |   |-- rq_reject_worker_20260603_172418.log
|   |   |-- rq_reject_worker_20260603_180940.log
|   |   |-- rq_reject_worker_20260603_183313.log
|   |   |-- rq_reject_worker_20260603_185357.log
|   |   |-- rq_reject_worker_20260604_172108.log
|   |   |-- rq_reject_worker_20260604_172435.log
|   |   |-- rq_reject_worker_20260604_173558.log
|   |   |-- rq_reject_worker_20260605_190831.log
|   |   |-- rq_reject_worker_20260605_203928.log
|   |   \-- ... (30 more entries truncated; cap=50)
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
|   |-- rq_msd_worker.log
|   |-- rq_prod_hist_worker.log
|   |-- rq_reject_worker.log
|   |-- rq_worker.log
|   |-- rq_yield_alert_worker.log
|   |-- startup.log
|   \-- watchdog.log
|-- scripts/
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
|       |   |-- partial_failure_contract.py
|       |   |-- permissions.py
|       |   |-- query_quality_contract.py
|       |   |-- query_spool_store.py
|       |   |-- rate_limit.py
|       |   |-- redis_client.py
|       |   |-- redis_df_store.py
|       |   |-- request_validation.py
|       |   |-- resilience.py
|       |   |-- response.py
|       |   |-- runtime_contract.py
|       |   |-- spool_dir_check.py
|       |   |-- spool_pipeline.py
|       |   |-- spool_warmup_scheduler.py
|       |   |-- sync_worker.py
|       |   |-- utils.py
|       |   |-- watchdog_logging.py
|       |   |-- worker_memory_guard.py
|       |   \-- worker_recovery_policy.py
|       |-- routes/
|       |   |-- __init__.py
|       |   |-- admin_routes.py
|       |   |-- ai_routes.py
|       |   |-- analytics_routes.py
|       |   |-- dashboard_routes.py
|       |   |-- downtime_analysis_routes.py
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
|       |   |-- downtime_analysis_cache.py
|       |   |-- downtime_analysis_service.py
|       |   |-- event_fetcher.py
|       |   |-- filter_cache.py
|       |   |-- hold_dataset_cache.py
|       |   |-- hold_history_service.py
|       |   |-- hold_history_sql_runtime.py
|       |   |-- hold_today_snapshot_service.py
|       |   |-- internal_metrics_service.py
|       |   |-- job_query_service.py
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
|       |   |-- production_history_job_service.py
|       |   |-- production_history_service.py
|       |   |-- production_history_sql_runtime.py
|       |   |-- qc_gate_service.py
|       |   |-- query_tool_service.py
|       |   |-- query_tool_sql_runtime.py
|       |   |-- realtime_equipment_cache.py
|       |   |-- reason_filter_cache.py
|       |   |-- reject_cache_sql_runtime.py
|       |   |-- reject_dataset_cache.py
|       |   |-- reject_history_service.py
|       |   \-- ... (20 more entries truncated; cap=50)
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
|       |   \-- wildcards.py
|       |-- static/
|       |   |-- js/
|       |   |   \-- ... (max depth)
|       |   \-- favicon.svg
|       |-- templates/
|       |   |-- admin/
|       |   |   \-- ... (max depth)
|       |   |-- _base.html
|       |   |-- 403.html
|       |   |-- 404.html
|       |   |-- 500.html
|       |   |-- job_query.html
|       |   |-- portal.html
|       |   \-- query_tool.html
|       |-- __init__.py
|       |-- __main__.py
|       |-- app.py
|       \-- rq_worker_preload.py
|-- tests/
|   |-- e2e/
|   |   |-- __init__.py
|   |   |-- browser_helpers.py
|   |   |-- conftest.py
|   |   |-- test_admin_auth_e2e.py
|   |   |-- test_admin_dashboard_e2e.py
|   |   |-- test_anomaly_overview_e2e.py
|   |   |-- test_cache_e2e.py
|   |   |-- test_downtime_analysis_e2e.py
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
|   |   |-- spool_snapshots/
|   |   |   \-- job__gpta0008_q1/
|   |   |       \-- ... (max depth)
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
|   |   |-- test_fixtures_smoke.py
|   |   |-- test_multi_worker_concurrency.py
|   |   |-- test_oracle_error_codes.py
|   |   |-- test_oracle_error_path.py
|   |   |-- test_preload_fork_safety.py
|   |   |-- test_race_conditions.py
|   |   |-- test_real_multi_worker.py
|   |   |-- test_real_oracle_fault_injection.py
|   |   |-- test_redis_chaos.py
|   |   |-- test_redis_timeout_fallback.py
|   |   |-- test_rowcount_flag_parity.py
|   |   \-- test_soak_workload.py
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
|   |   |-- test_chunk_boundary.py
|   |   |-- test_cross_module_stress.py
|   |   |-- test_data_integrity.py
|   |   |-- test_frontend_stress.py
|   |   |-- test_hold_today_snapshot_stress.py
|   |   |-- test_load_collector_unit.py
|   |   |-- test_material_consumption_stress.py
|   |   |-- test_material_trace_stress.py
|   |   |-- test_mid_section_defect_stress.py
|   |   |-- test_production_history_stress.py
|   |   |-- test_query_tool_stress.py
|   |   |-- test_reject_history_stress.py
|   |   |-- test_resource_history_stress.py
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
|   |-- test_async_job_timeout.py
|   |-- test_async_query_job_service.py
|   |-- test_auth_integration.py
|   |-- test_auth_service.py
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
|   |-- test_core_exceptions.py
|   |-- test_cross_worker_result_sharing.py
|   |-- test_dashboard_routes.py
|   |-- test_dashboard_service.py
|   |-- test_database_redaction.py
|   \-- ... (163 more entries truncated; cap=50)
|-- tmp/
|   |-- query_spool/
|   |   |-- downtime_analysis_events/
|   |   |   \-- 81b038e23f2de450.parquet
|   |   |-- probe_100077.json
|   |   |-- probe_100130.json
|   |   |-- probe_100921.json
|   |   |-- probe_100922.json
|   |   |-- probe_102819.json
|   |   |-- probe_102820.json
|   |   |-- probe_103949.json
|   |   |-- probe_103950.json
|   |   |-- probe_104066.json
|   |   |-- probe_104103.json
|   |   |-- probe_104148.json
|   |   |-- probe_104219.json
|   |   |-- probe_104755.json
|   |   |-- probe_104756.json
|   |   |-- probe_105427.json
|   |   |-- probe_105796.json
|   |   |-- probe_105797.json
|   |   |-- probe_107068.json
|   |   |-- probe_107069.json
|   |   |-- probe_107450.json
|   |   |-- probe_107453.json
|   |   |-- probe_107593.json
|   |   |-- probe_108245.json
|   |   |-- probe_108246.json
|   |   |-- probe_108255.json
|   |   |-- probe_108256.json
|   |   |-- probe_109089.json
|   |   |-- probe_109090.json
|   |   |-- probe_109468.json
|   |   |-- probe_109469.json
|   |   |-- probe_109596.json
|   |   |-- probe_109597.json
|   |   |-- probe_10985.json
|   |   |-- probe_10990.json
|   |   |-- probe_110595.json
|   |   |-- probe_110745.json
|   |   |-- probe_110747.json
|   |   |-- probe_112201.json
|   |   |-- probe_112498.json
|   |   |-- probe_112650.json
|   |   |-- probe_112651.json
|   |   |-- probe_113602.json
|   |   |-- probe_113603.json
|   |   |-- probe_113666.json
|   |   |-- probe_113869.json
|   |   |-- probe_116133.json
|   |   |-- probe_116787.json
|   |   |-- probe_116823.json
|   |   |-- probe_117915.json
|   |   \-- ... (781 more entries truncated; cap=50)
|   |-- gunicorn.pid
|   |-- mes_dashboard_restart_state.json
|   |-- resource_history.duckdb
|   |-- rq_msd_worker.pid
|   |-- rq_prod_hist_worker.pid
|   |-- rq_reject_worker.pid
|   |-- rq_trace_worker.pid
|   |-- rq_yield_alert_worker.pid
|   \-- worker_watchdog.pid
|-- tools/
|   |-- generate_documentation.py
|   |-- query_table_schema.py
|   |-- test_oracle_connection.py
|   \-- update_oracle_authorized_objects.py
|-- .coverage
|-- .dockerignore
|-- .env
|-- .env.development
|-- .env.example
|-- .env.production
|-- .gitignore
|-- AGENTS.md
|-- Check.md
|-- CLAUDE.md
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
