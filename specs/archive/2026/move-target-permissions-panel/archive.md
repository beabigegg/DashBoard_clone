# Archive: move-target-permissions-panel

## Change Summary

The "生產達成率" (production-achievement) target-value-edit permission
whitelist admin UI (`can_edit_targets` grant/revoke) was originally built
into the `admin-pages` app (`/admin/pages`, "頁面管理") during the
`production-achievement-kanban` change, even though the user's original
request was to add it under `/admin/dashboard` ("管理儀表板"). This left
the feature effectively undiscoverable at the location the user expected.
This change relocates the panel into a new tab of the existing
`admin-dashboard` app, matching the original intent, with no backend/API/
auth surface touched.

## Final Behavior

- A new tab `permissions` (label `目標值權限`) exists in `/admin/dashboard`
  alongside 總覽/效能/快取/Worker/用戶/日誌, backed by
  `frontend/src/admin-dashboard/tabs/PermissionsTab.vue` and
  `frontend/src/admin-dashboard/components/TargetPermissionsPanel.vue`.
- `/admin/pages` ("頁面管理") no longer shows the permission-whitelist
  panel — only the "所有頁面" page-management panel remains there.
- `GET`/`PUT /admin/api/production-achievement/permissions[/{user_identifier}]`
  are byte-identical to before (same auth, request/response shape); only
  their frontend consumer moved.
- The panel's CSS was re-scoped `.theme-admin-pages` → `.theme-admin-dashboard`
  and its rendered classes renamed to panel-exclusive `.pa-perm-*` names
  (not a straight copy of the generic `.table-container`/`.status-badge`
  names), because `.theme-admin-dashboard` already had a differently-defined
  `.status-badge`/bare-`table` pair in active use by `RecentSessionsTable.vue`
  (usage tab) — a same-name copy would have silently regressed that tab.
- `PermissionsTab.vue` shows a proper loading indicator (`BlockLoadingState`)
  during the initial fetch instead of misleadingly showing "尚無授權名單"
  (no permissions granted) before data has arrived.

## Final Contracts Updated

- `contracts/api/api-contract.md` 1.38.0 → 1.38.1 — prose-only consumer-note
  update (Compatibility Notes + CHANGELOG); no endpoint/schema/auth change.
- `contracts/css/css-contract.md` 1.12.0 → 1.13.0 — documents the
  `.theme-admin-pages` → `.theme-admin-dashboard` re-scope and the
  `.pa-perm-*` collision-avoidance rename.
- `contracts/css/css-inventory.md` 1.2.9 → 1.2.10 — Route-Local Feature
  Layers notes updated for both `admin-dashboard/style.css` (gained
  `.pa-perm-*`) and `admin-pages/style.css` (lost the two panel-exclusive
  rules; shared rules kept for `PagesManagementPanel`).
- `contracts/openapi.json` + `contracts/api/openapi.json` regenerated to
  match the 1.38.1 bump (see Production Reality Findings — this was missed
  in the first push and caught by CI).
- `contracts/CHANGELOG.md` — mirrored entries for all three bumps above.

## Final Tests Added / Updated

- `frontend/src/admin-dashboard/components/__tests__/TargetPermissionsPanel.test.ts`
  (moved + extended from `admin-pages`, 6 cases).
- `frontend/src/admin-dashboard/tabs/__tests__/PermissionsTab.test.ts` (new,
  10 cases: fetch/render, toggle/grantNew → PUT + refetch, error banner,
  `refresh()` expose, loading-state gate).
- `frontend/tests/legacy/admin-dashboard-permissions-css-scope.test.js` (new,
  10 static assertions guarding every `.pa-perm-*` class has a matching
  `.theme-admin-dashboard` rule and no `.status-badge` duplication).
- `frontend/tests/legacy/admin-dashboard.test.js` — updated 7-tab fixture.
- `frontend/tests/playwright/admin-dashboard.spec.ts` — new tab
  appears/switches, data loads, toggle round-trip, computed-style assertions
  on `.pa-perm-badge`/`.pa-perm-table-container` (not just DOM presence).
