---
change-id: async-progress-ui
schema-version: 0.1.0
last-changed: 2026-06-13
---

# Implementation Plan: async-progress-ui

## Objective
Extract the existing inline async-job progress pattern into a shared
`AsyncQueryProgress.vue` component, wire it into the yield-alert-center and
production-history consumers, type the `pct`/`stage` fields on
`JobStatusResponse`, and add `pct` milestones (0/30/100) at the existing
`update_job_progress()` call sites of two job services. Additive enhancement;
no API endpoints, no env vars, no Redis schema change.

## Execution Scope

### In Scope
- New shared component `frontend/src/shared-ui/components/AsyncQueryProgress.vue`
  (inline blue bar, NOT a modal; props/emits per `## File-Level Plan`; `<style
  scoped>` `.async-job-progress` base class, no `theme-*` ancestor).
- Type fix: add `pct?: number` and `stage?: string` to `JobStatusResponse` in
  `frontend/src/shared-composables/useAsyncJobPolling.ts` (additive only).
- Consumer wiring in `yield-alert-center/App.vue` and `production-history/App.vue`
  (mount component bound to existing `jobProgress` state, `@cancel` to existing
  cancel/abort logic).
- Backend pct milestones 0/30/100 at the existing `update_job_progress()` call
  sites in `yield_alert_job_service.py` (`execute_yield_alert_job`, lines 93-151)
  and `production_history_job_service.py` (`execute_production_history_job`,
  lines 93-138).
- New frontend component tests + extended composable tests + extended backend
  service tests per `test-plan.md`.
- Verify the existing `contracts/css/css-inventory.md` entry (line 52) matches
  the new file path.

### Out of Scope
- Do NOT touch reject-history (`frontend/src/reject-history/App.vue`, including
  the reference `.async-job-status-bar` at lines 1478-1486). It is a read-only
  reference for the new component.
- Do NOT touch downtime-analysis, hold-history, job-registry, or any other
  feature/service.
- Do NOT change `jobProgress` state shape, polling logic, Redis schema, or add
  any API endpoint or env var.
- Do NOT add the downtime/hold-history RQ migration (phase 3) or a job registry
  (phase 2).
- No E2E / Playwright, integration-against-real-infra, visual-snapshot, stress,
  or soak tests (see `test-plan.md` Out of Scope).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend service | Add `pct=0` (start), `pct=30` (after Oracle query), `pct=100` (before `complete_job()`) at existing `update_job_progress()` call sites in `execute_yield_alert_job` (`yield_alert_job_service.py` 93-151). No new imports/functions/Redis change. | backend-engineer |
| IP-2 | backend service | Same milestone additions in `execute_production_history_job` (`production_history_job_service.py` 93-138). | backend-engineer |
| IP-3 | backend tests | Extend `tests/test_yield_alert_job_service.py::TestExecuteYieldAlertJob` and `tests/test_production_history_job_service.py::TestExecuteProductionHistoryJob` with pct-milestone assertions (per-kwarg `call_args.kwargs['pct']`). | backend-engineer |
| IP-4 | frontend component | Create `AsyncQueryProgress.vue` per props/emits/CSS spec below; reference reject-history `App.vue:1478-1486` for visual pattern only. | frontend-engineer |
| IP-5 | frontend composable | Add `pct?: number`, `stage?: string` to `JobStatusResponse` in `useAsyncJobPolling.ts` (104 lines). | frontend-engineer |
| IP-6 | frontend consumer | Mount `<AsyncQueryProgress>` in `yield-alert-center/App.vue` bound to existing `jobProgress` state (lines 61-68); wire `@cancel` to existing cancel/abort logic. No state/polling change. | frontend-engineer |
| IP-7 | frontend consumer | Mount `<AsyncQueryProgress>` in `production-history/App.vue` bound to `jobProgress` from `useProductionHistory.ts`; wire `@cancel` to `cancelJob()` (expose from composable if not yet exposed — additive only). | frontend-engineer |
| IP-8 | frontend tests | Create `frontend/tests/components/AsyncQueryProgress.test.js`; extend `frontend/tests/shared-composables/useAsyncJobPolling.test.js` per `test-plan.md`. | frontend-engineer |
| IP-9 | css governance | Confirm `contracts/css/css-inventory.md` entry (line 52) path matches the created file; ensure `npm run css:check` passes. | frontend-engineer |
| IP-10 | build | Run `npm run build` after frontend CSS source changes (dist hashing — orphaned stale named files otherwise). | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC→test mapping table; "Test Names" sections | exact test files/names to write |
| test-plan.md | Test Update Contract table | which existing backend tests to extend |
| test-plan.md | Notes (per-kwarg assertions; AC-7 import guard) | test-discipline constraints |
| ci-gates.md | Required Gates table + Promotion Policy | verification commands / merge readiness |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7 | acceptance mapping |
| contracts/css/css-contract.md | `<style scoped>`, `.async-job-progress` base class, rule 4.4 Teleport | component CSS constraint |
| contracts/css/css-inventory.md | line 52 entry | css-inventory verification |
| contracts/data/data-shape-contract.md §1.4 | optional `pct?: number`, `stage?: string` | composable type fix |
| contracts/business/business-rules.md §ASYNC-05 | milestone map 0/30/100 | backend milestone semantics (additive; no doc edit expected — contract-reviewer confirms) |
| contracts/api/api-contract.md | no-change confirmation only | scope guard |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `frontend/src/shared-ui/components/AsyncQueryProgress.vue` | create | Props: `active: boolean`, `progress: string`, `pct: number`, `elapsedSeconds: number`, `canCancel?: boolean` (default true), `status?: string \| null`. Emits: `cancel`. Renders inline blue bar (not modal), LoadingSpinner sm, progress text, percentage label, elapsed-waited seconds, cancel button. `<style scoped>` `.async-job-progress`, no `theme-*` ancestor; include reduced-motion fallback per css-inventory entry. |
| `frontend/src/shared-composables/useAsyncJobPolling.ts` | modify | Add `pct?: number`, `stage?: string` to `JobStatusResponse`. Existing consumers ignore unknown fields. No polling logic change. |
| `frontend/src/yield-alert-center/App.vue` | modify | Import + mount `<AsyncQueryProgress>` bound to existing `jobProgress` (lines 61-68); `@cancel` to existing cancel/abort. Do not change state shape or polling. |
| `frontend/src/production-history/App.vue` | modify | Import + mount `<AsyncQueryProgress>` bound to `jobProgress` from `useProductionHistory.ts`; `@cancel` to `cancelJob()`. |
| `frontend/src/production-history/composables/useProductionHistory.ts` | modify (only if needed) | Expose `cancelJob()` if not already exposed; additive only, no polling change. |
| `frontend/src/reject-history/App.vue` | read-only | Reference pattern (1478-1486). MUST NOT be modified. |
| `src/mes_dashboard/services/yield_alert_job_service.py` | modify | pct 0/30/100 at existing `update_job_progress()` sites in `execute_yield_alert_job` (93-151). |
| `src/mes_dashboard/services/production_history_job_service.py` | modify | pct 0/30/100 in `execute_production_history_job` (93-138). |
| `frontend/tests/components/AsyncQueryProgress.test.js` | create | Tests per test-plan.md (names listed there). |
| `frontend/tests/shared-composables/useAsyncJobPolling.test.js` | modify | Add pct/stage field-forwarding tests. |
| `tests/test_yield_alert_job_service.py` | modify | Extend `TestExecuteYieldAlertJob` with 3 pct-milestone tests. |
| `tests/test_production_history_job_service.py` | modify | Extend `TestExecuteProductionHistoryJob` with 3 pct-milestone tests. |

