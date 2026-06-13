# Change Classification

## Change Types
- primary: ui-only-change, feature-enhancement
- secondary: frontend-type-change (data-shape), business-logic-change (backend pct milestone instrumentation)

## Lane
- feature

## Risk Summary
Pure UI/UX enhancement extracting an existing inline progress-bar pattern (reject-history) into a shared `AsyncQueryProgress.vue` component, wiring it into two existing consumers (yield-alert-center, production-history), tightening composable types (`pct`/`stage` in `JobStatusResponse`), and adding `pct` milestone values (0/30/100) at existing `update_job_progress()` call sites in two job services.

Low risk: no new API endpoints, no Redis schema change, no DB migration, no auth, no production data write path, no concurrency change. Backend change is additive instrumentation only. Main risk vectors are (1) CSS bleed if the new `.async-job-progress` base class is not authored correctly outside `theme-*` scope, (2) type-safety regression in a shared composable consumed beyond the two named consumers, and (3) visual/interaction correctness of the progress bar and cancel button. All are caught by `npm run css:check`, `vue-tsc --noEmit`, Vitest, and visual/UX review.

## Risk Level
- low

## Impact Radius
- module-level

## Tier
- 3

## Architecture Review Required
- no
- reason: (n/a — extracting an existing inline HTML/CSS pattern into a shared component; no new module boundary, data-flow, migration, or operational-risk decision.)

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Existing reference (reject-history inline bar) captured in change-request Known Context. |
| proposal.md | no | Scope is concrete and pre-decided. |
| spec.md | no | No new user-facing behavior decision beyond the change-request. |
| design.md | no | No architecture review required. |
| qa-report.md | no | Routine pass/fail goes in agent-log/qa-reviewer.yml. |
| regression-report.md | no | No existing behavior being changed in a risky way. |
| visual-review-report.md | no | Visual evidence goes in agent-log/visual-reviewer.yml. |
| monkey-test-report.md | no | Not warranted for a scoped progress component. |
| stress-soak-report.md | no | No high-load/long-running/queue behavior change. |

## Required Contracts
- API: none (no new endpoint; Redis schema unchanged; api-contract.md reviewed for no-change confirmation)
- CSS/UI: contracts/css/css-contract.md (new `.async-job-progress` base class; must NOT depend on `theme-*` scope) and contracts/css/css-inventory.md (register new authored CSS source)
- Env: none
- Data shape: contracts/data/data-shape-contract.md (add `pct`/`stage` fields to `JobStatusResponse`)
- Business logic: pct milestone semantics (0/30/100) at existing `update_job_progress()` call sites — additive; no contract document change expected; contract-reviewer to confirm
- CI/CD: none (using existing frontend-tests.yml, backend-tests.yml, contract-driven-gates.yml)

## Required Tests
- unit: Vitest unit tests for `AsyncQueryProgress.vue` (renders pct/percentage, elapsed-seconds, cancel-button emits cancel event, edge values 0/30/100); composable type-level coverage for `pct`/`stage` on `JobStatusResponse`
- contract: data-shape assertion that `JobStatusResponse` includes typed `pct`/`stage`; CSS contract compliance via `npm run css:check`; css-inventory entry present
- integration: yield-alert-center/App.vue and production-history (useProductionHistory.ts) wire `AsyncQueryProgress` to existing `jobProgress` state; backend pct milestone tests asserting `update_job_progress()` is called with `pct` 0/30/100 in both job services
- E2E: skip (unit + integration + visual review sufficient; add only if consumer flow regression appears)
- visual: progress bar rendering, percentage label, elapsed-seconds, cancel button states across both consumers
- data-boundary: n/a
- resilience: n/a
- fuzz/monkey: n/a
- stress: n/a
- soak: n/a

## Required Agents
- contract-reviewer (CSS contract for `.async-job-progress`, css-inventory update, data-shape contract for `pct`/`stage`, confirm api-contract unchanged)
- test-strategist (plan Vitest unit tests for component + integration tests for both consumers + backend pct milestone tests)
- ci-cd-gatekeeper (frontend-tests gate, backend-tests gate, css:check gate, vue-tsc type-check gate)
- implementation-planner (writes implementation-plan.md)
- frontend-engineer (implement AsyncQueryProgress.vue, fix useAsyncJobPolling.ts types, wire yield-alert-center + production-history)
- backend-engineer (add pct milestones 0/30/100 to yield_alert_job_service.py and production_history_job_service.py)
- ui-ux-reviewer (component interaction design: cancel affordance, progress/elapsed clarity, accessibility)
- visual-reviewer (progress bar rendering across both consumers)
- qa-reviewer (final release readiness)

