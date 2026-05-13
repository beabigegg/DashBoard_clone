---
change-id: migrate-wip-hold-ts
schema-version: 0.1.0
last-changed: 2026-05-13
---

# CI Gates — migrate-wip-hold-ts

Pure TypeScript migration of four frontend feature apps:
- `frontend/src/wip-overview/` (main.js→main.ts, all .vue files migrated)
- `frontend/src/wip-detail/` (main.js→main.ts, all .vue files migrated)
- `frontend/src/hold-overview/` (main.js→main.ts, all .vue files migrated)
- `frontend/src/hold-detail/` (main.js→main.ts, all .vue files migrated)

No backend, API, or CSS changes. `tsconfig.json` scope expanded to cover these four apps per `contracts/ci/ci-gate-contract.md` § 1.3.7.

## Pre-merge Gates (PR required)

| Gate | Tier | Command | Pass Condition |
|---|---|---|---|
| frontend-unit | 1 | `cd frontend && npm run test` | All 270 tests pass (27 Vitest files) |
| css-governance | 1 | `cd frontend && npm run css:check` | 0 violations (no new CSS changes) |
| contract-validate | 0 | `cdd-kit validate` | All contracts pass; ci-gate-contract.md updated to 1.3.7 |
| playwright-critical-journeys | 1 | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js` | All specs pass |

All four are **Tier 1 PR Required** gates per `contracts/ci/ci-gate-contract.md`. They block merge.

## Informational Gates (non-blocking)

| Gate | Tier | Command | Note |
|---|---|---|---|
| frontend-type-check | 1 | `cd frontend && npm run type-check` | 0 errors (already verified locally); scope now includes wip-overview, wip-detail, hold-overview, hold-detail per ci-gate-contract.md § 1.3.7; informational per Required Check Policy |

## Gates Removed / Not Applicable

- No new backend routes → no contract-validation gate needed (contract-validate is pre-merge for CI schema, not routing APIs).
- No Python parity tests reference wip-overview/wip-detail/hold-overview/hold-detail files → no Python parity audit.
- No hold-overview/hold-detail-specific Playwright spec exists → covered by critical-journeys suite only.
- No CSS additions → css-governance is pass-through (no new risk).

## Required Gates Statement

A PR for this change is merge-eligible when **all four pre-merge gates pass**: `frontend-unit`, `css-governance`, `contract-validate`, and `playwright-critical-journeys`.

## Workflow Configuration

All four pre-merge gates trigger automatically on every PR push via the CI workflow defined in `.github/workflows/frontend-tests.yml` and `.github/workflows/contract-driven-gates.yml`. The informational `frontend-type-check` runs in the same workflow pipeline.

## Trigger

All pre-merge gates run on `pull_request` against `main`. The informational `frontend-type-check` also runs on `pull_request` but does not block merge.

## Promotion Policy

The `frontend-type-check` gate is informational per ci-gate-contract.md § 1.3.7. No gate introduced in this change is a candidate for promotion — all pre-merge gates were already required before this change.

## Rollback Policy

No runtime behaviour changed. This is a pure TypeScript rename of four feature apps. If a post-merge regression is detected, revert the PR via GitHub revert button. No database, API, or asset rollback required.

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

# Contract validation (from repo root)
cdd-kit validate
```
