---
change-id: fix-prod-history-multiselect-filter
schema-version: 0.1.0
last-changed: 2026-05-15
risk: medium
tier: 2
---

# Test Plan: fix-prod-history-multiselect-filter

## Test Layer Strategy

Pre-merge runs three layers: (1) **Vitest unit** for the new `MultiSelect` `@dropdown-close` emit contract, (2) **node:test legacy unit** extending the existing `useFirstTierFilters` suite to cover the new buffer/commit split, and (3) **Playwright E2E** extending the existing `production-history-cross-filter.spec.ts` to assert request counts during/after dropdown interactions. Backend integration, contract, data-boundary, stress, soak, and monkey tiers are skipped because this change touches only frontend event timing — no API payloads, schemas, SQL, or backend services change (AC-6 confirms payload schema is invariant). Visual regression is delegated to the Tier-2 visual reviewer per AC-5 (no CSS layer or token change) and not automated here.

## Acceptance Criteria → Test Mapping

| AC | Test family | Test file path | Test name(s) |
|---|---|---|---|
| AC-1 | E2E (Playwright) | [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) | `multi-select toggles inside open dropdown trigger zero /filter-options and zero main-query requests` |
| AC-1 | Unit (Vitest) | [frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts](../../../frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts) | `does not emit dropdown-close while dropdown is open across multiple toggles` |
| AC-2 | E2E (Playwright) | [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) | `dropdown close with changed selection fires exactly 1 /filter-options and 0 main-query` (close via outside-click, blur, Escape — parametrized) |
| AC-2 | Unit (node:test) | [frontend/tests/legacy/production-history.test.js](../../../frontend/tests/legacy/production-history.test.js) | `commitSelection() fires fetcher exactly once with debounce`, `setSelection() never calls fetcher` |
| AC-3 | E2E (Playwright) | [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) | `after first filter commits, opening a second filter still buffers toggles until close` |
| AC-4 | E2E (Playwright) | [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) | `no-op close (selection identical to pre-open) fires zero requests` |
| AC-4 | Unit (node:test) | [frontend/tests/legacy/production-history.test.js](../../../frontend/tests/legacy/production-history.test.js) | `commitSelection() with unchanged selection is a no-op` |
| AC-5 | Manual / visual reviewer | n/a (Tier-2 visual review) | covered by reviewer checklist; no automated test |
| AC-6 | E2E (Playwright) | [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) | `committed /filter-options request body retains existing payload schema (snapshot)` |
| Regression | Unit (Vitest) | [frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts](../../../frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts) | `still emits update:model-value on every toggle (back-compat for unlisted consumers)`, `consumers without @dropdown-close listener see no behavioral change` |

## Test Files (new or modified)

- **NEW** [frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts](../../../frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts) — Vitest + `@vue/test-utils` mount of `MultiSelect.vue`. Tests: `emits dropdown-close once on outside-click with final selection`, `emits dropdown-close once on Escape with final selection`, `emits dropdown-close once on blur with final selection`, `dropdown-close payload equals current model-value at close time`, `does not emit dropdown-close while dropdown is open across multiple toggles`, `still emits update:model-value on every toggle (back-compat for unlisted consumers)`, `consumers without @dropdown-close listener see no behavioral change` (8 other apps regression guard).
- **MODIFIED** [frontend/tests/legacy/production-history.test.js](../../../frontend/tests/legacy/production-history.test.js) — extend existing node:test suite. Add tests: `setSelection() updates buffer but does not call fetcher`, `setSelection() does not start debounce timer`, `commitSelection() fires fetcher exactly once with debounce`, `commitSelection() with unchanged selection is a no-op`, `commitSelection() reads from buffer (latest setSelection wins)`, `multiple setSelection followed by single commitSelection produces one fetcher call`.
- **MODIFIED** [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) — extend (do NOT replace existing assertions). Add tests: `multi-select inside same dropdown does not trigger filter-options until dropdown close` (AC-1), `dropdown close with changed selection fires exactly 1 /filter-options` parametrized over `outside-click | Escape | blur` (AC-2), `no-op close fires zero requests` (AC-4), `cross-filter then second filter still buffers toggles` (AC-3), `committed /filter-options request body retains existing payload schema (snapshot)` (AC-6), `查詢 button still required to trigger main query — dropdown close alone does not` (AC-2 refinement).

## Out of scope

- Visual diff vs Figma / CSS regression (AC-5 handled by visual reviewer; no new layer or token).
- Backend integration / contract tests (no payload, route, or schema change — AC-6).
- Stress / soak / monkey tiers (UI event-timing fix, not load-related).
- Cross-app regression for the 8 other `MultiSelect` consumers beyond the unit-level back-compat assertion (Tier-2 module-level scope; full app regression would belong to Tier-3+).
- Data-boundary tests (no new edge inputs — selection model unchanged).

## Test Tier Assignment

| Test family | Tier (pre-merge / nightly / weekly / manual) |
|---|---|
| Vitest unit (`MultiSelect.test.ts`) | pre-merge |
| node:test unit (`production-history.test.js`) | pre-merge |
| Playwright E2E (`production-history-cross-filter.spec.ts`) | pre-merge |
| Visual review (AC-5) | manual (reviewer checklist) |
