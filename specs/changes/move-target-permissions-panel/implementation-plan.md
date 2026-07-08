---
change-id: move-target-permissions-panel
schema-version: 0.1.0
last-changed: 2026-07-08
---

# Implementation Plan: move-target-permissions-panel

## Objective
Relocate the "生產達成率 — 目標值編輯權限" whitelist UI (`TargetPermissionsPanel.vue`) out of the `admin-pages` app and into a NEW tab of the `admin-dashboard` app (existing `tabs` array + `defineAsyncComponent` pattern), re-scoped under `.theme-admin-dashboard`, with the old panel fully removed from `/admin/pages`. Backend/API/auth unchanged (props `permissions`, emits `toggle`/`grantNew`, and the GET/PUT permission endpoints stay byte-identical).

## Key Decisions (planner-owned)

- **DECISION-1 — Remove from `/admin/pages` (not coexist).** Resolves the change-request Open Question: fully remove the panel from `admin-pages/App.vue`. Rationale: both routes are `admin_only`, there is no external consumer or compatibility window (monorepo), and the change exists precisely because the panel was mis-placed — keeping both would perpetuate the "user can't find it / duplicate maintenance" problem the change fixes. Drives the AC-7 removal path in test-plan.md.
- **DECISION-2 — New tab key `permissions`, label `目標值權限`.** Fits the compact existing labels (總覽/效能/快取/Worker/用戶/日誌); appended after `logs`. (ui-ux-reviewer may refine the label copy; key stays `permissions`.)
- **DECISION-3 — Rename the panel's generic classes to panel-exclusive `.pa-perm-*` names; DO NOT copy the bare `table`/`th`/`td`/`.status-badge` rules into `.theme-admin-dashboard`.** Rationale (collision found during scoping): `.theme-admin-dashboard .status-badge` already exists (`admin-dashboard/style.css:595`) with a DIFFERENT definition and is actively consumed by `RecentSessionsTable.vue` (usage tab), which also renders a bare `<table>`. Copying admin-pages' bare-`table`/`th`/`td`/`.status-badge`/`.status-released`/`.status-dev` rules would silently regress the usage tab. Panel-exclusive `.pa-perm-*` classes are collision-safe and css-contract-compliant (Rule 4.2/4.3/6). Props/emits/API untouched, so this stays a relocation, not a rewrite. **This changes the concrete class list the AC-4 data-boundary test must assert — see Test Execution Plan and Known Risks.**
- **DECISION-4 — No route/manifest touchpoints (CER-001 stays not-needed).** A new tab inside an existing SPA is not a new route; `routeContracts.js`/`navigationManifest.js`/`nativeModuleRegistry.js`/`route_scope_matrix.json`/`asset_readiness_manifest.json`/`vite.config.ts INPUT_MAP` are NOT edited. Do not action CER-001.

## Execution Scope

### In Scope
- Move `TargetPermissionsPanel.vue` into `admin-dashboard/`, renaming rendered classes to `.pa-perm-*`.
- New tab wrapper under `admin-dashboard/tabs/` holding fetch/PUT state (ported from `admin-pages/App.vue`).
- Register the new tab in the `admin-dashboard/App.vue` `tabs` array.
- Add `.theme-admin-dashboard`-scoped `.pa-perm-*` rules to `admin-dashboard/style.css`.
- Remove the panel block + its state/functions/import from `admin-pages/App.vue`; remove the two dead `.pa-perm-*` rules from `admin-pages/style.css`.
- Move/extend the co-located component test; update `admin-dashboard.test.js` tab fixture; add tab-wrapper + css-scope tests; update `admin-pages.spec.ts` (absence) and `admin-dashboard.spec.ts` (new tab).

