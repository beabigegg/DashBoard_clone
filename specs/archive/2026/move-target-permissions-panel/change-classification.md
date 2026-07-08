# Change Classification

## Change Types
- primary: ui-only-change (relocate `TargetPermissionsPanel.vue` from the `admin-pages` app into a new tab of the `admin-dashboard` app + CSS re-scope)
- secondary: refactor (cross-app component relocation within the admin surface)

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- cross-module (two separate Vite apps — `admin-dashboard`, `admin-pages` — plus `admin-shared`; contained to the admin surface)

## Tier
- 3

## Architecture Review Required
- no
- reason: (n/a) The target pattern is already prescribed by the change-request (existing `tabs` array + `defineAsyncComponent`, tab component under `admin-dashboard/tabs/`, `.theme-admin-dashboard` scope). No new route, no new data flow, no migration/rollback decision. The one open decision (remove-from-`admin-pages` vs keep-both) is a delivery detail for `implementation-planner` to record, not a module-boundary architecture decision.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current placement is fully described in change-request Known Context; no separate product investigation needed. |
| proposal.md | no | Scope and goal are unambiguous. |
| spec.md | no | No user-facing behavior decision beyond relocation. |
| design.md | no | Architecture Review not required; pattern is prescribed. |
| qa-report.md | no | Routine pass/fail belongs in `agent-log/qa-reviewer.yml` unless a blocking/approved-with-risk finding arises. |
| regression-report.md | no | Regression scope (admin-pages after panel move) covered by updating `admin-pages.spec.ts`; log pointer suffices unless a regression is found. |
| visual-review-report.md | yes | UI relocation across apps benefits from a durable before/after visual evidence bundle of the new `admin-dashboard` tab placement and the old `admin-pages` state. |
| monkey-test-report.md | no | No new interaction complexity. |
| stress-soak-report.md | no | No load/refresh/queue/long-running behavior touched. |

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: none — GET/PUT `/admin/api/production-achievement/permissions[/{user_identifier}]` and `admin_required` are unchanged. `contract-reviewer` must confirm `contracts/api/api-contract.md` and the sample `tests/contract/samples/get_admin_production_achievement_permissions.json` need NO edit (relocation does not change the endpoint contract).
- CSS/UI: `contracts/css/css-contract.md` — panel CSS re-scoped `.theme-admin-pages` → `.theme-admin-dashboard` (Rule 4.2/4.3 scoping). `contracts/css/css-inventory.md` — update governed-source list if a new authored `.vue`/`.css` under `admin-dashboard/tabs/` is added or an old one removed.
- Env: none
- Data shape: none
- Business logic: none — `can_edit_targets` semantics and table unchanged.
- CI/CD: none (routine `css:check` gate applies but no `ci-gate-contract.md` change).

## Required Tests
- unit: frontend unit test for the new tab component — renders permission list from props, emits `toggle`/`grantNew` correctly (co-locate with `frontend/tests/legacy/admin-dashboard.test.js`).
- contract: confirmation-only — existing permissions endpoint sample remains byte-identical; no new contract sample.
- integration: (none)
- E2E: `frontend/tests/playwright/admin-dashboard.spec.ts` — new tab appears and panel operates; `frontend/tests/playwright/admin-pages.spec.ts` — updated to reflect removal (or retained coexistence) per planner decision.
- visual: new `admin-dashboard` tab under `.theme-admin-dashboard` (scoping bleed check + placement).
- data-boundary: (none)
- resilience: (none)
- fuzz/monkey: (none)
- stress: (none)
- soak: (none)

## Required Agents
- implementation-planner — turns the relocation + remove/keep decision into the execution packet (must run before frontend implementation).
- frontend-engineer — relocate component, wire new tab into `admin-dashboard` tabs array, re-scope CSS.
- contract-reviewer — confirm API contract unchanged; review CSS contract re-scope and css-inventory update.
- ui-ux-reviewer — tab interaction/copy/accessibility (tab label, keyboard nav, panel affordances).
- visual-reviewer — visual evidence bundle for the new tab and scoping correctness.
- test-strategist — populate Acceptance Criteria → Test Mapping and test plan.
- qa-reviewer — release readiness.

