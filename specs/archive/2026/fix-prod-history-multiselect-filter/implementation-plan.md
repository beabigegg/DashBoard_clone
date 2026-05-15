---
change-id: fix-prod-history-multiselect-filter
schema-version: 0.1.0
last-changed: 2026-05-15
---

# Implementation Plan: fix-prod-history-multiselect-filter

## Objective

Buffer first-tier MultiSelect toggles in Production History so cross-filter and main-query requests fire only when the dropdown closes (outside-click, Escape, or focus-leave). Achieve this by (a) adding an additive `dropdown-close` emit to the shared `MultiSelect.vue`, (b) splitting `useFirstTierFilters` into a no-side-effect `setSelection` buffer plus a new `commitSelection` that diffs and triggers `_scheduleRefresh()`, and (c) wiring `@dropdown-close` on the 4 MultiSelects in `production-history/App.vue`. See `design.md` for the contract.

## Execution Scope

### In Scope
- Add additive `dropdown-close` event to `frontend/src/shared-ui/components/MultiSelect.vue`.
- Split buffer/commit in `frontend/src/production-history/composables/useFirstTierFilters.ts` (`setSelection` stays buffer-only; new `commitSelection(field)` triggers `_scheduleRefresh`).
- Wire `@dropdown-close` on the 4 first-tier MultiSelects in `frontend/src/production-history/App.vue` (lines 320, 332, 344, 356).
- New unit test file `frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts`.
- Extend `frontend/tests/legacy/production-history.test.js` (migrate the 2 existing tests that relied on `setSelection` to use `commitSelection`; add 6 new tests).
- Extend `frontend/tests/playwright/production-history-cross-filter.spec.ts` (6 new cases per test-plan).

### Out of Scope
- Visual / layout / token changes (AC-5: zero CSS edits).
- Backend, API payload, SQL, or contract changes (AC-6 holds).
- Apply button or any new chrome (CR §Constraints rejects this).
- Changes to the 8 other MultiSelect consumers (wip-detail, wip-overview, hold-overview, reject-history, resource-history, resource-status, query-tool, mid-section-defect, yield-alert-center) — additive emit only.
- Refactoring `_scheduleRefresh`'s 200 ms debounce window.
- Generalising buffered-commit pattern to wip-*/hold-* reports (see Out-of-scope follow-ups).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | shared-ui MultiSelect | Add `dropdown-close` to `defineEmits`; emit final `string[]` whenever `isOpen` transitions `true → false` (watch `isOpen` for the transition; covers outside-click, Escape, blur, programmatic `closeDropdown`). | frontend-engineer |
| IP-2 | production-history composable | Remove `_scheduleRefresh()` call from `setSelection`; introduce private snapshot map `_lastCommitted` populated at init + after each successful commit; export new `commitSelection(field: CachedFilterField)` that compares `selection[field]` to `_lastCommitted[field]`, no-ops on equality, otherwise updates snapshot and calls `_scheduleRefresh()`. | frontend-engineer |
| IP-3 | production-history App.vue | Add `@dropdown-close="firstTier.commitSelection('<field>')"` on all 4 first-tier MultiSelects (pj_types, packages, bops, pj_functions). | frontend-engineer |
| IP-4 | unit tests (Vitest) | Create new `MultiSelect.test.ts` with the 7 cases listed in test-plan. | frontend-engineer |
| IP-5 | unit tests (node:test) | Update two existing tests (lines 183, 218) to call `commitSelection` after `setSelection`; add 6 new tests covering buffer-only `setSelection`, `commitSelection` no-op, idempotency, multiple buffer→single commit, snapshot reset semantics. | frontend-engineer |
| IP-6 | E2E (Playwright) | Extend `production-history-cross-filter.spec.ts` with 6 new cases; rewrite existing assertions that closed the dropdown after every toggle to instead toggle multiple values then close once. | frontend-engineer |
| IP-7 | escape handling | Confirm Escape closes the dropdown — current MultiSelect.vue has NO keyboard handler for Escape on the popup (only outside-click + an explicit "關閉" button). Add a minimal `@keydown.esc.stop="closeDropdown"` on the dropdown root or search input so Escape fires `isOpen=false`, which then drives the new `dropdown-close` emit. | frontend-engineer |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| [frontend/src/shared-ui/components/MultiSelect.vue](../../../frontend/src/shared-ui/components/MultiSelect.vue) | edit | Add emit signature; add `watch(isOpen, (now, prev) => { if (prev && !now) emit('dropdown-close', [...props.modelValue].map(String)); })`. Add `@keydown.esc.stop="closeDropdown"` on the dropdown root (line ~145) to give Escape a path. Do NOT change template structure, CSS, or `update:modelValue` behaviour. |
| [frontend/src/production-history/composables/useFirstTierFilters.ts](../../../frontend/src/production-history/composables/useFirstTierFilters.ts) | edit | Strip `_scheduleRefresh()` call from `setSelection` (line 214). Add `const _lastCommitted: Record<CachedFilterField, string[]> = { pj_types: [], packages: [], bops: [], pj_functions: [] }`. Add exported `commitSelection(field)`. After `_pruneSelection` runs inside `fetchFilterOptions`, refresh `_lastCommitted` from `selection` so prune-driven mutations remain consistent. Add `commitSelection` to the returned object. Keep `_scheduleRefresh`'s 200 ms debounce unchanged. |
| [frontend/src/production-history/App.vue](../../../frontend/src/production-history/App.vue) | edit | Lines 320-365: add `@dropdown-close="firstTier.commitSelection('pj_types')"` (and `'packages'`, `'bops'`, `'pj_functions'`) on the 4 MultiSelects. No other edits. |
| frontend/src/shared-ui/components/\_\_tests\_\_/MultiSelect.test.ts | new | 7 Vitest cases per test-plan (single-emit on close, payload equals current modelValue, no emit during open, back-compat on update:modelValue, listener-absent regression). |
| [frontend/tests/legacy/production-history.test.js](../../../frontend/tests/legacy/production-history.test.js) | edit | Migrate the 2 existing tests (lines 183, 218) to call `commitSelection('pj_types')` after `setSelection`. Add 6 new tests per test-plan. |
| [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) | edit | Add 6 cases per test-plan; keep existing cross-filter convergence assertions intact (re-assert with single close instead of per-toggle close). |

