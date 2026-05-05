# Archive — migrate-shared-composables-ts

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

---

## Change Summary

Phase 1b of the TypeScript migration program. Renamed all 11 `.js` composables plus `index.js` in `frontend/src/shared-composables/` to `.ts`, added explicit TypeScript type annotations throughout, and expanded `frontend/tsconfig.json` `include` from `["src/core/**/*"]` to `["src/core/**/*", "src/shared-composables/**/*"]`. The CI `frontend-type-check` gate now covers 32+ TypeScript modules under `strict: true` (up from 21 in Phase 1a). No runtime behavior changed; this is a pure compile-time migration establishing type contracts for all feature-app composable calls.

---

## Final Behavior

- `frontend/src/shared-composables/*.ts` are now type-checked under `strict: true` on every PR via the informational `frontend-type-check` gate.
- All 11 composables expose explicit return types; feature-app callers get IDE autocompletion and compile-time error detection for composable call sites.
- `frontend/src/shared-composables/index.ts` re-exports all composables with typed named exports.
- `useAutoRefresh` and `useAutocomplete` still delegate to `wip-shared/.js` (untyped) behind `@ts-expect-error` — Phase 1c will resolve this.

---

## Final Contracts Updated

| Contract | Change | Evidence |
|---|---|---|
| `contracts/ci/ci-gate-contract.md` | schema-version 1.3.0 → 1.3.1 (patch); Phase 1b Gate Compatibility Notes sub-section added | `agent-log/contract-reviewer.yml` |
| `contracts/CHANGELOG.md` | `[ci 1.3.1] — 2026-05-05` entry added | `agent-log/contract-reviewer.yml` |

---

## Final Tests Added / Updated

| File | Change | Evidence |
|---|---|---|
| `frontend/tests/shared-composables/useAsyncJobPolling.test.js` | Import specifier `.js` → `.ts` | `agent-log/frontend-engineer.yml` |
| `frontend/tests/shared-composables/useAutoRefresh.test.js` | Import specifier `.js` → `.ts` | `agent-log/frontend-engineer.yml` |
| `frontend/tests/shared-composables/useRequestGuard.test.js` | Import specifier `.js` → `.ts` | `agent-log/frontend-engineer.yml` |
| `frontend/tests/abort/production-history-abort.test.js` | Import specifiers updated (lines 25, 31) | `agent-log/frontend-engineer.yml` |
| `frontend/tests/abort/reject-history-abort.test.js` | Import specifiers updated (lines 49, 70) | `agent-log/frontend-engineer.yml` |
| `frontend/tests/abort/query-tool-abort.test.js` | `require()` → static `import`; specifiers updated (lines 38, 53) | `agent-log/frontend-engineer.yml` |

Vitest result: 270/270 passing. No new test files created; no test renames.

---

## Final CI/CD Gates

- No new gates added. No workflow YAML changes.
- `frontend-type-check` remains informational (`continue-on-error: true`). Promotion criteria documented in `ci-gates.md`.
- All required Tier 1 gates (`Run vitest suite`, `Run legacy node --test suite`, `Verify test discovery`) covered by existing `frontend-tests.yml` without modification.
- Merge eligibility: **mergeable**.

---

## Production Reality Findings

1. **`wip-shared/` dependency (untyped)**: `useAutoRefresh` and `useAutocomplete` import from `frontend/src/wip-shared/composables/*.js`, which have no TypeScript declarations. Resolved via `@ts-expect-error` + cast to a locally-declared interface. Phase 1c (`shared-ui/` migration) or a dedicated `wip-shared/` migration step should add declarations.

2. **CJS→ESM conversion required for `query-tool-abort.test.js`**: This test file used `require()` (CommonJS). When the source was renamed to `.ts` (ES Module), `require()` could no longer load it. Converted to static `import`. Evidence: `agent-log/frontend-engineer.yml` notes section.

3. **Feature-app directory reads not needed**: CER-001 (requested access to `frontend/src/wip-overview/` and 6 other feature-app dirs) was resolved as `not-needed`. Type-check passed without inspecting feature-app import sites.

4. **Python parity audit clean**: `grep -r "shared-composables.*\.js" tests/**/*.py` returned zero matches. No Python test file referenced the old `.js` paths.

---

## Lessons Promoted to Standards

| Lesson | Target | Evidence |
|---|---|---|
| CJS `require()` cannot load ES Module `.ts` files — convert test files to static `import` during source rename | `CLAUDE.md` §TypeScript Migration Rules (Rule #5) | `agent-log/frontend-engineer.yml` notes; `frontend/tests/abort/query-tool-abort.test.js` |
| `@ts-expect-error` + declared-interface + cast pattern for wrapping untyped `.js` cross-phase dependencies | `CLAUDE.md` §TypeScript Migration Rules (Rule #6) | `agent-log/frontend-engineer.yml` notes; `frontend/src/shared-composables/useAutoRefresh.ts`, `useAutocomplete.ts` |
| `import type { Ref, ComputedRef }` from Vue — **not promoted**: justification was inaccurate; enforcement belongs in ESLint (`@typescript-eslint/consistent-type-imports`), not prose | — | `agent-log/contract-reviewer-close.yml` |

---

## Follow-up Work

- **Phase 1c**: Migrate `frontend/src/shared-ui/` to TypeScript.
- **`wip-shared/` type declarations**: `useAutoRefresh.js` and `useAutocomplete.js` under `frontend/src/wip-shared/composables/` need TypeScript declarations or migration to remove `@ts-expect-error` workarounds.
- **Promote `frontend-type-check` to required gate**: After 20 calendar days / 60 PR runs with Phase 1b scope active and pass rate confirmed, update `contracts/ci/ci-gate-contract.md` and remove `continue-on-error: true` from `frontend-tests.yml` line 38.
