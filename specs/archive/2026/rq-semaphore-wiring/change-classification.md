# Change Classification: rq-semaphore-wiring

## Change Types
- primary: concurrency-hardening / business-logic-change (runtime concurrency policy)
- secondary: refactor (worker Oracle-call wrapping)

## Lane
- feature

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: Shared global semaphore acquisition across four independent production RQ worker code paths. Deadlock-avoidance and slot-leak-on-exception are non-obvious design decisions. ADR 0011 already governs this boundary; design must conform to it and document acquire-scope decision per worker.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Known: four workers unwired; captured in change-request |
| proposal.md | no | Behavior-internal hardening, no product/UX decision |
| spec.md | no | No new external contract or user-visible behavior |
| design.md | yes | Architecture Review Required; spec-architect must decide acquire-scope boundary, exception-release strategy, per-worker placement conforming to ADR 0011 |
| qa-report.md | no | Pass/fail in agent-log/qa-reviewer.yml; promote only if blocking finding |
| regression-report.md | no | Flag-off parity covered by integration tests |
| visual-review-report.md | no | No UI surface |
| monkey-test-report.md | no | No interactive UI flow |
| stress-soak-report.md | yes | Tier-1 concurrency; Oracle-connection-exhaustion risk; peak-cap + no-leak evidence required per CLAUDE.md §RQ Worker Concurrency Gate |

## Required Contracts
- API: none (no endpoint/response-shape change)
- CSS/UI: none
- Env: none (no new env var; read-only confirmation of no default change)
- Data shape: none (job result schemas unchanged)
- Business logic: candidate — may add rule codifying RQ Oracle-phase concurrency bound; contract-reviewer gates
- CI/CD: candidate — if stress/soak gate added; contract-reviewer gates

## Required Tests
- unit: per-worker acquire/release wiring assertions; slot released on success AND on exception; flag-off path unchanged
- integration: N=8 concurrent workers → peak ≤ MAX_CONCURRENT (3); all complete; no deadlock; no slot leak
- resilience: exception-during-Oracle-phase releases slot; subsequent job can acquire
- stress: high-concurrency burst sustains cap without leak or deadlock
- soak: prolonged dispatch confirms no slow permit leak (nightly lane)
- E2E: none
- data-boundary: none

## Required Agents
- spec-architect
- contract-reviewer
- test-strategist
- ci-cd-gatekeeper
- implementation-planner
- backend-engineer
- stress-soak-engineer
- qa-reviewer

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.4, 3.3, 3.4, 4.2, 4.3, 5.1, 5.2

## Inferred Acceptance Criteria
- AC-1: Under N=8 concurrently dispatched RQ workers spanning the four job types, peak simultaneous Oracle-phase executions is ≤ MAX_CONCURRENT (3) at all times.
- AC-2: All N dispatched jobs reach terminal state (complete) with no deadlock and no permanent stall.
- AC-3: After all jobs finish (success or failure), semaphore reports full availability (MAX_CONCURRENT permits free) — zero slot leak.
- AC-4: When Oracle phase raises an exception (or job times out), the acquired slot is released; a subsequent job can acquire it.
- AC-5: With the relevant feature flag OFF, each worker's behavior, job output, error handling, and progress_callback sequence are byte-for-byte identical to pre-change behavior.
- AC-6: Each of the four execute_*_job workers acquires the slot exactly once and only around the Oracle phase (context-managed, not job-global), per ADR 0011.
- AC-7: No new environment variable introduced and no env-contract default changes.

## Clarifications or Assumptions
- Assumption: Lane is `feature` (deliberate concurrency hardening), not `bug-fix` — no reported symptom; closes known wiring gap per CLAUDE.md + ADR 0011.
- Assumption: `acquire_heavy_query_slot()` is already a context manager; spec-architect must confirm and document the wrapping pattern if it is a bare acquire/release pair.
- CER-001 resolved: src/mes_dashboard/services/resource_query_job_service.py and reject_query_job_service.py both confirmed to exist.
- CER-002 resolved: src/mes_dashboard/core/heavy_query_telemetry.py exists; added to spec-architect allowed paths in case acquire boundary touches telemetry.
- Open question for design: should slot be acquired per-worker around only the Oracle call, or does any worker run multiple Oracle phases requiring re-acquisition? Drives AC-6; must be resolved before implementation.