- `frontend/tests/playwright/admin-pages.spec.ts` — asserts the old panel
  is now absent.
- `frontend/src/admin-pages/components/__tests__/TargetPermissionsPanel.test.ts`
  deleted (superseded by the relocated test).

## Final CI/CD Gates

Per `ci-gates.md`: `type-check`, `css-governance`, `unit`, `build`,
`contract` (confirmation-only), and the Tier-1 Playwright job
(`admin-dashboard.spec.ts` + `admin-pages.spec.ts`). No new gate/workflow
file was introduced — both apps already had build/gate wiring. All gates
confirmed green in CI on `main` (see Production Reality Findings).

## Production Reality Findings

- **implementation-planner caught a live collision the classifier/contract-reviewer
  missed**: `.theme-admin-dashboard .status-badge` and a bare `<table>`
  already existed for `RecentSessionsTable.vue` with a different definition.
  A naive copy-paste of the admin-pages panel's generic class names would
  have silently regressed the usage tab. Resolved via the `.pa-perm-*`
  rename (DECISION-3). This is the kind of cross-component CSS collision
  that `npm run css:check` cannot catch (it only flags *unscoped* rules,
  not *colliding* ones) — worth remembering for any future cross-app UI
  relocation into a theme that already has its own component library.
- **ui-ux-reviewer caught a loading/empty-state conflation** in the new
  `PermissionsTab.vue` (no `loading` ref, so the empty-state message showed
  falsely during the initial fetch). Fixed as a same-cycle fast-follow by
  `frontend-engineer`, re-verified green.
- **openapi-sync-gate failed on the first CI push**: bumping
  `api-contract.md`'s `schema-version` for a prose-only consumer-note
  change did not automatically regenerate `contracts/openapi.json` /
  `contracts/api/openapi.json`. `cdd-kit openapi export --check` in CI
  caught the drift; fixed in a follow-up commit (`11df6bc4`) by running
  `cdd-kit openapi export` for both output paths. No functional impact —
  the OpenAPI export is derived/generated, not hand-edited — but any
  `schema-version` bump to `api-contract.md`, even a prose-only one, must
  be followed by re-running the export before pushing.
- Tier-1 Playwright specs could not execute locally (sandbox environment
  had no installable browser); this was accepted as a documented residual
  risk (`qa-report.md`, "approved-with-risk") gated on CI, and CI's
  `frontend-tests` run passed cleanly on the first attempt — no
  relocation-specific E2E regressions.

## Lessons Promoted to Standards

Both candidates reviewed and approved by `contract-reviewer` (`/cdd-close` Step 3):

1. **openapi-sync-gate on prose-only api-contract.md bumps** (promote-to-guidance):
   - `CLAUDE.md` (CDD Kit operations, one line) + `docs/cdd-kit-patterns.md` §"openapi-sync Gate Fires on Any api-contract.md schema-version Bump" (new section).
   - Evidence: CI run 28982636955 failure; fix commit `11df6bc4`.
2. **Cross-app CSS class-name collision on UI relocation** (promote-to-contract):
   - `contracts/css/css-contract.md` §Known Global Rule Interactions + §Forbidden Practices (new bullets each), schema-version 1.13.0 → 1.14.0; `contracts/CHANGELOG.md` entry; `CLAUDE.md` (CSS architecture, one line pointer).
   - Evidence: `agent-log/implementation-planner.yml` DECISION-3 (`.theme-admin-dashboard .status-badge`/bare `table` collision with `RecentSessionsTable.vue`).

`cdd-kit validate --contracts` / `--versions` and `cdd-kit context-scan` re-run clean after both promotions.

## Follow-up Work

None outstanding. The one non-blocking UI/UX finding (loading state) was
fixed within this same change rather than deferred.

## Cold Data Warning

This archive is historical evidence. Current requirements live in
`contracts/` and active project guidance (`CLAUDE.md`/`CODEX.md`).
