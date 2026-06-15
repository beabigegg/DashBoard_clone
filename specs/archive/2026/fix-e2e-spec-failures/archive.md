---
change-id: fix-e2e-spec-failures
archived: 2026-06-15
---

# Archive: fix-e2e-spec-failures

## Change Summary

Repaired 21 failing Playwright E2E specs across 9 spec files in 6 independent
root-cause groups (A–F). The suite was producing 109 passed / 21 failed / 3
skipped on every run due to wrong button selectors, a closed sidebar default,
hash-URL auth bypass, a data-gated table selector, a request-race in
waitForResponse ordering, and missing route mocks for reject endpoints. All
repairs are confined to `frontend/tests/playwright/`; zero production source
files were modified.

## Final Behavior

Full Playwright suite: **126 passed / 0 failed / 7 skipped** (exit 0).
7 skips = 3 pre-existing intentional skips (hold-overview, material-consumption,
browser-history L124) + 4 wip-matrix-drilldown tests that skip via the
pre-existing `if (matrixCell.count() === 0) test.skip()` guard (WIP stub mock
returns empty data → no matrix cells → skip as designed).

## Final Contracts Updated

None — test-only change. No API, CSS, env, data-shape, business-logic, or CI
workflow contracts were modified.

## Final Tests Added / Updated

| spec file | group | fix |
|---|---|---|
| production-history-multi-line-input.spec.ts | A | button selector → `[data-testid="ph-query-btn"]` |
| production-history-wildcard-paste.spec.ts | A | same selector fix (3 sites) |
| job-abandon-on-unload.spec.js | B | replaced raw goto + click with navigateViaSidebar |
| resilience/browser-history.spec.js | B | inline sidebar toggle before second nav (no navigateViaSidebar to avoid extra history entry) |
| hold-history-flat-table.spec.js | C | added loginViaApi + navigateViaSidebar for 3 async-202 tests |
| wip-matrix-drilldown.spec.js | D | waitForSelector `table` → `.matrix-container` |
| production-history-pruning-feedback.spec.ts | E | moved waitForResponse registration before navigateViaSidebar |
| reject-history.spec.js | F | added page.route mocks for /query, /view, /batch-pareto, /export-cached + populated detail.items rows |
| reject-material-flat-table.spec.js | F | same + separate material-trace mocks; added queryBtn.click() in beforeEach |

## Final CI/CD Gates

- `static-scope-check` (tier 0, required) — git diff must return empty outside `frontend/tests/playwright/`
- `e2e-targeted` (tier 1, required) — 9 repaired spec files, 0 failures
- `e2e-full-suite` (tier 1, required) — full suite 126/0/7
- `playwright-html-report` (tier 2, informational) — uploaded as PR artifact

## Production Reality Findings

Two deviations from implementation plan discovered during repair:

1. **Playwright LIFO route matching** — `page.route` catch-all must be registered
   FIRST so specific routes registered LAST take priority (LIFO). The plan noted
   the requirement but not the ordering constraint explicitly; discovered when the
   catch-all was intercepting `/query`.

2. **reject-material beforeEach needs a query trigger** — `reject-history` does
   not auto-query on mount; `DetailTable` only renders after `queryId` is set.
   Adding route mocks alone was insufficient; `beforeEach` also needed to click
   the query button.

QA attestation: all 5 test-discipline constraints pass (no assertion weakened,
no wait lowered, Group F mocks populated, browser-history back/forward uses
inline nav, no test.skip added). Evidence: `agent-log/bug-fix-engineer.yml` +
`test-evidence.yml` + full-suite stdout (126/0/7).

## Lessons Promoted to Standards

Two one-liners added to CLAUDE.md `CI workflow & GunicornHarness` block (inside `cdd-kit:learnings` markers):

| lesson | target | evidence |
|---|---|---|
| `page.route()` LIFO: catch-all FIRST, specific routes LAST | CLAUDE.md L180 | agent-log/e2e-resilience-engineer.yml deviation #1 |
| reject-history / reject-material `DetailTable` requires `queryId` — click submit in beforeEach | CLAUDE.md L181 | agent-log/e2e-resilience-engineer.yml deviation #2 |

No contract file changes. No schema-version bumps. Detail pointers → `docs/architecture/ci-workflow.md`.

## Follow-up Work

- wip-matrix-drilldown 4 tests (AC-1–AC-4) will only execute when Oracle data is
  available or the WIP stub mock is extended with real matrix cell data. Track as
  separate change if matrix cell coverage is required.
- API conformance gap (32 backend routes not in contract) is pre-existing and
  outside this change's scope.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance (`CLAUDE.md`, `CODEX.md`, `docs/`).
