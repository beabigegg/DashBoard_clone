---
change-id: move-target-permissions-panel
schema-version: 0.1.0
last-changed: 2026-07-08
risk: medium
tier: 3
---

# Test Plan: move-target-permissions-panel

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit (tab-config contract) | frontend/tests/legacy/admin-dashboard.test.js | 0 |
| AC-1 | unit (tab component mount) | frontend/src/admin-dashboard/tabs/__tests__/PermissionsTab.test.ts | 0 |
| AC-1 | e2e (tab appears + switch) | frontend/tests/playwright/admin-dashboard.spec.ts::test_tab_switch_permissions | 1 |
| AC-2 | unit (fetch + render props) | frontend/src/admin-dashboard/tabs/__tests__/PermissionsTab.test.ts | 0 |
| AC-2 | e2e (data loads from mocked GET) | frontend/tests/playwright/admin-dashboard.spec.ts::test_permissions_data_loads | 1 |
| AC-3 | unit (toggle/grantNew → PUT + refetch) | frontend/src/admin-dashboard/tabs/__tests__/PermissionsTab.test.ts | 0 |
| AC-3 | e2e (round-trip toggle) | frontend/tests/playwright/admin-dashboard.spec.ts::test_permissions_toggle_round_trip | 1 |
| AC-4 | data-boundary (static css-scope presence) | frontend/tests/legacy/admin-dashboard-permissions-css-scope.test.js | 0 |
| AC-4 | e2e (computed-style, not just DOM presence) | frontend/tests/playwright/admin-dashboard.spec.ts::test_permissions_tab_styled | 1 |
| AC-5 | contract (confirmation-only, byte-identical) | tests/contract/samples/get_admin_production_achievement_permissions.json | 0 |
| AC-6 | unit (existing manifest-consistency gate) | frontend/tests/legacy/portal-shell-wave-a-smoke.test.js | 0 |
| AC-7 | unit (relocated presentational component) | frontend/src/admin-dashboard/components/__tests__/TargetPermissionsPanel.test.ts | 0 |
| AC-7 | e2e (old panel absent from admin-pages) | frontend/tests/playwright/admin-pages.spec.ts::test_target_permissions_panel_absent | 1 |

## Test Families Required

Mark all that apply: unit / contract / integration / e2e / data-boundary / resilience / monkey / stress / soak

| family | tier | notes |
|---|---|---|
| unit | 0 | New tab wrapper (props/emit/fetch), tab-array contract extension, relocated `TargetPermissionsPanel` component tests (extend existing 5 cases, don't duplicate) |
| contract | 0 | Confirmation-only — assert `tests/contract/samples/get_admin_production_achievement_permissions.json` and `api-contract.md` rows 260-261 are unchanged (no new sample) |
| e2e | 1 | `admin-dashboard.spec.ts` new-tab lifecycle + data + round-trip; `admin-pages.spec.ts` updated for removal (or parity check if coexistence chosen) |
| data-boundary | 0 | Static text assertion that `admin-dashboard/style.css` contains `.theme-admin-dashboard`-scoped rules for every class the relocated panel renders (`.pa-perm-table-container`, `.pa-perm-table`, `.pa-perm-user-cell`, `.pa-perm-badge`, `.pa-perm-badge--granted`, `.pa-perm-badge--revoked`, `.pa-perm-empty`, `.pa-perm-add-row`, `.pa-perm-add-input`) — the deterministic guard against a missed class copy |
| visual | 1 | Playwright `getComputedStyle` assertions (e.g. `.pa-perm-badge` border-radius/background, `.pa-perm-table-container` overflow) on the new tab — proves rendered layout, not just element existence; complements (does not replace) the visual-reviewer screenshot bundle |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| frontend/tests/legacy/admin-dashboard.test.js | update | new tab key/label added to `ADMIN_DASHBOARD_TABS` contract fixture (AC-1) |
| frontend/src/admin-pages/components/__tests__/TargetPermissionsPanel.test.ts | delete | component relocates to `admin-dashboard/components/`; superseded by the co-located test at the new path (AC-7, removal path) |
| frontend/tests/playwright/admin-pages.spec.ts | update | add absence assertion for the "生產達成率 — 目標值編輯權限" panel (AC-7, removal path); no prior E2E case exists to delete since this panel was never asserted there before |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Backend route/service/auth changes — `admin_required` and endpoint behavior are unchanged (contract-reviewer confirms, no test needed here).
- `can_edit_targets` business-rule semantics — unchanged, no business-rules test.
- New route/navigation-manifest tests — no new route introduced; existing manifest-consistency tests (AC-6) must keep passing unmodified as the negative-change signal.
- Load/soak/resilience/monkey — no new interaction complexity, no load surface touched.

## Notes

- `PermissionsTab.vue` / its test filename is illustrative (per `UsageTab.vue`/`CacheTab.vue` naming convention); actual name is frontend-engineer's call, but it must live under `admin-dashboard/tabs/` with a co-located `__tests__` file.
- AC-4's static css-scope test is the primary defense against the "DOM present but visually unstyled" silent failure the contract-reviewer flagged; a plain `toBeVisible()` E2E check does not catch it.
- If implementation-planner chooses coexistence over removal, the AC-7 `admin-pages.spec.ts` row becomes a presence-parity check instead of an absence assertion — do not hard-assert absence in that case.
- Extend `TargetPermissionsPanel.test.ts` in place at its new location rather than duplicating its 5 existing cases in a second file.