## Inferred Acceptance Criteria
- AC-1: A new `frontend/src/shared-ui/components/AsyncQueryProgress.vue` exists that renders an inline progress bar, a percentage value, elapsed-waited seconds, and a cancel button, and emits a cancel event when the cancel button is activated.
- AC-2: `useAsyncJobPolling.ts` `JobStatusResponse` declares typed `pct` and `stage` fields, eliminating the `unknown` cast; `vue-tsc --noEmit` passes with no new type errors.
- AC-3: `yield-alert-center/App.vue` renders `AsyncQueryProgress` bound to its existing `jobProgress` state during a slow query, showing pct, elapsed seconds, and a working cancel control.
- AC-4: `production-history/App.vue` (via `useProductionHistory.ts`) renders `AsyncQueryProgress` bound to its collected `jobProgress`, showing pct, elapsed seconds, and a working cancel control.
- AC-5: `yield_alert_job_service.py` and `production_history_job_service.py` call `update_job_progress()` with `pct` milestone values of 0, 30, and 100 at the existing call sites, with no Redis schema change.
- AC-6: The component's `.async-job-progress` base class is authored without dependence on any `theme-*` scope, is registered in `contracts/css/css-inventory.md`, and `npm run css:check` passes.
- AC-7: reject-history's existing `.async-job-status-bar` progress implementation (App.vue:1478-1486) is left unchanged.

## Tasks Not Applicable
- not-applicable: 1.3 (design.md / architecture review — not required), 2.1 (API contract — no-change confirmed; reviewed by contract-reviewer), 2.3 (Env contract — no new env vars), 2.6 (CI/CD contract — no gate definition change), 3.3 (E2E — not required for this enhancement), 3.4 (data-boundary/monkey — n/a), 3.5 (stress/soak — n/a), 4.3 (Env/deploy — no new env vars)

## Clarifications or Assumptions
- Assumption: backend pct milestone change is purely additive and does not require a new entry in contracts/business/business-rules.md; contract-reviewer should confirm.
- Assumption: no E2E spec required; unit + integration + visual review sufficient.
- Assumption: new component CSS source must be built (`npm run build`) for dist hashing per project CSS-patterns guidance.
- CER-001 RESOLVED: backend test path confirmed as `tests/` (root) — project-map shows `tests/test_async_query_job_service.py` at that level.

## Context Manifest Draft

### Affected Surfaces
- frontend-components (new shared `AsyncQueryProgress.vue`)
- frontend-composables (`useAsyncJobPolling.ts` type fix; `useProductionHistory.ts` wiring)
- frontend-consumers (`yield-alert-center/App.vue`, `production-history/App.vue`)
- backend-services (`yield_alert_job_service.py`, `production_history_job_service.py` pct milestones)

### Allowed Paths
- specs/changes/async-progress-ui/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/yield-alert-center/
- frontend/src/production-history/
- frontend/src/reject-history/
- frontend/tests/components/
- frontend/tests/shared-composables/
- src/mes_dashboard/services/
- tests/
- contracts/css/
- contracts/data/
- contracts/api/
- .github/workflows/

### Required Contracts
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/api/api-contract.md (no-change confirmation only)

### Required Tests
- frontend/tests/components/ (new AsyncQueryProgress.vue unit tests)
- frontend/tests/shared-composables/useAsyncJobPolling.test.js (extend for pct/stage types)
- tests/ (backend pct-milestone tests for the two job services)

### Agent Work Packets

#### contract-reviewer
- specs/changes/async-progress-ui/
- contracts/css/
- contracts/data/
- contracts/api/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/

#### test-strategist
- specs/changes/async-progress-ui/
- frontend/tests/components/
- frontend/tests/shared-composables/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/

#### ci-cd-gatekeeper
- specs/changes/async-progress-ui/
- .github/workflows/

#### implementation-planner
- specs/changes/async-progress-ui/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### frontend-engineer
- specs/changes/async-progress-ui/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/yield-alert-center/
- frontend/src/production-history/
- frontend/src/reject-history/
- frontend/tests/components/
- frontend/tests/shared-composables/
- contracts/css/

#### backend-engineer
- specs/changes/async-progress-ui/
- src/mes_dashboard/services/
- tests/

#### ui-ux-reviewer
- specs/changes/async-progress-ui/
- frontend/src/shared-ui/components/
- frontend/src/yield-alert-center/
- frontend/src/production-history/

#### visual-reviewer
- specs/changes/async-progress-ui/
- frontend/src/shared-ui/components/
- frontend/src/yield-alert-center/
- frontend/src/production-history/

#### qa-reviewer
- specs/changes/async-progress-ui/

### Context Expansion Requests
-
