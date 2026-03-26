## Why

The archived baseline change established a no-iframe SPA shell foundation, but route-view integration is still incomplete for day-to-day use. We need a controlled next phase that keeps drawer navigation stable, preserves page behavior during cutover, and avoids health/status UI overload while retaining diagnosability.

## What Changes

- Integrate rewritten pages directly into `portal-shell` route views and keep selected legacy pages on wrapper mode until rewrite is complete.
- Tighten drawer governance for mixed-mode navigation, including admin entry visibility and route fallback behavior.
- Refine shell health UX to show a compact summary by default and expose detailed diagnostics only on demand (expand/click).
- Add rollout guardrails for route switching with per-page smoke acceptance checklists and explicit rollback points.
- Complete wrapper-page rewrites (`job-query`, `excel-query`, `query-tool`, `tmtt-defect`) and decommission wrapper mode by final cutover.
- Enforce pre/post migration parity validation for table, chart, filter, interaction, and matrix behavior with release-blocking gates.

## Capabilities

### New Capabilities
- `shell-health-summary-detail`: Define summary-vs-detail behavior for shell health diagnostics and user interaction contract.

### Modified Capabilities
- `spa-shell-navigation`: Extend requirements from baseline shell to route-view integration and mixed-mode routing behavior.
- `portal-drawer-navigation`: Update drawer requirements for route readiness, admin entry handling, and fallback semantics.
- `legacy-page-wrapper-strategy`: Clarify temporary wrapper usage boundaries and promotion criteria from wrapper to rewrite.
- `migration-gates-and-rollout`: Add enforcement for smoke checklist completion before enabling direct shell route cutover.
- `report-effects-parity`: Strengthen parity requirements for table/chart/filter/interaction/matrix semantics and evidence capture.

## Impact

- Frontend shell code: `frontend/src/portal-shell/**`, `frontend/src/portal/main.js`, related shared UI/composables.
- Backend contracts and health API: navigation metadata provider and shell health endpoint payload/representation.
- Test suites: portal shell route tests, health endpoint tests, route/drawer integration smoke tests.
- Migration docs and operational runbooks for cutover/rollback and acceptance evidence.
- Legacy module modernization scope: wrapper-first pages must reach native route-view integration before this change is complete.
- Pre/post parity evidence pipeline: baseline snapshots, visual/interaction smoke records, and gate reports for table/chart/filter/matrix parity.