## Contract Updates

- API: none. Cross-filter / main-query payload schema invariant (AC-6).
- CSS/UI: none. No new tokens, no rule changes, no DOM restructuring (AC-5).
- Env: none.
- Data shape: none.
- Business logic: add one line to `contracts/business/business-rules.md` — "Production History first-tier filter apply trigger = dropdown close (outside-click / Escape / focus-leave)." (handled by contract-reviewer; planner flags it here.)
- CI/CD: none.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `cd frontend && npm run test -- MultiSelect.test.ts` + `npx playwright test production-history-cross-filter.spec.ts -g "zero /filter-options"` | 0 `/filter-options` requests while dropdown remains open across N toggles. |
| AC-2 | `npx playwright test production-history-cross-filter.spec.ts -g "exactly 1 /filter-options"` (parametrized over outside-click/Escape/blur) | Exactly 1 `/filter-options` request after close per close-trigger; 0 main-query requests until `查詢` clicked. |
| AC-3 | `npx playwright test production-history-cross-filter.spec.ts -g "second filter still buffers"` | After first filter commits and cross-filter narrows, opening a 2nd filter and toggling still produces 0 requests until that filter also closes. |
| AC-4 | `cd frontend && npm run test -- production-history.test.js -g "commitSelection.*no-op"` + Playwright `-g "no-op close"` | `commitSelection` returns without calling the fetcher; 0 network requests on no-op close. |
| AC-5 | manual visual review | No CSS diff; reviewer signs `qa-report.md`. |
| AC-6 | `npx playwright test -g "payload schema"` | Captured `/filter-options` request body matches the snapshot from pre-fix baseline (`{ selected: { pj_types: [...], ... } }`). |
| Regression | `cd frontend && npm run test -- MultiSelect.test.ts -g "back-compat"` | Existing consumers without `@dropdown-close` listener observe identical behaviour (still see every `update:modelValue`). |
| Type-check | `cd frontend && npm run type-check` | 0 errors. |
| Contract | `cdd-kit validate && cdd-kit gate fix-prod-history-multiselect-filter` | Both green. |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- `setSelection` signature `(field, values)` is frozen — back-compat for any future caller. Only its side-effect changes (no longer schedules a refresh).
- `MultiSelect.vue` public surface changes must be additive only. 8 sibling apps must remain behaviorally identical when they ignore the new emit.
- Do NOT remove the 200 ms debounce in `_scheduleRefresh()` — it is a cheap safety net for back-to-back commits and removing it is out of scope.
- Escape-key handling must close the dropdown via `isOpen = false` (not via a separate emit path) so the single `watch(isOpen)` covers all close triggers.

## Known Risks

- Risk 1 — `watch(isOpen)` fires synchronously inside the same tick a toggle happens. Fix is fine because Vue watchers run after current task, but tests must assert emit after `await nextTick()`.
- Risk 2 — Blur close path: if a click inside the dropdown momentarily blurs the button, we must not treat that as close. Existing `handleOutsideClick` already filters by `rootRef.contains`, so blur-driven closes are limited to true focus-leave. Verify in Vitest with a focusin/focusout simulation.
- Risk 3 — Two existing legacy tests (lines 183, 218) currently assert that `setSelection` triggers a fetch. These will fail until migrated to `commitSelection`. Migrate them in the same PR as the source change; do not split.
- Risk 4 — `_lastCommitted` initial state is `[]` per field, matching `selection` initial state. If a future feature seeds the composable with a non-empty selection, the snapshot must be primed accordingly. Out of scope for this change; document as a follow-up.
- Risk 5 — Programmatic close via the "關閉" button (line 175) drives `isOpen = false` → `dropdown-close` fires → `commitSelection` runs. This is the desired path; explicitly noted so reviewers do not flag it.

## Out-of-scope follow-ups

- Adopt the same buffered-commit pattern in wip-detail, wip-overview, hold-overview, reject-history, resource-history, resource-status, query-tool, mid-section-defect, yield-alert-center filter composables. Create a separate change after this lands and is validated in production.
- Decide whether the 200 ms `_scheduleRefresh` debounce can be dropped once commit-on-close is the only entry point.
- Generalise `MultiSelect` to expose `v-model:open` for cases where parents need finer control over the open state.

