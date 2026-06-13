# Archive — async-progress-ui

## Change Summary

Phase 1 of the dynamic-RQ migration plan: extracted an existing inline
progress-bar pattern (reject-history) into a new shared
`AsyncQueryProgress.vue` component and wired it into two async-job consumers
(yield-alert-center, production-history). Simultaneously tightened the
`JobStatusResponse` TypeScript interface with optional `pct` and `stage`
fields, and added canonical pct milestone values (0 = start, 30 = querying
Oracle, 100 = complete) at the existing `update_job_progress()` call sites in
`yield_alert_job_service.py` and `production_history_job_service.py`. All
backend changes are purely additive instrumentation with no Redis schema or DB
migration.

## Final Behavior

- Both yield-alert-center and production-history now render a shared inline
  progress bar with a percentage label, elapsed-seconds display, and a cancel
  button during slow async queries.
- Cancel dismisses the bar synchronously (sets `jobProgress.active = false` +
  `loading.value = false` immediately on click, before the abort resolves).
- Failed-state is visually distinct from the running state (red fill, spinner
  hidden, error icon).
- Backend job services emit pct 0/30/100 so polling consumers can render
  coarse progress without any new Redis key or data-shape change.

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| `contracts/css/css-contract.md` | 1.7.0 → 1.8.0 | AsyncQueryProgress.vue row added to Component Rules table |
| `contracts/css/css-inventory.md` | 1.2.4 → 1.2.5 | AsyncQueryProgress.vue added to Shared UI Component Styles |
| `contracts/data/data-shape-contract.md` | 1.13.0 → 1.14.0 | §1.4 pct?/stage? optional fields + constraint notes |
| `contracts/api/api-contract.md` | 1.15.0 → 1.16.0 | §10 compatibility note: pct/stage additive optional fields |
| `contracts/business/business-rules.md` | 1.17.0 → 1.18.0 | ASYNC-05 pct milestone semantics rule (0/30/100) |

## Final Tests Added / Updated

Backend (pytest):
- `tests/test_yield_alert_job_service.py` — 3 new: pct=0 at start, pct=30 after query, pct=100 before complete
- `tests/test_production_history_job_service.py` — 3 new: same three milestones

Frontend (Vitest):
- `frontend/tests/components/AsyncQueryProgress.test.js` — 13 new tests (render, props, cancel emit, failed-state)
- `frontend/tests/shared-composables/useAsyncJobPolling.test.js` — 2 new: `pct` and `stage` field forwarding

## Final CI/CD Gates

5 Tier-1 required gates (all green on CI): `frontend-unit-tests`, `type-check`,
`css-governance`, `backend-unit-tests`, `cdd-gate`. Full-backend suite
(Tier-2 informational) also green. No nightly/weekly gates applicable.

## Production Reality Findings

- **B-1 (resolved)**: Initial implementation left cancel dismissal to the
  `finally` block — bar remained visible during abort. Fixed: both consumers
  now synchronously clear `jobProgress.active` and `loading.value` on cancel.
- **B-2 (resolved)**: `:status` prop was omitted in both consumers; failed-state
  was visually indistinguishable from running. Fixed: prop passed + red-fill
  branch added to component.
- **Prop naming drift**: css-contract Component Rules table uses the term `stage`
  for the label prop; implementation uses `progress: string`. Functionally
  equivalent; no runtime impact. Resolved below in Lessons Promoted.

## Lessons Promoted to Standards

1. **css-contract Component Rules `progress` prop wording** — corrected
   `stage` → `progress` in `contracts/css/css-contract.md` AsyncQueryProgress
   row to match the live SFC prop name. Evidence: visual-reviewer advisory +
   qa-reviewer advisory.

## Follow-up Work

- A-1 (advisory, deferred): `elapsedSeconds` is hardwired to 0 in both
  consumers; no timer is started on `jobProgress.active` becoming true. A
  future change should wire a real interval timer (per Phase 2 of the
  dynamic-RQ migration plan).
- Phase 2 of dynamic-RQ migration plan: typed job-status state machine +
  further consumer migrations.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance.
