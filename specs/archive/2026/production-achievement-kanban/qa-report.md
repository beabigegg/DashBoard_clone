# QA Report — production-achievement-kanban

## Decision
**PASS**

## Gate Results
- `test-evidence.yml`: all 4 required phases (collect, targeted, changed-area, contract) `passed`; `final-status: passed`; no waivers.
- `cdd-kit validate --contracts`: passed (193 endpoints; response-shape, API semantic, API conformance, env semantic all pass).
- `cdd-kit validate --versions`: passed.
- `frontend` vitest `src/portal-shell`: 10/10 pass (regression check for the shared `App.vue` fix).
- `frontend` vitest `src/production-achievement` + `src/admin-pages`: 30+8/38 pass.
- `npm run css:check`: 0 errors, 307 pre-existing warnings unrelated to this change.
- `npm run type-check`: 0 errors.
- Playwright: `production-achievement.spec.js`, `resilience/production-achievement-resilience.spec.js`, `data-boundary/production-achievement-data-boundary.spec.js` — 10/10 pass live against a real gunicorn+dist build (e2e-resilience-engineer).

## Evidence Verified Directly (not taken on trust from prior agent-logs)
- **PA-05 predicate** preserved verbatim in `src/mes_dashboard/sql/production_achievement.sql` (every SPECNAME/processtypename/WORKFLOWNAME branch present, not simplified).
- **PA-03 cross-midnight rule**: confirmed a 4/27 07:29 trackout (`< 07:30:00`) correctly yields `output_date = 4/26` in both the SQL CASE and the Python mirror.
- **Permission fail-closed**: `can_edit_targets`/whitelist lookup denies on no whitelist row, `MYSQL_OPS_ENABLED=false`, and any MySQL exception — all three failure modes verified in source.
- **Write-path 503s**: `PUT /api/production-achievement/targets` and `PUT /admin/api/production-achievement/permissions/{user_identifier}` both map MySQL-unavailable to 503, not 500 or a silent allow.
- **Shared-file regression** (`frontend/src/portal-shell/App.vue`'s `await router.isReady()` fix): present, and the existing `src/portal-shell` unit suite still passes.

## Minor Observations (non-blocking)
- `api_put_targets` uses `@login_required` + an inline `can_edit_targets()` check rather than the `targets_edit_required` decorator directly — functionally equivalent and correctly ordered (permission check before the OPS-disabled check); cosmetic only.
- No dedicated unit/component test pins the `App.vue` `router.isReady()` race fix directly; it is covered at the integration level by the live Playwright resilience spec run. Acceptable given the fix is a one-line, idiomatic Vue Router guard.

## Accepted Risks (explicitly not blocking)
- `MYSQL_OPS_ENABLED` defaults to `false` — the feature ships inert on the target/permission-write dimension until an operator applies `scripts/sql/production_achievement_tables.sql` and flips the flag in production. Documented deploy precondition (design.md, ci-gates.md), not gate-enforced by design (no automated check can verify a human ran a DDL script or set a prod env var).
- PA-04 (three-shift historical regime output_date cross-day rule) is an explicitly unverified assumption, logged as such, out of this change's acceptance scope.
- UI/UX polish items from ui-ux-reviewer (no confirmation before revoking `can_edit_targets`, `window.alert()` used for admin action feedback instead of the in-app error-banner idiom, no focus-transfer into the target-edit input on open) — verified NOT to be stated requirements in change-request.md; tracked as follow-up polish, not blocking.

## Fixes Applied During Review (before this QA pass)
- visual-reviewer found a dead `.dashboard` CSS class (copied from `production-history` without importing `resource-shared/styles.css`) that silently dropped the page-width cap present on every sibling report page. Fixed by main Claude: removed the dead class, added a self-contained `max-width` rule in the page's own scoped CSS (following the `db-scheduling` precedent of not importing `resource-shared/styles.css`), and narrowed an overly-broad `.ui-card { overflow: visible }` rule to a specific `.pa-filter-card` modifier class per css-contract.md's documented pattern.
- e2e-resilience-engineer found and fixed a real race condition in the shared `frontend/src/portal-shell/App.vue`: on a direct/hard navigation to a dynamically-registered native route, `loadNavigation()` could read `route` before the router's own initial-navigation guard resolved, silently preventing the `shell-fallback` self-heal redirect. Fixed with `await router.isReady()`. Confirmed deterministic across repeated runs; existing `src/portal-shell` unit tests unaffected.

## Release Readiness
Approved. All required Tier-1 gates pass, contracts conform to the implemented routes, business rules PA-01/02/03/05/06/07 verified directly in source, the new permission gate fails closed under all three failure modes, and the one shared-file change (portal-shell `App.vue`) was regression-checked with no impact to existing behavior.
