## 0. Implementation Kickoff (Apply Session Day-1)

- [x] 0.1 Generate and commit migration baseline snapshots (drawer visibility, route/query contracts, critical API payload key/type).
- [x] 0.2 Create parity checklist artifacts mapped to the functional parity matrix routes.
- [x] 0.3 Define and verify cutover control mechanism (feature flag / env toggle) before any breaking navigation change.
- [x] 0.4 Record rollback rehearsal plan with target recovery SLO and responsible operator steps.

## 1. Drawer Baseline and Governance Contract

- [x] 1.1 Capture the current production drawer baseline from `data/page_status.json` (id/name/order/admin_only/pages) as migration reference data.
- [x] 1.2 Define canonical drawer responsibilities: IA grouping, ordering, and permission visibility only (no iframe/frame loading semantics).
- [x] 1.3 Define a drawer-route consistency contract (route exists, drawer exists, order is valid, admin_only behavior is deterministic).
- [x] 1.4 Add validation checks/tests for admin and non-admin drawer visibility against the current baseline configuration.
- [x] 1.5 Define `frame_id/tool_src` deprecation policy and transition checkpoints.

## 2. SPA Shell and Router Foundation

- [x] 2.1 Create a SPA shell entry for portal navigation using Vue 3 + Vue Router.
- [x] 2.2 Build router records from drawer/page route contracts while preserving existing URL compatibility.
- [x] 2.3 Implement router-aware sidebar active state and breadcrumb/title metadata handling.
- [x] 2.4 Align auth/permission checks between backend route guard and frontend navigation guard behavior.
- [x] 2.5 Keep health-status widget behavior available in shell without iframe coupling.

## 3. Portal Iframe Decommission

- [x] 3.1 Refactor `portal.html` to remove iframe panel DOM and switch sidebar metadata to route-driven navigation.
- [x] 3.2 Refactor `frontend/src/portal/main.js` to remove frame activation/lazy-load/unload logic.
- [x] 3.3 Replace iframe-specific UI states with route-transition states and loading indicators.
- [x] 3.4 Remove portal CSS rules that target iframe layout while preserving current visual structure.
- [x] 3.5 Verify non-admin/admin navigation outcomes for all current drawers under direct routing.

## 4. Tailwind Design System Bootstrap

- [x] 4.1 Introduce Tailwind CSS + PostCSS configuration into the frontend build pipeline.
- [x] 4.2 Define design tokens (color, spacing, typography, radius, elevation, z-index) mapped to existing UI language.
- [x] 4.3 Establish global base/component/utility layers and migration-safe style ordering.
- [x] 4.4 Define style governance rules to prevent new large page-local CSS during migration.
- [x] 4.5 Publish migration guide for converting existing CSS modules/pages to Tailwind patterns.

## 5. Shared UI and Composable Consolidation

- [x] 5.1 Inventory duplicated UI patterns across WIP/Resource/Hold/QC pages (filter bar, KPI cards, tables, pagination, badges, banners).
- [x] 5.2 Create shared UI component layer and normalize props/events/slot contracts.
- [x] 5.3 Consolidate cross-page composables (auto-refresh, autocomplete, query state, pagination state) under shared modules.
- [x] 5.4 Migrate existing pages to shared components incrementally with visual parity checks.
- [x] 5.5 Remove obsolete duplicated component/style artifacts after each migration batch.

## 6. Legacy Page Wrapper Phase (Confirmed Decision)

- [x] 6.1 Implement wrapper integration for `job-query` inside the new router/shell flow.
- [x] 6.2 Implement wrapper integration for `excel-query` inside the new router/shell flow.
- [x] 6.3 Implement wrapper integration for `query-tool` inside the new router/shell flow.
- [x] 6.4 Implement wrapper integration for `tmtt-defect` inside the new router/shell flow.
- [x] 6.5 Define wrapper-level telemetry (load success, error, latency) and fallback behavior.
- [x] 6.6 Document hard exit criteria that determine when each wrapped page can be considered rewrite-ready.

## 7. Legacy Rewrite Execution (Post-Wrapper)

- Reference checklist: `docs/migration/portal-no-iframe/legacy_rewrite_smoke_checklists.md`
- Reference exemplar: `docs/migration/portal-no-iframe/tmtt_rewrite_exemplar.md`
- Reference playbook: `docs/migration/portal-no-iframe/legacy_rewrite_playbook.md`
- Reference decommission record: `docs/migration/portal-no-iframe/wrapper_decommission_report.md`
- [x] 7.1 Prioritize rewrite order among wrapped pages using usage/complexity/risk scoring.
- [x] 7.2 Rewrite first legacy page as canonical migration exemplar with shared UI + Tailwind.
- [x] 7.3 Rewrite remaining three legacy pages with reusable migration playbook and acceptance criteria.
- [x] 7.4 Decommission wrappers after rewrite completion and parity validation.

## 8. Interaction and Motion System

- [x] 8.1 Define baseline motion guidelines using Vue Transition (route transitions, panel changes, loading states).
- [x] 8.2 Implement reduced-motion accessibility behavior and fallback styles.
- [x] 8.3 Add key interaction transitions for filter apply, chart/table refresh, and drawer navigation.
- [x] 8.4 Define an escalation rule for when GSAP (or equivalent) is allowed beyond baseline transitions.

## 9. Testing, Quality Gates, and Performance

- [x] 9.1 Update unit/template tests from iframe assumptions to router/drawer contract assertions.
- [x] 9.2 Update E2E and stress suites to validate route navigation stability instead of iframe switching.
- [x] 9.3 Add regression tests for drawer ordering, admin_only filtering, and mixed release/dev visibility.
- [x] 9.4 Add contract tests for legacy wrapper routing and fallback behavior.
- [x] 9.5 Establish performance baselines (first paint, route switch latency, memory footprint) and compare pre/post migration.

## 10. Rollout, Cleanup, and Spec Closure

- [x] 10.1 Define phased rollout plan with canary scope and success/error thresholds.
- [x] 10.2 Define rollback strategy for shell/router cutover and wrapper failures.
- [x] 10.3 Remove `frame_id/tool_src` from runtime navigation payload after wrapper-to-rewrite milestones are complete.
- [x] 10.4 Sync changed requirements into main specs and prepare archive criteria for this migration change.

## 11. Cutover Gate Enforcement (Measurable)

- [x] 11.1 Enforce G1 route availability gate: P0 routes return 2xx/3xx at 100% pass rate in release validation.
- [x] 11.2 Enforce G2 drawer parity gate: admin/non-admin visible route sets must match pre-migration baseline exactly (delta = 0).
- [x] 11.3 Enforce G3 workflow parity gate: one critical smoke flow per route in parity matrix must pass at 100%.
- [x] 11.4 Enforce G4 client stability gate: zero unhandled JavaScript runtime errors on critical E2E paths.
- [x] 11.5 Enforce G5 data contract gate: required payload key/type parity checks must pass for all critical APIs.
- [x] 11.6 Enforce G7 rollback readiness gate: rollback rehearsal must recover stable navigation within target SLO (e.g., <= 15 minutes).
