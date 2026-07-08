# QA Report — move-target-permissions-panel

## Decision

**approved-with-risk** (single reviewer, `qa-reviewer` — tier 3, medium
risk, no high/critical trigger requiring a second sign-off).

## Gate Results

| gate | status | evidence |
|---|---|---|
| type-check | pass | `vue-tsc --noEmit` 0 errors |
| css-governance | pass | `npm run css:check`: 0 errors, 0 unscoped feature-CSS rules |
| unit / changed-area | pass | vitest `src/admin-dashboard` 46/46; legacy node 25/25 |
| build | pass | both `admin-dashboard`/`admin-pages` Vite entries built |
| contract (confirmation-only) | pass | `cdd-kit validate --contracts`/`--versions` green; API sample byte-identical |
| data-boundary (css-scope static) | pass | `admin-dashboard-permissions-css-scope.test.js` 10/10 |
| e2e-critical (Tier-1 Playwright) | **scheduled in CI, not run locally** | no browser available in this sandbox (`npx playwright install` unsupported OS) |
| `cdd-kit gate` | pass | tier-floor-override recorded and justified (keyword-scan false positive) |

## Residual Risk

- **Risk:** Browser-rendered confirmation of the relocated tab (actual
  layout, computed-style, tab-switch interaction) has not executed — only
  a static CSS/template audit (see `visual-review-report.md`). Bounded low:
  the CSS diff is rename-only and value-for-value identical to the prior
  admin-pages rules (visual-reviewer finding), and the collision this
  relocation was specifically designed to avoid (`.status-badge`/bare
  `table` vs. `RecentSessionsTable.vue`) was confirmed absent by both the
  static guard test and manual selector grep.
- **Owner:** CI/CD gatekeeper (Tier-1 Playwright gate) + whoever cuts the PR.
- **Follow-up:** `admin-dashboard.spec.ts` + `admin-pages.spec.ts` (Tier-1,
  required per `ci-gates.md`) MUST run and pass in CI on the PR head commit
  before merge. If that job fails, this decision flips to **blocked** —
  it is a release condition, not a waived gate.

## Non-blocking Process Notes

- CER-001 (route/manifest context-expansion request) is confirmed
  **not-needed** — implementation-planner's DECISION-4 established no new
  route/manifest wiring is required (new tab inside an existing SPA, not a
  new route); closed accordingly in `context-manifest.md`.
- `tasks.yml` items 6.2/6.3 (PR-required / informational gates) remain
  `pending` until the CI Tier-1 Playwright run above actually goes green —
  intentionally not marked `done` on local evidence alone, per this
  change's own release condition.

## Fixback Applied During This Cycle

- `ui-ux-reviewer` flagged a loading/empty-state conflation in
  `PermissionsTab.vue` (non-blocking) — fixed as a fast-follow in the same
  change by `frontend-engineer`, re-verified green (see
  `agent-log/frontend-engineer.yml`).
