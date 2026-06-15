---
change-id: fix-e2e-spec-failures
schema-version: 0.1.0
last-changed: 2026-06-15
---

# Implementation Plan: fix-e2e-spec-failures

## Objective
Repair the 6 root-cause groups (A–F) so the Playwright E2E suite reaches 130 passed / 0 failed / 3 skipped without depending on Oracle. Fix root causes only; do not weaken assertions or lower waits to force green. ALL edits confined to `frontend/tests/playwright/` (AC-8).

## Execution Scope

### In Scope
- Group A: retarget production-history submit button to `[data-testid="ph-query-btn"]` in 2 specs.
- Group B: open sidebar before sidebar-link clicks in 2 specs.
- Group C: authenticate + SPA-navigate the hold-history async describe block (replace hash-URL goto).
- Group D: change wip-matrix `waitForSelector` to an always-rendered container selector.
- Group E: register the initial-fetch `waitForResponse` before navigation in pruning-feedback.
- Group F: convert reject-history + reject-material-flat-table specs to full API mocks matching the documented envelope.

### Out of Scope
- Any change to production source, contracts, CSS, env, or CI workflow files (AC-8).
- Any change to `_auth.js` `navigateViaSidebar` behavior (already fixed in prior commit; reuse as-is).
- Refactoring unrelated specs, renaming helpers, or "tidying" passing tests.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-A | Group A | Replace `page.locator('button:has-text("查詢")').first()` with `page.locator('[data-testid="ph-query-btn"]')` (button substring-matches tab buttons 依產品分類查詢/依識別碼查詢). | e2e-resilience-engineer |
| IP-B | Group B | Replace raw `page.goto('/portal-shell/')` + `page.click('a[href*=...]')` with sidebar-open-first navigation (sidebar starts closed, route watcher re-closes it). | e2e-resilience-engineer |
| IP-C | Group C | Add `loginViaApi(page)` + `navigateViaSidebar(page, 'hold-history', { waitForSelector: '.ui-card' })`; remove `page.goto('/portal-shell.html#/hold-history')` (hash URL bypasses auth). | e2e-resilience-engineer |
| IP-D | Group D | Change `waitForSelector: 'table'` to `waitForSelector: '.matrix-container'`; existing `test.skip` guards handle empty-data case. | e2e-resilience-engineer |
| IP-E | Group E | Register the initial filter-options `waitForResponse` before `navigateViaSidebar` (mount call completes during navigation, before the current registration). | e2e-resilience-engineer |
| IP-F | Group F | Add `page.route` mocks for all `/api/reject-history/**`, `/api/material-trace/**` and async `/api/job/**` endpoints used; envelope `{ success:true, data:<payload>, meta:{} }`; populated `detail` rows so column assertions hold. | e2e-resilience-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | § Inferred Acceptance Criteria (AC-1..AC-8) | authoritative acceptance criteria |
| change-classification.md | § Required Tests | test families + green target (130/0/3) |
| test-plan.md | § Test Execution Ladder | required phases (collect, targeted, changed-area) |
| ci-gates.md | § Required Gates | verification gate names (scaffold; reference by name) |
| _auth.js | `loginViaApi` L54, `navigateViaSidebar` L161, sidebar-open pattern L184-188 | reuse helpers; copy inline toggle for goBack case |
| src/.../reject_history_routes.py | `/query` 202 shape L762-770; sync `success_response(result)` L724 | Group F mock shape |
| core/response.py | `success_response` L91 → `{success, data, meta}` | Group F envelope wrapper key |
| frontend/src/reject-history/App.vue | result keys L497-537 (`summary`,`detail`,`available_filters`,`total_row_count`,`spool_download_url`); endpoints `/query` L609, `/view` L783, `/batch-pareto` L436 | Group F payload field names |
| reject-history/components/DetailTable.vue | props `items`, `pagination` L13-15 | `detail` mock shape `{items, pagination}` |
| frontend/src/wip-overview/components/MatrixTable.vue | `<table>` gated by `workcenters.length` L115-116 | Group D root cause |
| frontend/src/wip-overview/App.vue | `.matrix-container` L556 (always rendered) | Group D selector target |
| frontend/src/production-history/App.vue | `data-testid="ph-query-btn"` L498; tab buttons L270/L284 | Group A confirmation |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| tests/playwright/production-history-multi-line-input.spec.ts | edit | L111, L145: `'button:has-text("查詢")').first()` → `'[data-testid="ph-query-btn"]'`. Keep `toBeEnabled`/dedup/`.ph-app__form-error` assertions unchanged. |
| tests/playwright/production-history-wildcard-paste.spec.ts | edit | L124, L149, L182: same retarget. Keep raw-`*` and 400-error assertions unchanged. |
| tests/playwright/job-abandon-on-unload.spec.js | edit | L22-25: replace goto+click with `await navigateViaSidebar(page,'reject-history',{waitForSelector:'input[type="date"]'})`. Import `navigateViaSidebar` from `./_auth.js`. Keep 202/abandon assertions. |
| tests/playwright/resilience/browser-history.spec.js | edit | L177 (back/forward test, classification ref "165"): before `page.click('a[href*="reject-history"]')`, open sidebar inline (locate `button.sidebar-toggle`, click if `aria-expanded!=='true'`) — do NOT use `navigateViaSidebar` here (its `page.goto` breaks `goBack`). Keep first nav via `navigateViaSidebar`. |
| tests/playwright/hold-history-flat-table.spec.js | edit | In `hold-history async 202 path` describe (3 tests): add `await loginViaApi(page)` and replace each `page.goto('/portal-shell.html#/hold-history')` (L161,L192,L226) with `navigateViaSidebar(page,'hold-history',{waitForSelector:'.ui-card'})`. Keep `.async-job-progress` / overlay-suppression assertions. Existing flat-table describe already uses helper — leave untouched. |
| tests/playwright/wip-matrix-drilldown.spec.js | edit | L17, L76: `waitForSelector: 'table'` → `waitForSelector: '.matrix-container'`. Keep all `test.skip('No matrix data cells...')` guards and URL/CSS assertions unchanged. |
| tests/playwright/production-history-pruning-feedback.spec.ts | edit | Move the initial filter-options `waitForResponse` (currently L69) to a promise registered BEFORE `navigateViaSidebar` (L64), then await it after. Keep pruned-notice appear+auto-clear assertions (L93-97). |
| tests/playwright/reject-history.spec.js | edit | Add `page.route` mocks before `loginViaApi`/nav for every endpoint hit: `/options`, `/summary`, `/trend`, `/reason-pareto`, `/batch-pareto`, `/list`, `/view`, `/query`, `/export`, `/analytics`, and `/api/job/**`. Return envelope with populated `detail.items`. CSV-export test must mock `/export` (or `/export-cached`) with a downloadable body so `waitForEvent('download')` fires. Keep all assertions. |
| tests/playwright/reject-material-flat-table.spec.js | edit | Same reject-history mock set for the reject-history describe; add `/api/material-trace/**` mocks for the material-trace describe (textarea query → `查詢結果` card). `detail.items` must carry columns rendering `LOT`/`WORKCENTER`/`原因` (confirm key→header map in DetailTable.vue column config). Keep flat-structure + column-presence assertions. |

