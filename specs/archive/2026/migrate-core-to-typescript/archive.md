# Archive — migrate-core-to-typescript

Closed: 2026-05-05

## Change Summary

Phase 1a of the TypeScript migration plan: all 21 `.js` files in
`frontend/src/core/` were renamed to `.ts` and annotated with TypeScript
types. A new `types.ts` module was introduced for shared interfaces (notably
`ApiResponse<T>`). The `tsconfig.json` include scope was expanded from the
Phase 0 placeholder `src/core/index.ts` to `src/core/**/*`. This change
establishes the typed API-layer foundation for all subsequent migration phases
(1b, 1c, 2, 3).

## Final Behavior

- `frontend/src/core/` contains only `.ts` files (0 `.js` remaining).
- `ApiResponse<T>` generic interface exported from `frontend/src/core/index.ts`.
- `vue-tsc --noEmit` (`npm run type-check`) checks all 21 core modules with 0
  errors.
- Runtime behavior is unchanged; no business logic was modified.

## Final Contracts Updated

| Contract | Change | Evidence |
|---|---|---|
| `contracts/ci/ci-gate-contract.md` | Added Gate Compatibility Notes: `frontend-type-check` scope expanded from 0 → 21 core modules | `agent-log/ci-cd-gatekeeper.yml` |

## Final Tests Added / Updated

| Test | Change | Evidence |
|---|---|---|
| `frontend/tests/legacy/*.test.js` | Updated to import `.ts` source via `module.stripTypeScriptTypes()` | `agent-log/frontend-engineer.yml` notes |
| Vitest suite | 270/270 tests passing post-rename | `agent-log/qa-reviewer.yml` gate-results |
| `tests/test_frontend_compute_parity.py` | Updated path `compute.js → compute.ts`; added `--experimental-strip-types` to Node subprocess | CI fix commit `05e8c99` |
| `tests/test_frontend_duckdb_parity.py` | Updated both `risk-score.js → risk-score.ts`; added `--experimental-strip-types` to `_run_node()` | CI fix commit `b2fd91b` |

## Final CI/CD Gates

| Gate | Tier | Result |
|---|---|---|
| contract-validate (`cdd-kit validate`) | 0 | pass |
| frontend-unit (`npm run test`) | 1 | pass — 270/270 |
| frontend-build (`npm run build`) | 1 | pass — 19 entry points |
| css-governance (`npm run css:check`) | 1 | pass |
| frontend-type-check (`vue-tsc --noEmit`) | 1 | informational — pass |
| backend-tests (pytest `unit-and-integration-tests`) | 1 | pass (after Node setup fix) |
| contract-driven-gates (pytest + Vitest) | 1 | pass (after conda pin fix) |

## Production Reality Findings

The `.js → .ts` rename broke two Python parity test files that call Node
subprocesses to import frontend source files. This was not caught by the
initial ci-cd-gatekeeper review because `backend-tests.yml` and parity tests
were out of scope for a "frontend-only" classification. Four CI fix commits
were required after the initial implementation:

1. `frontend-tests.yml` needed `node-version: "20" → "22"` (Node 22+ required
   for `--experimental-strip-types`).
2. `contract-driven-gates.yml` both Node version occurrences bumped to `"22"`.
3. `test_frontend_compute_parity.py` path and Node subprocess args updated.
4. `environment.yml` `nodejs>=22` pinned to `nodejs>=22.6` (conda could install
   22.0–22.5 which lack the flag); `test_frontend_duckdb_parity.py` path and
   `_run_node()` updated; `backend-tests.yml` needed `setup-node@v4` added
   (it had no Node setup at all).

The key insight: `backend-tests.yml` runs pytest using `setup-python` only —
no Node setup. When the parity tests gained `--experimental-strip-types`, they
started failing on the runner's default node (≤20). The change-classifier
marked the change as "frontend-only", so `backend-tests.yml` was never in
scope for the original review.

## Lessons Promoted to Standards

| # | Lesson | Promoted To | Target | Evidence |
|---|---|---|---|---|
| 1 | Python parity tests require `--experimental-strip-types` + Node ≥22.6 | guidance | `CLAUDE.md` §TypeScript Migration Rules | `tests/test_frontend_*_parity.py:25,46,59` |
| 2 | `backend-tests.yml` must include `setup-node@v4 node-version: "22"` | contract | `contracts/ci/ci-gate-contract.md` §Workflow Configuration; `contracts/CHANGELOG.md [ci 1.3.0]` | CI fix commit `06eaad3` |
| 3 | `environment.yml` must pin `nodejs>=22.6`, not `>=22` | contract | `contracts/ci/ci-gate-contract.md` §Environment Constraints; `contracts/CHANGELOG.md [ci 1.3.0]` | `environment.yml:16`; CI fix commit `b2fd91b` |
| 4 | `.js → .ts` renames require auditing Python test file-path references | guidance | `CLAUDE.md` §TypeScript Migration Rules | CI fix commits `05e8c99`, `b2fd91b` |

## Follow-up Work

- **Phase 1b**: Migrate `frontend/src/shared-composables/` to TypeScript
  (`/cdd-new migrate shared-composables/ to TypeScript`).
- **Phase 1c**: Migrate `frontend/src/shared-ui/` components to TypeScript.
- **frontend-type-check promotion**: After 20 days / 60 CI runs at 100% pass
  rate, promote from informational to required (per `contracts/ci/ci-gate-contract.md`
  Gate Compatibility Notes).

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance in `CLAUDE.md`. Do not treat prose here as current
specifications.
