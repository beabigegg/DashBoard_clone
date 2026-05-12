---
change-id: migrate-hold-history-ts
schema-version: 0.1.0
last-changed: 2026-05-12
---

# CI Gates — migrate-hold-history-ts

Pure TypeScript migration of `frontend/src/hold-history/`. No backend, API, or CSS changes.

## Pre-merge Gates (PR required)

| Gate | Tier | Command | Pass Condition |
|---|---|---|---|
| frontend-unit | 1 | `cd frontend && npm run test` | All 270 tests pass |
| css-governance | 1 | `cd frontend && npm run css:check` | 0 violations |
| playwright-critical-journeys | 1 | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js` | All specs pass |

All three are **Tier 1 PR Required** gates per `contracts/ci/ci-gate-contract.md`. They block merge.

## Informational Gates (non-blocking)

| Gate | Tier | Command | Note |
|---|---|---|---|
| frontend-type-check | 1 | `cd frontend && npm run type-check` | 0 errors (already verified); informational per ci-gate-contract.md |

## Gates Removed / Not Applicable

- No new backend routes → no contract-validation gate needed.
- No Python parity tests reference hold-history files → no Python parity audit.
- No hold-history-specific Playwright spec exists → covered by critical-journeys suite only.
- No CSS additions → css-governance is pass-through (no new risk).

## Required Gates Statement

A PR for this change is merge-eligible when **all three pre-merge gates pass**: `frontend-unit`, `css-governance`, and `playwright-critical-journeys`.

## Workflow Configuration

All three pre-merge gates trigger automatically on every PR push via the CI workflow defined in `.github/workflows/frontend-tests.yml` and `.github/workflows/contract-driven-gates.yml`. The informational `frontend-type-check` runs in the same workflow pipeline.

## Trigger

All pre-merge gates run on `pull_request` against `main`. The informational `frontend-type-check` also runs on `pull_request` but does not block merge.

## Promotion Policy

If `frontend-type-check` surfaces errors in a subsequent run, open a follow-up issue; do not revert the migration. Type errors in a pure migration are never production-blocking.

## Rollback Policy

No runtime behaviour changed. If a post-merge regression is detected, revert the PR via GitHub revert button. No database or API rollback required.

## How to Run Locally

```bash
# From repo root
cd frontend

# Type check (informational)
npm run type-check

# Unit tests
npm run test

# CSS governance
npm run css:check

# Playwright critical journeys (requires dev server or built assets)
npx playwright test \
  tests/playwright/hold-overview.spec.js \
  tests/playwright/reject-history.spec.js \
  tests/playwright/query-tool.spec.js
```
