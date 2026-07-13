---
change-id: query-tool-subtab-cache
schema-version: 0.1.0
last-changed: 2026-07-09
---

# Implementation Plan: query-tool-subtab-cache

## Objective
Make query-tool sub-tab switching reuse already-fetched results instead of
re-querying Oracle on every revisit. Under one unchanged filter set, each of the
three sub-tabs (lots/jobs/rejects) queries at most once; changing any filter axis
(equipment ids / lot list / workcenter groups / date range) invalidates the cache
so the next sub-tab entry re-queries and never shows stale data. Pure client-side
change in the query-tool composables — no route, payload, or contract change.

## Execution Scope

### In Scope
- `useLotEquipmentQuery.ts`: add a skip-if-cached guard inside `setActiveSubTab()`.
- `useEquipmentQuery.ts`: add the same guard PLUS the missing invalidation wiring
  (this composable has no invalidation hook today).
- `useLotDetail.ts`: audit only — the `loaded.*` gate already implements the target
  pattern correctly; add a pinning regression test, no production change.
- Create/extend the unit tests per test-plan.md AC->test mapping.

### Out of Scope
- Any backend route, RQ worker, or API/response-shape change (queries hit the same
  endpoints, just fewer times). See change-classification.md `Required Contracts: none`.
- Any change to `useLotLineage.ts` / `useReverseLineage.ts` / `useLotResolve.ts` —
  no `setActiveSubTab` cache pattern there (test-plan.md Out of Scope).
- Any production-code change to `useLotDetail.ts` (AC-6 is audit-and-pin only).
- Refactoring `queryLots/queryJobs/queryRejects`, pagination, CSV export, or the
  `fetchEquipmentPeriod` async-polling path beyond what the guard/invalidation needs.
- Putting the guard inside `queryActiveSubTab()` or the `query*` functions — see
  Handoff Constraints (would break AC-5 explicit refresh and pagination).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `useLotEquipmentQuery.ts` `setActiveSubTab()` | Add cache-hit guard: after `activeSubTab.value = normalizeSubTab(tab)`, before the `queryActiveSubTab()` call, return early if the target tab is already cached. No new invalidation needed (already handled by `clearResults()`). | frontend-engineer |
