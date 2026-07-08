# Visual Review Report — move-target-permissions-panel

## Scope

Relocation of the target-value-edit permission whitelist admin UI from
`admin-pages` (`.theme-admin-pages`) into a new tab of `admin-dashboard`
(`.theme-admin-dashboard`), with rendered classes renamed to panel-exclusive
`.pa-perm-*` names to avoid colliding with the pre-existing `.status-badge`/
bare-`table` selectors used by `RecentSessionsTable.vue` (usage tab).

## Environment Limitation

No browser is available in this environment (`npx playwright install`
fails — unsupported Ubuntu version in the sandbox). A live-rendered
screenshot bundle could not be produced. This report documents the
compensating **static CSS/template audit** performed instead by
`visual-reviewer`, and defers the browser-rendered confirmation to the
CI Tier-1 Playwright job (`admin-dashboard.spec.ts`, `admin-pages.spec.ts`)
per `ci-gates.md`.

## Findings (static audit)

1. **Class-definition completeness.** Every `.pa-perm-*` class rendered by
   `TargetPermissionsPanel.vue` (`pa-perm-table-container`, `pa-perm-table`,
   `pa-perm-user-cell`, `pa-perm-badge`, `pa-perm-badge--granted`,
   `pa-perm-badge--revoked`, `pa-perm-empty`, `pa-perm-add-row`,
   `pa-perm-add-input`) has a matching `.theme-admin-dashboard .pa-perm-*`
   rule in `frontend/src/admin-dashboard/style.css:650-735`. Confirmed by
   the repo's own static guard test,
   `frontend/tests/legacy/admin-dashboard-permissions-css-scope.test.js`
   (10/10 assertions pass).
2. **Collision check.** `RecentSessionsTable.vue` uses `.mini-table` and
   `.status-badge`/`.status-active`/`.status-ended` — zero string overlap
   with the new `.pa-perm-*` names. No bare `table`/`th`/`td` selector
   exists anywhere in `admin-dashboard/style.css`; every table rule is
   class-scoped. No bleed in either direction.
3. **Unscoped-rule check (css-contract Rule 4.2/4.3/6).** Every rule in
   `admin-dashboard/style.css` is prefixed `.theme-admin-dashboard` (the
   sole exception, `@keyframes ad-spin`, is not a selector and is exempt).
   `npm run css:check`: 0 errors, 0 unscoped feature-CSS rules.
4. **Visual consistency.** `.pa-perm-*` declarations diffed against
   `git show HEAD~:frontend/src/admin-pages/style.css:128-222` (the
   pre-relocation rules) are value-for-value identical — this is a
   rename-only relocation, not a redesign. All values use registered
   Tailwind tokens (no ad-hoc magic values).
5. **Cleanup verification.** `admin-pages/App.vue` and
   `admin-pages/style.css` have zero remaining `pa-perm`/
   `TargetPermissionsPanel` references; shared classes
   (`.table-container`/`.status-badge`/etc.) remain intact for
   `PagesManagementPanel`, which still depends on them.

## Outstanding Before Merge

Browser-rendered confirmation (actual pixel layout, computed-style
assertions on `.pa-perm-badge`/`.pa-perm-table-container`, tab
switch/interaction) is deferred to the CI Tier-1 Playwright job. This is
a scheduled required gate per `ci-gates.md`, not a skipped one — see
`qa-report.md` for the release-readiness decision this drives.

## Verdict

approved (static audit) — no blocking findings; browser-rendered
confirmation deferred to CI per the environment limitation above.