### Out of Scope
- Any backend/route/service/auth change; `can_edit_targets` semantics; the permission endpoints or their contract sample.
- Refactoring `PagesManagementPanel` or the shared `.theme-admin-pages` table/badge rules it still uses (must stay).
- New portal route / navigation / manifest / vite entry changes (DECISION-4).
- Extracting shared `putJson`/`getCsrfToken` helpers — port them into the new tab wrapper (admin-pages keeps its copy for `handleUpdatePage`).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | admin-dashboard component | Move `admin-pages/components/TargetPermissionsPanel.vue` → `admin-dashboard/components/TargetPermissionsPanel.vue`; rename rendered classes to `.pa-perm-*` (File-Level Plan); update docstring to say `.theme-admin-dashboard`; keep props/emits/`.ui-btn*`/`data-testid`s | frontend-engineer |
| IP-2 | admin-dashboard tab wrapper | Create `admin-dashboard/tabs/PermissionsTab.vue` holding permissions state + fetch/PUT (ported from `admin-pages/App.vue:43-141`), rendering `TargetPermissionsPanel`, exposing `refresh()` via `defineExpose` (tab convention, `CacheTab.vue:86`) | frontend-engineer |
| IP-3 | admin-dashboard App | Add `{ key: 'permissions', label: '目標值權限', component: defineAsyncComponent(() => import('./tabs/PermissionsTab.vue')) }` to the `tabs` array (`App.vue:15-46`), appended after `logs` | frontend-engineer |
| IP-4 | admin-dashboard CSS | Append `.theme-admin-dashboard .pa-perm-*` rules to `admin-dashboard/style.css` (Contract Updates → CSS) | frontend-engineer |
| IP-5 | admin-pages App removal | Remove `TargetPermissionsPanel` import (line 15), `ProductionAchievementPermissionRow` interface (30-35), `permissions`/`permissionsError` refs (43-44), `loadPermissions`/`refreshPermissions`/`handleTogglePermission`/`handleGrantNewPermission` (112-141), the `await refreshPermissions()` call (149), and the second `<div class="panel">` block (183-200). Keep `putJson`/`getCsrfToken` (used by `handleUpdatePage`) | frontend-engineer |
| IP-6 | admin-pages CSS cleanup | Remove the dead `.pa-perm-add-row`/`.pa-perm-add-input` rules + comment header (`admin-pages/style.css:205-222`). KEEP all shared rules (lines 128-203) — still used by `PagesManagementPanel` | frontend-engineer |
| IP-7 | tests | Move + extend component test; update tab fixture; add tab-wrapper + css-scope tests; update both specs (Test Execution Plan) | frontend-engineer |
| IP-8 | contracts (prose) | Apply CSS/inventory + api-contract consumer-note edits per Contract Updates (main Claude applies) | contract-reviewer / main |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC→Test Mapping table; Test Update Contract | which test files to add/move/update |
| test-plan.md | Test Execution Ladder | required phases (collect/targeted/changed-area floor) |
| ci-gates.md | Required Gates table | verification commands (type-check/css:check/unit/build/e2e) |
| ci-gates.md | Required Check Policy | merge eligibility |
| agent-log/contract-reviewer.yml | api 1.38.x / css-contract 1.13.0 / css-inventory 1.2.10 | pending prose version bumps |
| change-request.md | Open Questions | remove-vs-coexist (resolved: DECISION-1) |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| frontend/src/admin-dashboard/components/TargetPermissionsPanel.vue | create (move) | class renames: `.table-container`→`.pa-perm-table-container`; `<table>`→`<table class="pa-perm-table">`; `.route-cell`→`.pa-perm-user-cell`; `.status-badge`→`.pa-perm-badge`; `.status-released`→`.pa-perm-badge--granted`; `.status-dev`→`.pa-perm-badge--revoked`; `.empty-state`→`.pa-perm-empty`; keep `.pa-perm-add-row`/`.pa-perm-add-input`/`.ui-btn*`/`data-testid`s |
| frontend/src/admin-pages/components/TargetPermissionsPanel.vue | delete | superseded by moved file (delete after new test green) |
| frontend/src/admin-dashboard/tabs/PermissionsTab.vue | create | ports `putJson`+`getCsrfToken`+`loadPermissions`+`refreshPermissions`+`handleTogglePermission`+`handleGrantNewPermission`; local `permissions`/`permissionsError` state; `apiGet` from `../../core/api`; renders panel; `defineExpose({ refresh })` (=`refreshPermissions`); own `onMounted` initial load |
| frontend/src/admin-dashboard/App.vue | edit | add `permissions` tab entry (IP-3) |
| frontend/src/admin-dashboard/style.css | edit | append `.theme-admin-dashboard .pa-perm-*` rules (Contract Updates → CSS) |
| frontend/src/admin-pages/App.vue | edit | removals per IP-5 |
| frontend/src/admin-pages/style.css | edit | remove lines 205-222 only (IP-6) |

## Contract Updates