## Contract Updates
- API: none (mocks emulate existing documented `/api/reject-history/*` and `/api/material-trace/*` responses; no contract change).
- CSS/UI: none.
- Env: none.
- Data shape: none (mock bodies follow `success_response` envelope `{success,data,meta}`; verify against routes, do not invent fields).
- Business logic: none.
- CI/CD: none.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (Group A) | frontend/tests/playwright/production-history-multi-line-input.spec.ts | both tests pass; dedup body + form-error block |
| AC-1 (Group A) | frontend/tests/playwright/production-history-wildcard-paste.spec.ts | 3 tests pass; raw `*` preserved, 400 surfaces error |
| AC-2 (Group B) | frontend/tests/playwright/job-abandon-on-unload.spec.js | nav reaches reject-history; abandon flow asserts pass |
| AC-2 (Group B) | frontend/tests/playwright/resilience/browser-history.spec.js | back/forward test reaches reject-history; goBack lands on query-tool |
| AC-3 (Group C) | frontend/tests/playwright/hold-history-flat-table.spec.js | async describe authenticated; `.async-job-progress` visible then hidden |
| AC-4 (Group D) | frontend/tests/playwright/wip-matrix-drilldown.spec.js | beforeEach resolves on `.matrix-container`; tests pass or auto-skip |
| AC-5 (Group E) | frontend/tests/playwright/production-history-pruning-feedback.spec.ts | pruned notice appears then auto-clears |
| AC-6 (Group F) | frontend/tests/playwright/reject-history.spec.js | 4 tests pass against mocks; no Oracle hit |
| AC-6 (Group F) | frontend/tests/playwright/reject-material-flat-table.spec.js | flat-table + column tests pass against mocks |
| AC-7 (full suite) | `cd frontend && npm run test:e2e` (full Playwright run) | 130 passed / 0 failed / 3 skipped |

Phases: collect, targeted, changed-area (always); full suite for AC-7. Generate evidence via `cdd-kit test run`; do not weaken or skip specs to reach green. Full ladder in test-plan.md / references/sdd-tdd-policy.md.

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Group F: if any reject-history/material-trace endpoint returns a field shape NOT derivable from the route + App.vue/DetailTable consumer, STOP and raise CER-003 rather than guessing (per classification § Clarifications).
- Do NOT call `navigateViaSidebar` in the browser-history back/forward case (IP-B, L177) — it issues `page.goto` that pushes an extra history entry and breaks `goBack`.

## Known Risks
- Count mismatch: change-request says "Group C (2)" / "Group F (7)", but the hold-history async describe has 3 tests using the hash URL and Group F spans 9 tests across 2 files. Fix all occurrences in scope; the headline counts are approximate, not a cap. AC-7's 130/0/3 is the binding target.
- Group F mock surface is large (≥10 reject-history endpoints + job-poll + material-trace). The reject-history `result` shape is composite (`summary`/`detail`/`available_filters`/`analytics_raw`/`total_row_count`); build from `reject_history_routes.py` + `reject-history/App.vue` consumer, not from memory. `browser-history.spec.js` L42-52 has a minimal `{success:true,data:{data:[],total:0}}` reject mock as a starting envelope, but it is too thin for column-presence assertions — populate `detail.items`.
- Group F column-presence tests require the exact key→header mapping (`LOT`/`WORKCENTER`/`原因`); confirm in `DetailTable.vue` / shared DataTable column config before authoring `detail.items` keys.
- Group D assumes Oracle-backed real WIP data still renders `<table>` after the helper un-routes `**/api/wip/**`; if real data is empty the in-test `test.skip` guards keep the suite green (consistent with AC-4).
- Group C: hold-history page mounts and auto-queries on load; ensure `/api/hold-history/query**` + `/api/job/**` mocks are registered (via `setupBaseRoutes` + per-test route) before `navigateViaSidebar` so the 202/poll path fires deterministically.
- test-plan.md and ci-gates.md are still scaffolds; referenced by path/section. If gate names are finalized later, this plan's verification rows remain valid (they map ACs to spec files + the full-suite command).