## Inferred Acceptance Criteria
- AC-1: A new tab is added to the `admin-dashboard` App `tabs` array (alongside overview/performance/cache/worker/usage/logs), with its Tab component under `frontend/src/admin-dashboard/tabs/`, loaded via the existing `defineAsyncComponent` pattern.
- AC-2: The new tab renders the target-edit permission whitelist (permissions list) fetched via the existing GET `/admin/api/production-achievement/permissions`, unchanged.
- AC-3: Grant and toggle/revoke actions in the tab call PUT `/admin/api/production-achievement/permissions[/{user_identifier}]` and refresh the list, with behavior identical to the current admin-pages panel.
- AC-4: All panel CSS is scoped under `.theme-admin-dashboard` (no unscoped rules); `npm run css:check` passes (css-contract Rule 4.2/4.3/Rule 6).
- AC-5: No backend/API/auth change: `contracts/api/api-contract.md` and the permissions endpoint contract sample are unchanged; endpoints remain `admin_required`.
- AC-6: `/admin/dashboard` and `/admin/pages` route visibility (`admin_only`) and navigation are unchanged; no new route is introduced.
- AC-7: implementation-planner records whether the panel is removed from `/admin/pages` or kept in both; if removed, `admin-pages` no longer shows the "生產達成率 — 目標值編輯權限" panel and its E2E/unit coverage is updated accordingly.

## Tasks Not Applicable
- not-applicable: 1.3 (no architecture review / design.md); all backend/API implementation tasks, data-shape tasks, env-contract tasks, business-rules tasks, and stress/soak/resilience test tasks are not applicable (no backend, data, env, business, or load surface is touched).

## Clarifications or Assumptions
- Assumption: "new tab" is internal to the existing `admin-dashboard` SPA (tabs array), NOT a new portal route — therefore `INPUT_MAP`/`ROUTE_CONTRACTS`/`navigationManifest`/`route_scope_matrix` changes are expected to be unnecessary (per change-request Constraints). Deferred to implementation-planner; gated behind CER-001 in context-manifest.md.
- Assumption: The remove-vs-coexist decision for the old `admin-pages` panel (Open Question) defaults to removal, decided and justified by implementation-planner.
- Assumption: `TargetPermissionsPanel.vue` is reused as-is (or moved) rather than rewritten; its props (`permissions`) / emits (`toggle`, `grantNew`) contract is preserved so the API interaction is byte-identical.

## Context Manifest Draft

### Affected Surfaces
- Admin UI surface — `admin-dashboard` app (target), `admin-pages` app (source), `admin-shared` (shared components/composables)

### Allowed Paths
- specs/changes/move-target-permissions-panel/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/
- contracts/api/

### Required Contracts
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/api/api-contract.md (read-only confirmation of no change)

### Required Tests
- frontend/tests/legacy/admin-dashboard.test.js
- frontend/tests/playwright/admin-dashboard.spec.ts
- frontend/tests/playwright/admin-pages.spec.ts

### Agent Work Packets

#### implementation-planner
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- contracts/css/
- contracts/api/

#### frontend-engineer
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/

#### contract-reviewer
- specs/changes/move-target-permissions-panel/
- contracts/css/
- contracts/api/

#### ui-ux-reviewer
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/

#### visual-reviewer
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/

#### test-strategist
- specs/changes/move-target-permissions-panel/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/
- contracts/api/

#### qa-reviewer
- specs/changes/move-target-permissions-panel/

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - frontend/src/portal-shell/routeContracts.js
    - frontend/src/portal-shell/navigationManifest.js
    - frontend/src/portal-shell/nativeModuleRegistry.js
    - docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
    - docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
  reason: Only needed IF implementation-planner determines the new tab requires route/manifest touchpoints. The change-request states a new tab is NOT a new route and manifest edits should be avoided; request stays pending unless the planner confirms a wiring need.
  status: pending