- **API:** `contracts/api/api-contract.md` — rows 260-261 UNCHANGED (endpoints/auth identical). Only the consumer note at line 483 updates: `frontend/src/admin-pages/` (permission block) → `frontend/src/admin-dashboard/` (permissions tab). Version bump 1.38.0→1.38.x, CHANGELOG note "permission whitelist UI relocated admin-pages→admin-dashboard; endpoints unchanged". No sample edit — `tests/contract/samples/get_admin_production_achievement_permissions.json` stays byte-identical (AC-5).
- **CSS/UI:** `contracts/css/css-contract.md` — add re-scope note (panel classes moved `.theme-admin-pages`→panel-exclusive `.pa-perm-*` under `.theme-admin-dashboard`; new class names introduced to avoid the existing `.theme-admin-dashboard .status-badge` collision, Rule 4.2/4.3/6). Version 1.12.0→1.13.0. `contracts/css/css-inventory.md` — both `admin-dashboard/style.css` and `admin-pages/style.css` rows already registered (no new file); update notes to record the `.pa-perm-*` addition (admin-dashboard) and removal (admin-pages). Version 1.2.9→1.2.10.
- **Env:** none.
- **Data shape:** none.
- **Business logic:** none.
- **CI/CD:** none (routine `css:check`/Tier-1 gates apply; `admin-dashboard.spec.ts`/`admin-pages.spec.ts` are pre-named targets — ci-gates.md).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | frontend/tests/legacy/admin-dashboard.test.js | `ADMIN_DASHBOARD_TABS` extended to 7 tabs incl. `{permissions,'目標值權限'}`; count/uniqueness/label tests pass |
| AC-1/2/3 | frontend/src/admin-dashboard/tabs/__tests__/PermissionsTab.test.ts | mounts, renders props, toggle/grantNew → PUT + refetch |
| AC-4 | frontend/tests/legacy/admin-dashboard-permissions-css-scope.test.js | asserts `admin-dashboard/style.css` has `.theme-admin-dashboard`-scoped rules for RENAMED classes: `.pa-perm-table-container`, `.pa-perm-table`, `.pa-perm-user-cell`, `.pa-perm-badge`, `.pa-perm-badge--granted`, `.pa-perm-badge--revoked`, `.pa-perm-empty`, `.pa-perm-add-row`, `.pa-perm-add-input` |
| AC-7 | frontend/src/admin-dashboard/components/__tests__/TargetPermissionsPanel.test.ts | moved from admin-pages; extend 5 existing cases in place; update class-selectors to `.pa-perm-*` |
| AC-1/2/3/4 | frontend/tests/playwright/admin-dashboard.spec.ts | tab appears + switch, data loads, toggle round-trip, computed-style on `.pa-perm-badge`/`.pa-perm-table-container` |
| AC-7 | frontend/tests/playwright/admin-pages.spec.ts | "生產達成率 — 目標值編輯權限" panel absent |
| AC-5 | cdd-kit validate --contracts | sample + api rows 260-261 byte-identical |
| AC-6 | frontend/tests/legacy/portal-shell-wave-a-smoke.test.js | unchanged, still green |
| gates | see ci-gates.md Required Gates table | type-check / css:check / unit / build / Tier-1 all green |

Required phase floor: `collect`, `targeted`, `changed-area` (+ `contract` since the API sample is asserted). Generate evidence via `cdd-kit test run`; do not restate the ladder — see test-plan.md "Test Execution Ladder".

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- Do NOT copy bare `table`/`th`/`td`/`.status-badge`/`.status-released`/`.status-dev` rules into `.theme-admin-dashboard` — use the `.pa-perm-*` names only (DECISION-3); a bare copy regresses the usage tab.
- Delete the old-path `admin-pages/components/__tests__/TargetPermissionsPanel.test.ts` only after the moved+extended test at the new path is green (test-plan Test Update Contract).
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- **Class-name collision (primary):** `.theme-admin-dashboard .status-badge` (style.css:595) and the bare `<table>` in `RecentSessionsTable.vue` are live in the target theme. DECISION-3's `.pa-perm-*` rename is the mitigation; a naive copy-paste is the failure mode. The AC-4 static css-scope test must assert the `.pa-perm-*` names, NOT the original class list in test-plan.md line 38 — flag to test-strategist to update that literal list (intent unchanged: "every class the relocated panel renders").
- **`.ui-btn*` availability:** panel keeps `.ui-btn ui-btn--primary ui-btn--sm` (global `@layer components`, app-agnostic) — confirm they resolve in the admin-dashboard build during type-check/build; no re-scope needed.
- **Duplicated `putJson`/`getCsrfToken`:** intentionally duplicated into the tab wrapper (admin-pages retains its copy). Accepted to keep the diff minimal and avoid an admin-shared refactor.
- **Code map:** `.cdd/code-map.yml` not consulted — the admin surface is fully covered by direct reads of the four allowed frontend dirs; no staleness impact on this plan.
