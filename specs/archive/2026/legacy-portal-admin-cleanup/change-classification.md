# Change Classification

## Change Types
- primary: `feature-reduction` (deprecate/remove the legacy non-SPA `portal.html` render path — behavior change for the non-default `PORTAL_SPA_ENABLED=false` state)
- secondary: `ui-only-change` (admin-pages a11y), `refactor` (dead-CSS removal), `test-change` (delete non-SPA render tests)

## Lane
- feature
<!-- deliberate cleanup/deprecation of nav-config-to-code follow-ups; not symptom-driven -->

## Risk Level
- low

## Impact Radius
- module-level (portal entry route + templates/tests; admin-pages frontend). Default (SPA) behavior unchanged; only the already-broken non-default `PORTAL_SPA_ENABLED=false` legacy render is removed. No API/data/env/CI contract change.

## Tier
- 3

Rationale: low risk × module-level → Tier 3–4; classified up to **Tier 3** because Item 1 is a behavior change for an existing (flag-off) state + a deprecate-vs-keep design decision + a template removal touching multiple test files. Items 2/3 alone would be Tier 4.

## Architecture Review Required
- yes
- reason: Item 1 is a deprecate-vs-keep decision on the legacy non-SPA portal render path with a behavior change for the `PORTAL_SPA_ENABLED=false` state and a hard constraint that the backend MUST NOT re-introduce a navigation-structure source (moved to `navigationManifest.js`). `spec-architect` writes a short `design.md` (deprecate-vs-keep; flag disposition = keep; route-name + flag-consumer preservation) referencing ADR 0012, before `implementation-planner`.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Captured in change-request + archived nav-config-to-code/regression-report.md |
| design.md | yes | Architecture Review = yes (deprecate-vs-keep + flag disposition) |
| qa-report.md | no | Routine → agent-log/qa-reviewer.yml |
| regression-report.md | no | Small scope; provable by existing suite (AC-1) → agent-log pointers |
| visual-review-report.md | no | a11y is non-visual DOM semantics; no pixel change |
| (others) | no | no proposal/spec/monkey/stress surface |

## Required Contracts
- API: none (portal_index still 200; `/api/portal/navigation` unchanged; status `portal_spa_enabled` key preserved). contract-reviewer CONFIRMS no status/health endpoint drops the key.
- CSS/UI: none (dead-CSS removal within already-`.theme-admin-pages`-scoped file; `css:check` must still pass). Confirm no `css-inventory` entry invalidated.
- Env: none (`PORTAL_SPA_ENABLED` kept). NOTE: if implementation decides to remove/simplify the flag → promotes to env-contract change (env-contract.md + env.schema.json + .env.example).
- Data shape / Business / CI/CD: none.

## Required Tests
- unit: backend — `portal_index` always serves the SPA; `url_for('portal_index')` resolves; status payload keeps `portal_spa_enabled`; `is_portal_spa_enabled` unchanged. frontend — vitest `aria-pressed` reflects toggle state + `role="alert"` on error panel.
- Deletions: remove `portal.html` render tests + `PORTAL_SPA_ENABLED=false` branches in test_template_integration / test_portal_shell_routes / test_hold_routes / test_yield_alert_shell_coverage — **deliberate deletes, NOT skip/xfail**.
- contract/integration/E2E/visual/data-boundary/resilience/fuzz/stress/soak: none new (existing must stay green).

## Required Agents
spec-architect → contract-reviewer (read-only no-change confirm) → test-strategist → ci-cd-gatekeeper → implementation-planner → backend-engineer → frontend-engineer → ui-ux-reviewer → qa-reviewer.
(No visual-reviewer — a11y non-visual. No e2e/stress engineers.)

## Inferred Acceptance Criteria
- AC-1: non-SPA `portal.html` render branch removed; `portal_index` (`/`) serves the SPA by default, no user-visible change; full pytest + vitest + CI green.
- AC-2: `portal_index` route NAME preserved (`url_for('portal_index')` resolves from 404/403/500 + admin/pages templates); `test_app_factory.py` pins it.
- AC-3: no orphaned drawer-era CSS remains in `admin-pages/style.css`; `css:check` passes.
- AC-4: admin status-toggle exposes `aria-pressed` (reflects Released/Dev); load-error panel exposes `role="alert"`.
- AC-5: `PORTAL_SPA_ENABLED` non-portal consumers unchanged (`modernization_policy.is_portal_spa_enabled`; status `portal_spa_enabled` key); flag not deleted/default-changed in env-contract/env.schema.
- AC-6: `templates/portal.html` deleted; no surviving code/test references `portal.html` or the non-SPA branch.
- AC-7: removed render tests are deliberately deleted (not skip/xfail); no new test failure introduced.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.2, 3.3, 3.4, 3.5, 4.3, 4.4, 5.2, 6.4

## Clarifications or Assumptions
1. Single change (no atomic split): 3 items share the nav-config-to-code origin; ≤2 surfaces, 0/6 contracts, ~6-8 tasks.
2. Flag stays: `PORTAL_SPA_ENABLED` kept (live non-portal consumers). If implementation removes/simplifies it → env-contract change (re-trigger contract tests).
3. No API change: status payload keeps `portal_spa_enabled`. contract-reviewer must confirm no endpoint drops it.
4. Modernization manifests untouched (portal.html = legacy home, not a tracked report page) — CER-001 covers the case spec-architect finds otherwise.
5. i18n: a11y adds ARIA roles/states, not visible text; if any visible label/aria-label string is added, sync all i18n files.

## Context Manifest Draft
Full draft written to `context-manifest.md` (Allowed Paths, per-agent packets, CER-001).
