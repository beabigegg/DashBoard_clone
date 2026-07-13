---
change-id: query-tool-subtab-cache
schema-version: 0.1.0
last-changed: 2026-07-09
risk: low
tier: 3
---

# Test Plan: query-tool-subtab-cache

## Code-map grounding

`useLotEquipmentQuery.ts` (469 lines) and `useEquipmentQuery.ts` (422 lines) both
expose `queried.{lots,jobs,rejects}` reactive flags, `queryActiveSubTab()`, and
`setActiveSubTab()` — the two call sites the fix must guard. `useLotEquipmentQuery`
already funnels every filter change (input values/workcenter groups) through
`lookupEquipment()` → `clearResults()`, which resets `queried.*`; its only gap is
the missing skip-if-cached check inside `setActiveSubTab`. `useEquipmentQuery`
exposes `startDate`/`endDate` as raw refs and `setSelectedEquipmentIds()` with no
existing invalidation hook — both the skip-check and the invalidation trigger are
missing there. `useLotDetail.ts` (594 lines) already implements this exact pattern
correctly (`loaded.*` flags gate `loadHistory`/`loadAssociation`; `setSelectedContainerId(s)`/
`setSelectedWorkcenterGroups` call `clearTabData()` or reset `loaded.history`) —
AC-6 is an audit-and-pin, not a fix.

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | frontend/tests/query-tool/useLotEquipmentQuery.test.js::"setActiveSubTab reuses cached lots rows without a new equipment-period POST on same-filter revisit" | 3 |
| AC-1 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"setActiveSubTab skips re-query when target sub-tab already queried under current filters" | 3 |
| AC-2 | unit | frontend/tests/query-tool/useLotEquipmentQuery.test.js::"cycling lots→jobs→rejects→lots issues exactly one equipment-period call per query_type" | 3 |
| AC-2 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"cycling lots→jobs→rejects→lots issues exactly one equipment-period call per query_type" | 3 |
| AC-3 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"changing selectedEquipmentIds invalidates queried.lots/jobs/rejects" | 3 |
| AC-3 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"changing startDate or endDate invalidates queried.lots/jobs/rejects" | 3 |
| AC-3 | unit | frontend/tests/query-tool/useLotEquipmentQuery.test.js::"re-running lookupEquipment with a changed input/workcenter-group set resets queried.* before auto-query" | 3 |
| AC-4 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"entering a sub-tab after a filter change re-queries and replaces previously cached rows, never showing pre-change data" | 3 |
| AC-4 | unit | frontend/tests/query-tool/useLotEquipmentQuery.test.js::"entering a sub-tab after re-lookup re-queries and replaces previously cached rows" | 3 |
| AC-5 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"explicit refresh re-queries the active sub-tab even when filters and queried flag are unchanged" | 3 |
| AC-5 | unit | frontend/tests/query-tool/useLotEquipmentQuery.test.js::"explicit refresh re-queries the active sub-tab even when filters and queried flag are unchanged" | 3 |
| AC-6 | unit | frontend/tests/query-tool/useLotDetail.pagination.test.js::"revisiting an already-loaded sub-tab issues no new lot-associations/lot-history POST (pins existing loaded.* gate as audit evidence)" | 3 |
| AC-7 | unit | frontend/tests/query-tool/useEquipmentQuery.test.js::"queried.lots/jobs/rejects are the sole cache-hit signal: forcing queried.<tab>=false directly causes the next setActiveSubTab to re-query" | 3 |
| AC-7 | unit | frontend/tests/query-tool/useLotEquipmentQuery.test.js::"queried.lots/jobs/rejects are the sole cache-hit signal: forcing queried.<tab>=false directly causes the next setActiveSubTab to re-query" | 3 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 3 | All coverage lives at composable-unit level; mock boundary is the `window.MesApi.get/post` bridge (network boundary), per existing sibling-test convention (`setupWindowMesApi`) — no internal class/module mocking. |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

The approved place to record that an existing test must change because the
accepted spec or contract changed. This is not a waiver: a still-valid test that
fails must be fixed, not relisted here.

| existing test | action | reason |
|---|---|---|
| frontend/tests/legacy/query-tool-composables.test.js | none (reused, no edits) | checked line-by-line: its `useEquipmentQuery` case never calls `setActiveSubTab` twice under identical filters, and its two `useLotDetail.setActiveSubTab` calls target previously-unqueried tabs — no assertion encodes the old always-requery behavior |
| frontend/tests/query-tool/useLotEquipmentQuery.test.js | update | add new cache-hit/invalidation/refresh cases alongside the existing 4 regression tests; no existing assertion contradicts skip-on-cache-hit |
| frontend/tests/query-tool/useEquipmentQuery.test.js | create | file does not yet exist; net-new coverage for AC-1..AC-5, AC-7 |
| frontend/tests/query-tool/useLotDetail.pagination.test.js | update | add one pinning regression test for AC-6 (existing `loaded.*` gate) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Contract, integration, E2E, visual, data-boundary, resilience, monkey, stress, soak — none required per change-classification.md (Required Tests: unit only; optional E2E strengthening explicitly not required).
- `useLotLineage.ts` / `useReverseLineage.ts` / `useLotResolve.ts` — not in Affected Surfaces; no `setActiveSubTab` cache pattern present.
- Backend routes/workers, RQ job payload shape — unchanged; no new server-side test needed.

## Notes

- AC-6: `useLotDetail.ts` already gates on `loaded.*` and invalidates via `clearTabData()`/`loaded.history = false` on every container/workcenter-group change — the required test is a pinning regression test, not a bug-fix-driven test.
- `frontend/tests/query-tool/useEquipmentQuery.test.js` does not exist yet; create it mirroring `useLotEquipmentQuery.test.js`'s `setupWindowMesApi` + vitest describe/it style.
- Run command: `cd frontend && npm run test -- query-tool`