## Contract Updates

- API: none. `contracts/api/api-contract.md` reviewed for no-change confirmation only (no new endpoint, Redis schema unchanged).
- CSS/UI: `contracts/css/css-contract.md` governs `<style scoped>` + `.async-job-progress` base class with no `theme-*` dependence (rule 4.4 Teleport). `contracts/css/css-inventory.md` entry already present (line 52) — verify path match only; no new contract edit expected.
- Env: none.
- Data shape: `contracts/data/data-shape-contract.md §1.4` already declares optional `pct`/`stage`; the frontend type fix must match it. No contract edit expected.
- Business logic: pct milestone semantics covered by `contracts/business/business-rules.md §ASYNC-05` (0/30/100); additive — no doc change expected; contract-reviewer confirms.
- CI/CD: none (existing `frontend-tests.yml`, `backend-tests.yml`, `contract-driven-gates.yml`; existing path filters trigger all required gates).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1, AC-3, AC-4, AC-6, AC-7 | `frontend/tests/components/AsyncQueryProgress.test.js` | renders bar/pct/elapsed/cancel; emits cancel; no `theme-*` class; no reject-history import |
| AC-2 | `frontend/tests/shared-composables/useAsyncJobPolling.test.js` | pct/stage fields forwarded; `npm run type-check` (vue-tsc --noEmit) green |
| AC-5 | `tests/test_yield_alert_job_service.py` · `tests/test_production_history_job_service.py` | `update_job_progress()` called with pct 0/30/100 (per-kwarg assertions) |
| AC-6 (CSS governance) | `npm run css:check` | no unscoped bleed; css-inventory entry present |

Required test phases: `collect`, `targeted`, `changed-area` (floor), plus
`contract` and `quality` (CSS-governance + data/CSS contracts are touched).
Implementation agents generate evidence via `cdd-kit test run`; the gate
validates `test-evidence.yml`. Full ladder lives in `test-plan.md` /
`references/sdd-tdd-policy.md` — not restated here.

TDD note: backend pct-milestone tests written alongside the service edits;
frontend `AsyncQueryProgress.test.js` written before/alongside the component
(red→green); composable type tests extend the existing file.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- reject-history is reference-only and MUST remain byte-unchanged (AC-7).
- No new API endpoint, no env var, no Redis schema change, no `jobProgress` state-shape or polling-logic change.
- Run `npm run build` after frontend CSS source changes (dist hashing).
- Execution order: backend (IP-1..IP-3) first or in parallel; then frontend (IP-4..IP-10). Both may run sequentially or concurrently while frontend scaffolds the component.

## Known Risks

- CSS bleed if `.async-job-progress` is authored outside `<style scoped>` or made dependent on a `theme-*` ancestor — caught by `npm run css:check` (AC-6).
- Type-safety regression in the shared `useAsyncJobPolling.ts` consumed beyond the two named consumers; additive optional fields mitigate — caught by `npm run type-check` (AC-2). Note: the `type-check` step has `continue-on-error: true` in the workflow, but per ci-gates.md it must be green before merge regardless.
- Accidental modification of the reject-history reference (AC-7 regression) — guard by import-absence test and leaving the file untouched.
- `useProductionHistory.ts` may not yet expose `cancelJob()`; expose additively only — do not refactor polling.
- code-map.yml verified current (generated 2026-06-13 by cdd-kit 3.1.0); line pointers above are accurate as of that map.
