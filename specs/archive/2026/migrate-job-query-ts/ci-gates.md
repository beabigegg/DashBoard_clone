---
change: migrate-job-query-ts
ci-contract-version: 1.3.11
date: 2026-05-13
---

# CI Gate Plan — migrate-job-query-ts

Pure TypeScript migration (Tier 3, no behavioral change).
No backend changes; no new runtime logic; no new test coverage required.

## Gate Table

| gate | tier | required | command | AC verified |
|---|---:|---|---|---|
| frontend-unit | 1 | yes (PR-blocking) | `cd frontend && npm run test` | AC-8 (Vitest suite zero regressions; parity test regex assertions pass) |
| css-governance | 1 | yes (PR-blocking) | `cd frontend && npm run css:check` | AC-7 (css:check exits 0); no new CSS violations |
| frontend-type-check | 1 | informational (continue-on-error) | `cd frontend && npm run type-check` | AC-7 (type-check exits 0); AC-5 (tsconfig include expanded); AC-9 (no bare `any`, no new `@ts-expect-error`) |
| contract-validate | 0 | yes (local pre-PR) | `cdd-kit validate` | AC-6 (ci-gate-contract schema 1.3.11; CHANGELOG entry present); AC-10 (cdd-kit gate --strict passes) |

### Build Verification (local pre-PR, not a CI pipeline gate)

| step | command | AC verified |
|---|---|---|
| Vite build | `cd frontend && npm run build` | AC-7 (build exits 0); AC-1 (`index.html` → `main.ts` resolved by Vite at build time) |

## Not-Applicable Gates

| gate | reason |
|---|---|
| unit-mock-integration (`pytest`) | No Python changes in this migration |
| lint (`ruff check .`) | No Python changes |
| type-check (`mypy src/`) | No Python changes |
| playwright-resilience | No behavioral change; no new endpoint or runtime path |
| playwright-data-boundary | No behavioral change; no new data contract |
| playwright-critical-journeys | No behavioral change; existing E2E coverage unchanged |
| visual-regression | No UI change; template and CSS untouched |
| nightly-integration | No new real-infra test coverage added by this change |
| stress-load | No new stress/load scenarios added by this change |
| soak | No new soak scenarios added by this change |

## Schema-Version Note — 1.3.11

- **What changed**: additive prose in `contracts/ci/ci-gate-contract.md` documenting
  `frontend-type-check` scope expansion to `src/job-query/**/*` (Phase 3 migration of
  `main.ts`, `App.vue`, `composables/useJobQueryData.ts`).
- **Previous version**: 1.3.10 (resource-history-perf — new test coverage scope note).
- **Gate tier, command, and status**: unchanged. `frontend-type-check` remains
  informational (continue-on-error: true).
- **`contracts/CHANGELOG.md`**: [ci 1.3.11] entry added (same PR).
- **`frontend/tsconfig.json`**: `"src/job-query/**/*"` appended to `include` (confirmed
  present — covers `main.ts`, `App.vue`, `composables/useJobQueryData.ts`).

## Local Verification (run before opening PR)

```bash
# 1. Contract validation
cdd-kit validate

# 2. Frontend unit tests (PR-blocking gate)
cd frontend && npm run test

# 3. CSS governance (PR-blocking gate)
cd frontend && npm run css:check

# 4. TypeScript type check (informational gate — must exit 0 per AC-7)
cd frontend && npm run type-check

# 5. Vite build (confirms main.ts resolution via index.html entry point)
cd frontend && npm run build

# 6. Full CDD gate check (AC-10)
cdd-kit gate migrate-job-query-ts --strict
```

All six commands must exit 0 before the PR is opened.

## Required Gates, Trigger, and Policies

**Required gates** (PR-blocking): `frontend-unit`, `css-governance`.
`frontend-type-check` is also required to exit 0 locally but runs as
`continue-on-error: true` in CI (informational). `contract-validate` is
required locally (pre-PR) and is not part of the CI pipeline.

**Trigger**: all PR-blocking gates fire on every `pull_request` event via the
`frontend-ci` **workflow** (`.github/workflows/frontend-ci.yml`).

**Promotion policy**: `frontend-type-check` will be promoted from informational
to required once all Phase 3 feature-app migrations are complete and the gate
has held clean for two consecutive release cycles.

**Rollback policy**: if a gate failure is discovered post-merge, revert the merge
commit immediately and re-open the PR with a fix. No direct hotfix to main.
