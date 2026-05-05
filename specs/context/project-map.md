---
artifact: project-map
generated-by: cdd-kit context-scan
schema-version: 1
root: DashBoard_vite
visible-dirs: 294
visible-files: 878
omitted-dirs: 105
truncated-dirs: 7
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
|   |-- context-policy.json
|   \-- model-policy.json
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
|   |   |-- 01ac26600a99dcaa
|   |   |-- 028b26de3bd91d6a
|   |   |-- 02bca2c9d2f8566d
|   |   |-- 0478f49b48ee4a27
|   |   |-- 04f75a340f5aee98
|   |   |-- 06e37be44b7c2558
|   |   |-- 08745ff61ac492c1
|   |   |-- 09285e556a014b0c
|   |   |-- 09af02b32eace3be
|   |   |-- 0ac8c61031ebb16b
|   |   |-- 0bc782813901ee7f
|   |   |-- 0c14e8a6e0dfaa9a
|   |   |-- 0e749cfd569a40b7
|   |   |-- 11815b8e122a7f29
|   |   |-- 148861a8d0e5c483
|   |   |-- 1a1983b4680d2470
|   |   |-- 1bd126f84a2f6572
|   |   |-- 1fcb892092629696
|   |   |-- 1fe4d4106549ecd9
|   |   |-- 2079893a07ce42c4
|   |   |-- 20a29d650996dc03
|   |   |-- 22775c7be38c0fc8
|   |   |-- 23347e16dbdb08ae
|   |   |-- 2487e0dd67ee4005
|   |   |-- 2513622121cc3cd3
|   |   |-- 2550e0b05b884943
|   |   |-- 256f0124da909fa3
|   |   |-- 25db02c884e47e34
|   |   |-- 263226a93d9fd720
|   |   |-- 267688019eacc507
|   |   |-- 27e483e573db703b
|   |   |-- 2ab6068320c1832c
|   |   |-- 2b2923cb2e7b99f7
|   |   |-- 2bed5af1a1ea5659
|   |   |-- 2d3a3f69d4e8aa6d
|   |   |-- 2f2ae64af48e93fe
|   |   |-- 2f46fe56abf81670
|   |   |-- 314c411df6192c80
|   |   |-- 3240b7b84e21f638
|   |   |-- 3247c74d4d5e4ad2
|   |   |-- 327c52ae13744797
|   |   |-- 3399b41644e40c25
|   |   |-- 3453e8fac951ce5c
|   |   |-- 349505052d6929ea
|   |   |-- 36c681f3d6d05607
|   |   |-- 370b8fa4575b8f05
|   |   |-- 374a27ac8e75b801
|   |   |-- 392d6328bece7db8
|   |   \-- ... (154 more entries truncated; cap=50)
|   |-- examples/
|   |   |-- 04e6b3400353b141/
|   |   |   |-- 13e0290a1a9c0bba
|   |   |   |-- 25780db009731065
|   |   |   |-- 70f32d79fe32806f
|   |   |   |-- 732eb1d55d40a61c
|   |   |   |-- 7373c906dd3afb5f
|   |   |   |-- 8355f184023fed84
|   |   |   |-- 8b239543e3d9cc8d
|   |   |   |-- 920c57710c454aff
|   |   |   |-- 9ac95d917e947b9e
|   |   |   |-- 9f91d507623b59fd
|   |   |   \-- c52b7cce57e8e75b
|   |   |-- 13e0290a1a9c0bba/
|   |   |   |-- 117fab2cf7adb151
|   |   |   \-- 646fdc58526d8e4b
|   |   |-- 25780db009731065/
|   |   |   |-- 00dafc6aa48d981b
|   |   |   |-- 1589d6fe81f1163c
|   |   |   |-- 18be135b6dea1c2e
|   |   |   |-- 19d5c06e2c24ff09
|   |   |   |-- 1a53d22937da2da4
|   |   |   |-- 1b4e7c221e209087
|   |   |   |-- 1ea9dffb42f008e9
|   |   |   |-- 1ede9c758cafd806
|   |   |   |-- 21586c920324c323
|   |   |   |-- 2357e3ccb321904b
|   |   |   |-- 2a909f01d30bb093
|   |   |   |-- 2d99c3ac78c0adf6
|   |   |   |-- 2e2d752dd8edb6a6
|   |   |   |-- 38654a8b1100508d
|   |   |   |-- 3b64986a97a66f60
|   |   |   |-- 3d2bd52e3c6cffb9
|   |   |   |-- 3e0e3607ef615f86
|   |   |   |-- 3f5b694523d49bef
|   |   |   |-- 41990b7e05df85c3
|   |   |   |-- 4721f12d094ceeeb
|   |   |   |-- 48fb418d34c790ae
|   |   |   |-- 4a4e41697813dc4b
|   |   |   |-- 4a626573fbb38a40
|   |   |   |-- 4b0cddf8df71db53
|   |   |   |-- 4b3c7dccc7762ce1
|   |   |   |-- 537d8c5bb433eeb3
|   |   |   |-- 578e2da8b08786b6
|   |   |   |-- 58a8c7542f3649f1
|   |   |   |-- 5e9016a0c2aa5f2f
|   |   |   |-- 5f3c74f848debe67
|   |   |   |-- 5fa18edf990aa121
|   |   |   |-- 60fb06582833a47a
|   |   |   |-- 6675009269427d52
|   |   |   |-- 681e57af582a68fb
|   |   |   |-- 6a1191e630cb1e10
|   |   |   |-- 6a70189c3877c917
|   |   |   |-- 6f4000ed1b1098ae
|   |   |   |-- 742d6813cde824f8
|   |   |   |-- 773960fb21ed98db
|   |   |   |-- 7fcda584183b109a
|   |   |   |-- 80456afa8bacfb09
|   |   |   |-- 863b8c40345e11f1
|   |   |   |-- 86c5344306e98019
|   |   |   |-- 89eaa4c075bb5e83
|   |   |   |-- 8e9e5243197432a3
|   |   |   |-- 90645ff6fb123d49
|   |   |   |-- 90b09cf3efdd0912
|   |   |   |-- 95108d21f1bc2462
|   |   |   |-- 994b10e745844634
|   |   |   |-- 9c32bd0137e3a2b0
|   |   |   \-- ... (29 more entries truncated; cap=50)
|   |   |-- 70f32d79fe32806f/
|   |   |   \-- 241907265b8f643b
|   |   |-- 732eb1d55d40a61c/
|   |   |   \-- 59a0424d9d1db2bd
|   |   |-- 7373c906dd3afb5f/
|   |   |   |-- 2428427b872c86d2
|   |   |   |-- 725376f2f5f843c6
|   |   |   |-- af1171caaba222fc
|   |   |   |-- e2ad4d0c52a24b99
|   |   |   |-- e84a7b98ab0c83e9
|   |   |   \-- fe217628c71bb5ac
|   |   |-- 8355f184023fed84/
|   |   |   \-- 241907265b8f643b
|   |   |-- 8b239543e3d9cc8d/
|   |   |   \-- 59a0424d9d1db2bd
|   |   |-- 920c57710c454aff/
|   |   |   \-- b39cb8cc4b6a5b4f
|   |   |-- 9ac95d917e947b9e/
|   |   |   \-- 2cc28d71ff5ec552
|   |   |-- 9f91d507623b59fd/
|   |   |   \-- afd8f8308bb2d703
|   |   \-- c52b7cce57e8e75b/
|   |       \-- 9f12751898102a73
|   |-- unicode_data/
|   |   \-- 14.0.0/
|   |       |-- charmap.json.gz
|   |       \-- codec-utf-8.json.gz
|   \-- .gitignore
|-- artifacts/
|   |-- mutation-B/
|   |   |-- baseline/
|   |   |   \-- soak-metrics-1776814981.json
|   |   |-- mutated/
|   |   |   \-- soak-metrics-1776776688.json
|   |   |-- mutated-v2/
|   |   |   \-- soak-metrics-1776814121.json
|   |   |-- mutated-v3/
|   |   |   \-- soak-metrics-1776814608.json
|   |   |-- baseline-pytest.log
|   |   |-- mutated-pytest.log
|   |   |-- mutated-v2-pytest.log
|   |   \-- mutated-v3-pytest.log
|   |-- soak-local/
|   |   |-- 20260421T114824Z/
|   |   |   \-- soak-metrics-1776772408.json
|   |   \-- 20260424T023505Z/
|   |       \-- soak-metrics-1776998409.json
|   |-- stability-local/
|   |   |-- stability-20260422T010200Z.jsonl
|   |   |-- stability-20260422T010200Z.log
|   |   |-- stability-20260423T000218Z.jsonl
|   |   \-- stability-20260423T000218Z.log
|   \-- stability-pilot.jsonl
|-- ci/
|   |-- gate-policy.md
|   |-- playwright-nightly.md
|   \-- required-check-policy.md
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
|   |-- mes-dashboard-msd-worker.service
|   |-- mes-dashboard-reject-worker.service
|   |-- mes-dashboard-trace-worker.service
|   |-- mes-dashboard-watchdog.service
|   \-- mes-dashboard.service
|-- docs/
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
|   |-- ci_real_infra_gate_policy.md
|   |-- hold_history.md
|   \-- real_infra_stability_report.md
|-- frontend/
|   |-- logs/
|   |   \-- admin_logs.sqlite
|   |-- scripts/
|   |   \-- css-governance-check.js
|   |-- src/
|   |   |-- admin-dashboard/
|   |   |   |-- tabs/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- admin-performance/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- admin-shared/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   \-- composables/
|   |   |       \-- ... (max depth)
|   |   |-- admin-user-usage-kpi/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- anomaly-overview/
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- assets/
|   |   |   \-- fonts/
|   |   |       \-- ... (max depth)
|   |   |-- core/
|   |   |   |-- api.js
|   |   |   |-- app-version-check.js
|   |   |   |-- autocomplete.js
|   |   |   |-- compute.js
|   |   |   |-- datetime.js
|   |   |   |-- dev-warnings.js
|   |   |   |-- duckdb-activation-policy.js
|   |   |   |-- duckdb-client.js
|   |   |   |-- endpoint-schemas.js
|   |   |   |-- field-contracts.js
|   |   |   |-- pending-jobs-registry.js
|   |   |   |-- post-export.js
|   |   |   |-- reject-history-filters.js
|   |   |   |-- resource-history-filters.js
|   |   |   |-- risk-score.js
|   |   |   |-- schema-guard.js
|   |   |   |-- shell-navigation.js
|   |   |   |-- table-tree.js
|   |   |   |-- unwrap-api-result.js
|   |   |   |-- wip-derive.js
|   |   |   \-- wip-navigation-state.js
|   |   |-- hold-detail/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- hold-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   |-- style.css
|   |   |   |-- useAutoRefresh.js
|   |   |   \-- useHoldHistoryDuckDB.js
|   |   |-- hold-overview/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- job-query/
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- material-trace/
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- mid-section-defect/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
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
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- qc-gate/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- query-tool/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- utils/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- reject-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   |-- style.css
|   |   |   \-- useRejectHistoryDuckDB.js
|   |   |-- resource-history/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   |-- style.css
|   |   |   \-- useResourceHistoryDuckDB.js
|   |   |-- resource-shared/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- constants.js
|   |   |   \-- styles.css
|   |   |-- resource-status/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- shared-composables/
|   |   |   |-- index.js
|   |   |   |-- TraceProgressBar.vue
|   |   |   |-- useAiChat.js
|   |   |   |-- useAsyncJobPolling.js
|   |   |   |-- useAutocomplete.js
|   |   |   |-- useAutoRefresh.js
|   |   |   |-- useFilterOrchestrator.js
|   |   |   |-- usePaginationState.js
|   |   |   |-- useQueryState.js
|   |   |   |-- useRequestGuard.js
|   |   |   |-- useSortableTable.js
|   |   |   |-- useTraceProgress.js
|   |   |   \-- useUrlSync.js
|   |   |-- shared-ui/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   \-- index.js
|   |   |-- styles/
|   |   |   \-- tailwind.css
|   |   |-- tables/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- wip-detail/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- wip-overview/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- App.vue
|   |   |   |-- index.html
|   |   |   |-- main.js
|   |   |   \-- style.css
|   |   |-- wip-shared/
|   |   |   |-- components/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- composables/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- constants.js
|   |   |   |-- pareto-styles.css
|   |   |   \-- styles.css
|   |   |-- workers/
|   |   |   \-- duckdb-worker.js
|   |   \-- yield-alert-center/
|   |       |-- App.vue
|   |       |-- index.html
|   |       |-- main.js
|   |       |-- style.css
|   |       |-- useYieldAlertDuckDB.js
|   |       |-- utils.js
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
|   |   |   \-- ParetoGrid.test.js
|   |   |-- core/
|   |   |   \-- api-dedup.test.js
|   |   |-- legacy/
|   |   |   |-- admin-dashboard.test.js
|   |   |   |-- admin-performance.test.js
|   |   |   |-- admin-user-usage-kpi.test.js
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
|   |   |   |-- hold-overview.spec.js
|   |   |   |-- job-abandon-on-unload.spec.js
|   |   |   |-- query-tool-url-state.spec.js
|   |   |   |-- query-tool.spec.js
|   |   |   \-- reject-history.spec.js
|   |   |-- query-tool/
|   |   |   |-- App.url-state.test.js
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
|   |   |   \-- useYieldAlert.validation.test.js
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
|   |-- vite.config.js
|   \-- vitest.config.js
|-- logs/
|   |-- admin_logs.sqlite
|   \-- login_sessions.sqlite
|-- openspec/
|   |-- archive/
|   |   |-- 2026-03-26-system-status-and-online-presence/
|   |   |   |-- specs/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- .openspec.yaml
|   |   |   |-- design.md
|   |   |   |-- proposal.md
|   |   |   \-- tasks.md
|   |   \-- 2026-03-27-msd-lineage-memory-protection/
|   |       |-- specs/
|   |       |   \-- ... (max depth)
|   |       |-- .openspec.yaml
|   |       |-- design.md
|   |       |-- proposal.md
|   |       \-- tasks.md
|   |-- changes/
|   |   |-- archive/
|   |   |   |-- 2026-02-07-dashboard-vite-complete-migration/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-07-dashboard-vite-root-refactor/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-07-hold-detail-vite-hardening/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-07-stability-and-frontend-compute-shift/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-07-vite-jinja-report-parity-hardening/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-p0-runtime-stability-hardening/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-p1-cache-query-efficiency/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-p2-ops-self-healing-runbook/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-post-migration-resilience-governance/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-residual-hardening-round3/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-residual-hardening-round4/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-08-security-stability-hardening-round2/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-09-dynamic-nav-management/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-09-harden-mid-section-defect/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-09-migrate-resource-duo-vue/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-09-migrate-tables-vue/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-09-migrate-wip-trio-vue/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-09-qc-gate-report/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-10-hold-history-dashboard/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-10-hold-lot-overview/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-10-wip-filter-persistence/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-11-equipment-cache-dedup/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-11-fluid-layout-collapsible-sidebar/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-11-portal-no-iframe-navigation/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-11-portal-shell-route-view-integration/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-12-deferred-route-modernization-follow-up/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-12-full-modernization-architecture-blueprint/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-12-modernization-hardening-follow-up/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-12-trace-progressive-ui/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-12-unified-lineage-engine/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-13-query-tool-rewrite/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-13-reject-history-query-page/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-22-query-tool-lineage-model-alignment/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-22-reject-history-ui-polish/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-22-report-filter-strategy-hardening/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-22-wip-overview-filter-dropdown-search/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-23-admin-performance-vue-spa/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-23-released-pages-production-hardening/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-24-full-line-defect-trace/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-25-hold-resource-history-dataset-cache/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-25-trace-pipeline-pool-isolation/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-02-26-admin-perf-vue-migration-monitoring-gaps/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-historical-query-slow-connection/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-msd-multifactor-backward-tracing/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-qc-gate-lot-package-column/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-reject-history-multi-pareto-layout/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-reject-history-pareto-datasource-fix/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-reject-history-pareto-ux-enhancements/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-02-unified-batch-query-redis-cache/
|   |   |   |   \-- ... (max depth)
|   |   |   |-- 2026-03-03-add-material-trace-page/
|   |   |   |   \-- ... (max depth)
|   |   |   \-- ... (86 more entries truncated; cap=50)
|   |   \-- harden-real-infra-test-coverage/
|   |       |-- specs/
|   |       |   \-- ... (max depth)
|   |       |-- design.md
|   |       |-- pr_description_template.md
|   |       |-- proposal.md
|   |       \-- tasks.md
|   |-- specs/
|   |   |-- accessibility-foundation/
|   |   |   \-- spec.md
|   |   |-- admin-dashboard-frontend/
|   |   |   \-- spec.md
|   |   |-- admin-performance-spa/
|   |   |   \-- spec.md
|   |   |-- admin-shared-components/
|   |   |   \-- spec.md
|   |   |-- ai-agent-loop/
|   |   |   \-- spec.md
|   |   |-- ai-chat-sql-display/
|   |   |   \-- spec.md
|   |   |-- ai-clarification-flow/
|   |   |   \-- spec.md
|   |   |-- ai-schema-context/
|   |   |   \-- spec.md
|   |   |-- ai-text-to-sql-pipeline/
|   |   |   \-- spec.md
|   |   |-- ai-tool-definitions/
|   |   |   \-- spec.md
|   |   |-- ai-tool-executor/
|   |   |   \-- spec.md
|   |   |-- anomaly-indicator-header/
|   |   |   \-- spec.md
|   |   |-- anomaly-overview-page/
|   |   |   \-- spec.md
|   |   |-- anomaly-summary-api/
|   |   |   \-- spec.md
|   |   |-- api-response-contract-unification/
|   |   |   \-- spec.md
|   |   |-- api-safety-hygiene/
|   |   |   \-- spec.md
|   |   |-- archive-log-rotation/
|   |   |   \-- spec.md
|   |   |-- asset-readiness-and-fallback-retirement/
|   |   |   \-- spec.md
|   |   |-- async-job-stress-probe/
|   |   |   \-- spec.md
|   |   |-- async-query-job-service/
|   |   |   \-- spec.md
|   |   |-- backend-integration-test-coverage/
|   |   |   \-- spec.md
|   |   |-- backend-unit-test-coverage/
|   |   |   \-- spec.md
|   |   |-- batch-query-resilience/
|   |   |   \-- spec.md
|   |   |-- cache-indexed-query-acceleration/
|   |   |   \-- spec.md
|   |   |-- cache-observability-hardening/
|   |   |   \-- spec.md
|   |   |-- cache-plane-architecture/
|   |   |   \-- spec.md
|   |   |-- cache-telemetry-api/
|   |   |   \-- spec.md
|   |   |-- chart-interaction-hardening/
|   |   |   \-- spec.md
|   |   |-- chip-component/
|   |   |   \-- spec.md
|   |   |-- chunk-boundary-probe/
|   |   |   \-- spec.md
|   |   |-- ci-test-orchestration/
|   |   |   \-- spec.md
|   |   |-- collapsible-sidebar-drawer/
|   |   |   \-- spec.md
|   |   |-- component-style-unification/
|   |   |   \-- spec.md
|   |   |-- conda-systemd-runtime-alignment/
|   |   |   \-- spec.md
|   |   |-- connection-pool-monitoring/
|   |   |   \-- spec.md
|   |   |-- container-filter-cache/
|   |   |   \-- spec.md
|   |   |-- cross-worker-result-integrity/
|   |   |   \-- spec.md
|   |   |-- data-integrity-probe/
|   |   |   \-- spec.md
|   |   |-- data-table-component/
|   |   |   \-- spec.md
|   |   |-- dataset-cache-metadata-only-redis/
|   |   |   \-- spec.md
|   |   |-- dataset-cache-warmup/
|   |   |   \-- spec.md
|   |   |-- design-token-expansion/
|   |   |   \-- spec.md
|   |   |-- distributed-lock-policy/
|   |   |   \-- spec.md
|   |   |-- drawer-management/
|   |   |   \-- spec.md
|   |   |-- e2e-test-coverage/
|   |   |   \-- spec.md
|   |   |-- empty-state/
|   |   |   \-- spec.md
|   |   |-- equipment-sync-dedup/
|   |   |   \-- spec.md
|   |   |-- erp-reject-history-linkage/
|   |   |   \-- spec.md
|   |   |-- event-fetcher-unified/
|   |   |   \-- spec.md
|   |   |-- feature-page-unification/
|   |   |   \-- spec.md
|   |   \-- ... (118 more entries truncated; cap=50)
|   |-- config.yaml
|   \-- openapi.yaml
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
|   \-- templates/
|       |-- archive.md
|       |-- change-classification.md
|       |-- change-request.md
|       |-- ci-gates.md
|       |-- context-manifest.md
|       |-- contracts.md
|       |-- current-behavior.md
|       |-- design.md
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
|       |   |-- health_routes.py
|       |   |-- hold_history_routes.py
|       |   |-- hold_overview_routes.py
|       |   |-- hold_routes.py
|       |   |-- internal_routes.py
|       |   |-- job_query_routes.py
|       |   |-- job_routes.py
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
|       |   |-- event_fetcher.py
|       |   |-- filter_cache.py
|       |   |-- hold_dataset_cache.py
|       |   |-- hold_history_service.py
|       |   |-- hold_history_sql_runtime.py
|       |   |-- hold_today_snapshot_service.py
|       |   |-- internal_metrics_service.py
|       |   |-- job_query_service.py
|       |   |-- lineage_engine.py
|       |   |-- material_trace_duckdb_runtime.py
|       |   |-- material_trace_service.py
|       |   |-- mid_section_defect_service.py
|       |   |-- msd_duckdb_runtime.py
|       |   |-- msd_lineage_job_service.py
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
|       |   |-- reject_pareto_materialized.py
|       |   |-- reject_query_job_service.py
|       |   |-- resource_cache.py
|       |   |-- resource_dataset_cache.py
|       |   |-- resource_history_service.py
|       |   \-- ... (14 more entries truncated; cap=50)
|       |-- sql/
|       |   |-- analytics/
|       |   |   \-- ... (max depth)
|       |   |-- dashboard/
|       |   |   \-- ... (max depth)
|       |   |-- hold_history/
|       |   |   \-- ... (max depth)
|       |   |-- job_query/
|       |   |   \-- ... (max depth)
|       |   |-- lineage/
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
|       |   \-- loader.py
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
|   |   |-- test_admin_performance_e2e.py
|   |   |-- test_admin_user_usage_kpi_e2e.py
|   |   |-- test_anomaly_overview_e2e.py
|   |   |-- test_cache_e2e.py
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
|   |   |-- test_tables_e2e.py
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
|   |   |-- test_race_conditions.py
|   |   |-- test_real_multi_worker.py
|   |   |-- test_real_oracle_fault_injection.py
|   |   |-- test_redis_chaos.py
|   |   |-- test_redis_timeout_fallback.py
|   |   \-- test_soak_workload.py
|   |-- manual/
|   |   \-- test_job_owner_auth_live.py
|   |-- property/
|   |   |-- __init__.py
|   |   |-- conftest.py
|   |   |-- README.md
|   |   |-- strategies.py
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
|   |   \-- test_url_state_roundtrip.py
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
|   |-- test_database_slow_circuit_breaker.py
|   \-- ... (151 more entries truncated; cap=50)
|-- tmp/
|   |-- query_spool/
|   |   |-- anomaly_hold_dataset/
|   |   |   \-- 7c193f4e1ec6e300.parquet
|   |   |-- hold_dataset/
|   |   |   |-- 44249536daa7ea5e.parquet
|   |   |   |-- 4bd16ea73a4bbf32.parquet
|   |   |   \-- 95e42fcaaa327839.parquet
|   |   |-- msd-events/
|   |   |-- reject_dataset/
|   |   |   |-- 3511280f81a0f4eb.parquet
|   |   |   |-- 679917c51221d095.parquet
|   |   |   \-- 78e599fe0d8d79c7.parquet
|   |   |-- resource_dataset/
|   |   |   |-- 44404b8c8320a4dc.parquet
|   |   |   \-- c5c811f2b223e0cf.parquet
|   |   |-- resource_oee/
|   |   |   |-- 44404b8c8320a4dc.parquet
|   |   |   \-- c5c811f2b223e0cf.parquet
|   |   |-- yield_alert_dataset/
|   |   |   |-- b14cb138e6173d12.parquet
|   |   |   |-- d34c4109d641dd36.parquet
|   |   |   \-- f90475d8fa771e62.parquet
|   |   |-- probe_100077.json
|   |   |-- probe_100130.json
|   |   |-- probe_102819.json
|   |   |-- probe_102820.json
|   |   |-- probe_103949.json
|   |   |-- probe_103950.json
|   |   |-- probe_104148.json
|   |   |-- probe_104755.json
|   |   |-- probe_104756.json
|   |   |-- probe_105796.json
|   |   |-- probe_105797.json
|   |   |-- probe_107068.json
|   |   |-- probe_107069.json
|   |   |-- probe_107593.json
|   |   |-- probe_108245.json
|   |   |-- probe_108246.json
|   |   |-- probe_109596.json
|   |   |-- probe_109597.json
|   |   |-- probe_10985.json
|   |   |-- probe_10990.json
|   |   |-- probe_112201.json
|   |   |-- probe_112498.json
|   |   |-- probe_113666.json
|   |   |-- probe_113869.json
|   |   |-- probe_116133.json
|   |   |-- probe_118725.json
|   |   |-- probe_119972.json
|   |   |-- probe_121043.json
|   |   |-- probe_121048.json
|   |   |-- probe_121848.json
|   |   |-- probe_121849.json
|   |   |-- probe_121887.json
|   |   |-- probe_121888.json
|   |   |-- probe_128430.json
|   |   |-- probe_128521.json
|   |   |-- probe_128558.json
|   |   |-- probe_128645.json
|   |   |-- probe_128799.json
|   |   |-- probe_128859.json
|   |   |-- probe_128901.json
|   |   |-- probe_128971.json
|   |   |-- probe_129725.json
|   |   |-- probe_129909.json
|   |   \-- ... (243 more entries truncated; cap=50)
|   \-- mes_dashboard_restart_state.json
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
|-- TDD.md
\-- ts-migration-plan.md
```