| IP-2 | `useEquipmentQuery.ts` `setActiveSubTab()` + invalidation | Add the same guard, PLUS wire filter-change invalidation that resets `queried.{lots,jobs,rejects,timeline}` when equipment ids or date range change. | frontend-engineer |
| IP-3 | `useLotDetail.ts` | Audit only — confirm the existing `loaded.*` gate already satisfies the AC-6 pattern. No production edit. | frontend-engineer |
| IP-4 | query-tool unit tests | Create `useEquipmentQuery.test.js`; extend `useLotEquipmentQuery.test.js`; add one pinning test to `useLotDetail.pagination.test.js`, per test-plan.md AC->test mapping. | frontend-engineer (tests authored with test-strategist) |
| IP-5 | verification | Run vitest for the changed area + `vue-tsc --noEmit`, and the `cdd-kit test run` bounded ladder (collect/targeted/changed-area); record `test-evidence.yml`. | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7 | behavior the change must satisfy |
| change-classification.md | Required Contracts (all `none`) | confirms zero-contract scope |
| test-plan.md | Acceptance Criteria -> Test Mapping table | exact test file/name per AC |
| test-plan.md | Test Update Contract | which test files create vs update vs leave |
| test-plan.md | Test Execution Ladder + Notes (`npm run test -- query-tool`) | verification commands |
| ci-gates.md | Required Gates table | which gates must stay green (frontend-unit-tests, contract-and-fast-tests) |
| context-manifest.md | Allowed Paths | read/write boundary |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `frontend/src/query-tool/composables/useLotEquipmentQuery.ts` | edit | Guard in `setActiveSubTab()` (lines 366-372). After `activeSubTab.value = normalizeSubTab(tab)` and the `resolvedEquipmentIds.value.length > 0` check, return `true` early when `(queried as Record<string, boolean>)[activeSubTab.value]` is already `true`, skipping `queryActiveSubTab()`. Invalidation already exists: `clearResults()` (lines 162-175) resets every `queried.*` flag and is called by `lookupEquipment()` (line 188), which is the sole filter-change entry point. Do NOT touch `queryActiveSubTab()` (359-364) or the `query*` functions. |
| `frontend/src/query-tool/composables/useEquipmentQuery.ts` | edit | (a) Guard in `setActiveSubTab()` (lines 305-311): after `activeSubTab.value = normalizeSubTab(tab)` and the `autoQuery` short-circuit, return `true` early when `(queried as Record<string, boolean>)[activeSubTab.value]` is already `true`. (b) Add a private `invalidateQueryCache()` helper that sets `queried.lots = queried.jobs = queried.rejects = queried.timeline = false` (flags defined by `emptyTabFlags()`, lines 46-53). (c) Call it from `setSelectedEquipmentIds()` (lines 313-315) — equipment-id change. (d) Cover the raw `startDate`/`endDate` refs (lines 64-65): App.vue mutates them directly via `equipmentQuery.startDate.value = $event` / `endDate.value = $event` (App.vue lines 686-687) and `resetDateRange()` (lines 106-110) reassigns them — there is no function boundary, so add `watch([startDate, endDate], invalidateQueryCache, { flush: 'sync' })` inside the composable. `{ flush: 'sync' }` keeps invalidation deterministic for the unit tests (no `nextTick` needed). Do NOT touch `queryActiveSubTab()` (294-303) or `query*`. |
| `frontend/src/query-tool/composables/useLotDetail.ts` | read only | Confirm no change: `loadHistory()` gates on `if (!force && loaded.history) return true` (line 252) and `loadAssociation()` has the equivalent gate; `setSelectedContainerId(s)`/`setSelectedWorkcenterGroups` already reset `loaded.*`/call `clearTabData()`. AC-6 = pinning test only. |
| `frontend/src/query-tool/App.vue` | read only | Call-site verification done — no edit required. Sub-tab switches route through `setActiveSubTab` (lines 419, 435) where the guard lives; explicit refresh/search uses `queryActiveSubTab()`/`lookupEquipment()` (lines 423, 431) and pagination uses `queryLots({page})` (lines 443, 691), all of which bypass the guard and therefore still force a fresh query. This is why the guard must live ONLY in `setActiveSubTab`. |
| `frontend/tests/query-tool/useEquipmentQuery.test.js` | create | Mirror `useLotEquipmentQuery.test.js`'s `setupWindowMesApi` + vitest describe/it pattern. Cover AC-1, AC-2, AC-3, AC-4, AC-5, AC-7 test names from test-plan.md. |
| `frontend/tests/query-tool/useLotEquipmentQuery.test.js` | edit | Add cache-hit / invalidation / refresh / cache-signal cases (AC-1, AC-2, AC-3, AC-4, AC-5, AC-7 rows) alongside the existing 4 regression tests. Do not remove existing assertions. |
| `frontend/tests/query-tool/useLotDetail.pagination.test.js` | edit | Add one pinning regression test for AC-6 (revisiting an already-loaded sub-tab issues no new lot-associations/lot-history POST). |
| `frontend/tests/legacy/query-tool-composables.test.js` | none | No edit — per test-plan.md Test Update Contract it encodes no always-requery assertion. Must stay green. |

