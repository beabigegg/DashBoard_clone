---
change-id: migrate-hold-history-ts
schema-version: 0.1.0
last-changed: 2026-05-12
risk: low
tier: 3
---

# Test Plan: migrate-hold-history-ts

## Acceptance Criteria → Test Mapping

| AC | Test family | Test file path | Test name | Tier | Pass condition |
|---|---|---|---|---|---|
| AC-1 | static-gate | — | `npm run type-check` | 3 | exits 0; main.ts resolves |
| AC-1 | static-gate | — | `npm run build` | 3 | exits 0; no missing entry-point error |
| AC-2 | static-gate | — | `npm run type-check` | 3 | exits 0; no reference to useAutoRefresh.js remains |
| AC-2 | unit | frontend/tests/validation/useHoldOverview.validation.test.js | existing suite | 3 | all tests pass; no import path errors |
| AC-3 | static-gate | — | `npm run type-check` | 3 | exits 0; useHoldHistoryDuckDB.ts compiles with no implicit any |
| AC-4 | static-gate | — | `npm run type-check` | 3 | exits 0; App.vue script setup lang="ts" compiles |
| AC-5 | static-gate | — | `npm run type-check` | 3 | exits 0; all 8 SFCs compile with typed defineProps |
| AC-6 | static-gate | — | `npm run type-check` | 3 | exits 0; no stale .js specifier errors |
| AC-7 | static-gate | — | `npm run type-check` | 3 | exits 0; tsconfig.json includes src/hold-history/**/* |
| AC-8 | contract | contracts/ci/ci-gate-contract.md | schema-version field = 1.3.6 | 3 | grep passes |
| AC-8 | contract | contracts/CHANGELOG.md | [ci 1.3.6] entry present | 3 | grep passes |
| AC-9 | static-gate | — | `npm run type-check` | 3 | exits 0 |
| AC-9 | static-gate | — | `npm run build` | 3 | exits 0 |
| AC-9 | static-gate | — | `npm run css:check` | 3 | exits 0 |
| AC-10 | unit | frontend/tests/components/HoldMatrix.test.js | existing suite | 3 | all tests pass; zero regressions vs. baseline |
| AC-10 | unit | frontend/tests/validation/useHoldOverview.validation.test.js | existing suite | 3 | all tests pass |
| AC-10 | unit | — (full Vitest run) | `npm run test` | 3 | 270+ tests pass; no new failures |
| AC-11 | static-gate | — | `npm run type-check` | 3 | exits 0; no implicit any warnings |
| AC-12 | cdd-gate | — | `cdd-kit gate migrate-hold-history-ts --strict` | 3 | exits 0 |

## Test Families Required

static-gate / unit / contract / cdd-gate

## Out of Scope

- New Vitest unit tests for hold-history composables (no new behaviour introduced).
- Python backend tests — no Python file references hold-history source paths.
- E2E tests (`tests/e2e/test_hold_history_e2e.py`) — runtime behaviour is unchanged; E2E is not a pre-merge gate for a pure rename (nightly only, per test-layer governance).
- Property tests (`tests/property/test_hold_history_duration_invariants.py`) — same rationale; data contracts not modified.
- Resilience / monkey / stress / soak — not applicable for Tier 3.

## Notes

This is a pure TypeScript migration (Tier 3). All ACs are verified by static gates
(`type-check`, `build`, `css:check`) and the existing Vitest suite. No new test files
are required. The ci-gate-contract.md bump (AC-8) is verified by grep, not a test runner.
