---
change-id: migrate-reject-history-ts
schema-version: 0.1.0
last-changed: 2026-05-12
---

# CI Gates: migrate-reject-history-ts

## Pre-merge gates (must pass before PR merge)

| gate | command | pass condition |
|---|---|---|
| frontend-type-check | `cd frontend && npm run type-check` | zero errors; `src/reject-history/**/*` now in tsconfig.json include |
| frontend-unit | `cd frontend && npm run test` | 270/270 Vitest tests pass (28 reject-history tests included) |
| css-governance | `cd frontend && npm run css:check` | no new violations; migration adds no CSS changes |

All three are **Tier 1 PR Required** gates per `contracts/ci/ci-gate-contract.md`. They block merge.

## Informational gates (run in CI, non-blocking)

| gate | command | note |
|---|---|---|
| playwright-critical-journeys | `cd frontend && npx playwright test tests/playwright/reject-history.spec.js` | 4 E2E tests; regression check only |
| python-parity-audit | `pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py` | verifies no stale `.js` path references for renamed reject-history files |

Python parity tests require Node ≥22.6 (`--experimental-strip-types`). Ensure
`uses: actions/setup-node@v4 / node-version: "22"` is present in any workflow
job running pytest. See ci-gate-contract.md § Node version constraint.

## Gates removed / not applicable

None. This migration adds no new gates and removes none.

## Required gates

`frontend-type-check`, `frontend-unit`, and `css-governance` are required gates.
They must pass before this change can be merged. See pre-merge table above.

## Trigger

All three pre-merge gates trigger automatically on every PR push via the CI
workflow defined in `.github/workflows/`. The two informational gates run on
`main` branch pushes only.

## Promotion policy

Informational gates follow the standard Informational Gate Promotion Policy
documented in `contracts/ci/ci-gate-contract.md`. Promotion requires:
1. Three consecutive passing runs on `main`.
2. A `contracts/ci/ci-gate-contract.md` PR updating the gate row's status to `required`.

No gate introduced in this change is a candidate for promotion — all three
pre-merge gates were already `required` before this change.

## Rollback policy

This change is a pure TypeScript rename. Rollback is achieved by reverting the
two commits on `main` (`feat(migrate-reject-history-ts)` and its fix commit).
No data migration or schema change is involved.

## How to run locally

```bash
# 1. Type-check (zero errors required)
cd frontend && npm run type-check

# 2. All Vitest unit tests
cd frontend && npm run test

# 3. CSS governance
cd frontend && npm run css:check

# 4. Playwright E2E (informational — needs a running dev server)
cd frontend && npx playwright test tests/playwright/reject-history.spec.js

# 5. Python parity audit (informational — run inside conda env)
conda run -n mes-dashboard pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py

# 6. Static grep audits (AC-4 / AC-5)
# Zero bare `any` without TODO annotation:
grep -rn '\bany\b' frontend/src/reject-history/ | grep -v '// TODO: type'
# Zero stale .js import specifiers inside migrated files:
grep -rn '\.js"' frontend/src/reject-history/
```