## Contract Updates
- API: none
- CSS/UI: none
- Env: none
- Data shape: none (cached payloads are the existing response shapes)
- Business logic: none
- CI/CD: none

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | frontend/tests/query-tool/useLotEquipmentQuery.test.js | same-filter sub-tab revisit issues no new equipment-period POST |
| AC-1 | frontend/tests/query-tool/useEquipmentQuery.test.js | setActiveSubTab skips re-query when target tab already queried under current filters |
| AC-2 | frontend/tests/query-tool/useLotEquipmentQuery.test.js | lots->jobs->rejects->lots issues exactly one call per query_type |
| AC-2 | frontend/tests/query-tool/useEquipmentQuery.test.js | lots->jobs->rejects->lots issues exactly one call per query_type |
| AC-3 | frontend/tests/query-tool/useEquipmentQuery.test.js | changing selectedEquipmentIds resets queried.lots/jobs/rejects |
| AC-3 | frontend/tests/query-tool/useEquipmentQuery.test.js | changing startDate or endDate resets queried.lots/jobs/rejects |
| AC-3 | frontend/tests/query-tool/useLotEquipmentQuery.test.js | re-running lookupEquipment with changed inputs resets queried.* before auto-query |
| AC-4 | frontend/tests/query-tool/useEquipmentQuery.test.js | post-filter-change sub-tab entry re-queries and replaces cached rows |
| AC-4 | frontend/tests/query-tool/useLotEquipmentQuery.test.js | post-re-lookup sub-tab entry re-queries and replaces cached rows |
| AC-5 | frontend/tests/query-tool/useEquipmentQuery.test.js | explicit refresh re-queries active sub-tab even when queried flag unchanged |
| AC-5 | frontend/tests/query-tool/useLotEquipmentQuery.test.js | explicit refresh re-queries active sub-tab even when queried flag unchanged |
| AC-6 | frontend/tests/query-tool/useLotDetail.pagination.test.js | revisiting an already-loaded sub-tab issues no new lot-associations/lot-history POST (pins existing loaded.* gate) |
| AC-7 | frontend/tests/query-tool/useEquipmentQuery.test.js | forcing queried.<tab>=false directly makes the next setActiveSubTab re-query |
| AC-7 | frontend/tests/query-tool/useLotEquipmentQuery.test.js | forcing queried.<tab>=false directly makes the next setActiveSubTab re-query |

Local run commands (from `frontend/`): `npx vitest run tests/query-tool tests/legacy/query-tool-composables.test.js` and `vue-tsc --noEmit` (type-check is informational per ci-gates.md but must not regress the three touched composables). Required test phases: `collect`, `targeted`, `changed-area` (test-plan.md Test Execution Ladder). Generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. This is frontend-only (no cross-stack race on `test-evidence.yml`).

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- The guard MUST live only in `setActiveSubTab()`. Never add it to `queryActiveSubTab()`
  or the `query*` functions — those are the explicit-refresh (AC-5) and pagination paths
  and must always force a fresh query.
- `queried.{lots,jobs,rejects}` (and `timeline` for `useEquipmentQuery`) are the sole
  cache-hit signal (AC-7); invalidation must reset them in lockstep, never leaving a
  stale-true flag after a filter change (AC-3/AC-4 correctness risk).
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan;
  follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks
- Stale-data-after-filter-change (AC-3/AC-4) is the primary correctness risk. For
  `useEquipmentQuery`, the date refs are mutated directly by the App.vue template with no
  setter boundary — the `watch([startDate, endDate], ...)` is the invalidation seam for
  that axis; if the watch is omitted or its flush timing is wrong, date-range changes will
  silently serve stale cached rows. Use `{ flush: 'sync' }` so the reset is observable
  without `nextTick` and lands before the next `setActiveSubTab`.
- `emptyTabFlags()` includes a `timeline` flag consumed by `queryTimeline()`; invalidation
  must reset `timeline` too so the timeline view does not serve stale data after a filter change.
- `useLotDetail.ts` is intentionally left unchanged (AC-6 audit-and-pin). Do not
  opportunistically "align" its pattern — the pinning test exists to catch future regression,
  not to drive a change now.
- `.cdd/code-map.yml` shows as modified in git status; the line ranges cited above were
  re-verified against current source, so they are authoritative regardless of map staleness.
