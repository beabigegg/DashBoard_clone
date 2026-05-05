# Change Classification

## Change Types
- primary: refactor
- secondary: typescript-migration, ci-cd-change (tsconfig scope expansion)

## Risk Level
- medium

## Impact Radius
- module-level (shared-composables/), with cross-module compile-time consumers (multiple feature apps import these)

## Tier
- 2

## Architecture Review Required
- no
- reason: Phase 1a established the migration pattern; this phase reuses it without architectural change.

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | No behavior change; pure type-layer migration. |
| proposal.md | no | Phase pattern already approved in Phase 1a; no new proposal needed. |
| spec.md | no | No new feature spec; types are derived from existing JS implementation. |
| design.md | no | Phase 1a established the design pattern (rename + types + tsconfig include). |
| qa-report.md | no | qa-reviewer fills review notes inline; no separate QA artifact required. |
| regression-report.md | no | No runtime behavior change; existing Vitest suite + type-check serve as regression evidence. |

## Required Contracts
- API: none
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: tsconfig.json `include` scope must expand to cover shared-composables; CI `frontend-tests` workflow already runs `npm run type-check` — no workflow file change expected, but type-check coverage scope changes are documented in ci-gates.md.

## Required Tests
- unit: existing Vitest tests in `frontend/tests/shared-composables/` (useAsyncJobPolling, useAutoRefresh, useRequestGuard) must continue to pass after rename.
- contract: `npm run type-check` acts as the compile-time contract; must pass with zero errors against shared-composables.
- integration: feature-app consumer Vitest suites that import shared-composables (query-tool-composables, material-trace-composables, mid-section-defect-composables) must continue to pass.
- E2E: not required (no runtime behavior change)
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
1. change-classifier (complete)
2. contract-reviewer — confirm zero contract surface impact and verify ci-gate-contract is unaffected beyond tsconfig include scope
3. test-strategist — produce test-plan.md mapping AC → existing Vitest + type-check coverage; decide test-file rename policy (.test.js vs .test.ts)
4. frontend-engineer — perform .js→.ts rename, add type signatures, update tsconfig `include`, update `index.ts` typed re-exports, audit Python parity tests for hardcoded `.js` paths
5. ci-cd-gatekeeper — write ci-gates.md capturing type-check scope expansion and confirm frontend-tests.yml still covers it
6. qa-reviewer — release-readiness review (always last)

## Inferred Acceptance Criteria
- AC-1: All `.js` files in `frontend/src/shared-composables/` (excluding `TraceProgressBar.vue`) are renamed to `.ts` and contain explicit type annotations on every exported function's parameters and return value.
- AC-2: `frontend/src/shared-composables/index.ts` exists and provides typed re-exports of all public composables (replacing the previous `index.js`).
- AC-3: `frontend/tsconfig.json`'s `include` array covers `shared-composables/**/*` so `npm run type-check` type-checks the new sources.
- AC-4: `cd frontend && npm run type-check` exits 0 with zero errors and zero warnings attributable to shared-composables.
- AC-5: Existing Vitest suites at `frontend/tests/shared-composables/` (useAsyncJobPolling, useAutoRefresh, useRequestGuard) continue to pass after the rename.
- AC-6: All feature-app consumer Vitest suites that import shared-composables (query-tool, material-trace, mid-section-defect composables tests) continue to pass.
- AC-7: No Python parity test in `tests/**/*.py` references a now-deleted `frontend/src/shared-composables/*.js` path; if any matched, references are updated to `.ts`.
- AC-8: No runtime behavior change — `npm run build` succeeds and emits the same module surface (no missing-export errors at SPA load time).

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 3.4, 3.5, 4.1, 4.3, 4.4, 5.1, 5.2

## Clarifications or Assumptions
- Open question (test file `.test.js` vs `.test.ts`) is deferred to test-strategist; default assumption is to keep `.test.js` and rely on Vitest's Node-strip-types resolver, matching Phase 1a precedent.
- `TraceProgressBar.vue` stays a `.vue` SFC; its `<script>` block migration to `lang="ts"` is optional.
- No feature-app `main.js` edits required — Vite resolves `.ts` extensions transparently when imports omit the extension.
- Python parity tests in `test_frontend_compute_parity.py` and `test_frontend_duckdb_parity.py` are expected to import from `frontend/src/core/` only; frontend-engineer must verify per CLAUDE.md TypeScript Migration Rules.
