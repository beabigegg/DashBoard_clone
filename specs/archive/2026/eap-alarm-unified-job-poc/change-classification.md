# Change Classification

## Change Types
- primary: refactor (async worker → `BaseChunkedDuckDBJob` inheritance), business-logic-change (job enqueue routing / `sync_fallback_allowed` semantics)
- secondary: env-change (new `EAP_ALARM_USE_UNIFIED_JOB` feature flag var), performance (chunk parallelism)

## Lane
- feature

## Risk Level
- high

## Impact Radius
- cross-module

Rationale: This is the first-in-class POC for a new shared base class (`BaseChunkedDuckDBJob`) whose correctness gates all later domain migrations (P2+). It introduces concurrency (ThreadPoolExecutor against Oracle), rewires the job enqueue registry (`job_registry` / `async_query_job_service`) that multiple domains share, and changes always-async fallback behavior. The blast radius reaches the shared async-job plane even though only eap_alarm flips on.

## Tier
- 1

## Architecture Review Required
- yes
- reason: First concrete implementation of the `BaseChunkedDuckDBJob` template-method base class in a real domain. Non-obvious design decisions require a design record before implementation: (1) the template-method contract eap_alarm must satisfy (chunk decomposition via `decompose_by_time_range`, progress bracketing, connection lifecycle); (2) the unified enqueue entry-point design and the `sync_fallback_allowed` / `always_async` flag semantics shared across domains; (3) the new-vs-old path equivalence-testing strategy (spool parquet schema + rowcount parity) that becomes the acceptance template for every P2+ migration; (4) ThreadPoolExecutor concurrency model and ADR-0003 non-applicability assertion (`requires_cross_chunk_reduction=False`). These are module-boundary and data-flow decisions that `spec-architect` must settle in `design.md` before `implementation-planner` runs.

## Required Artifacts

Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Existing serial `run_eap_alarm_query_job` behavior is adequately captured in change-request §Business Goal and design.md; no separate product investigation needed. |
| proposal.md | no | Architecture decision lives in `docs/architecture/query-dataflow-unification.md` (already authored) + design.md; no user-facing behavior decision to investigate. |
| spec.md | no | No new user-facing behavior; spool schema and frontend unchanged. |
| design.md | yes | Architecture Review Required = yes; spec-architect must record the base-class template contract, unified-enqueue/flag semantics, equivalence-test strategy, and concurrency model before implementation. |
| qa-report.md | no | Routine pass/fail evidence goes in `agent-log/qa-reviewer.yml`; promote to yes only if a blocking finding or approved-with-risk emerges. |
| regression-report.md | no | New/old path equivalence is proven by parity tests, not prose; agent-log pointer suffices unless a regression is found. |
| visual-review-report.md | no | No UI/CSS surface touched. |
| monkey-test-report.md | no | No interactive UI surface. |
| stress-soak-report.md | yes | Tier-1 concurrency surface (ThreadPoolExecutor against Oracle) with a now-real caller. Durable load/soak evidence is needed: connection-pool exhaustion / leak under parallel chunk fan-out, memory-peak non-linearity claim, and chunk no-duplication/no-loss under concurrent load. This invalidates P0's `tier-floor-override` deferral. |

## Required Contracts
- API: none — no endpoint shape change; spool parquet schema + rowcount held equivalent. If `sync_fallback_allowed=False` 503 behavior is newly documented, record it in `contracts/api/error-format.md`.
- CSS/UI: none
- Env: yes — `contracts/env/env-contract.md` + `.env.example` must add `EAP_ALARM_USE_UNIFIED_JOB` (default `off`/`false`); env-contract test must pin the default value.
- Data shape: none — spool parquet schema is an explicit non-goal; equivalence is a test acceptance criterion, not a contract change.
- Business logic: yes — `contracts/business/business-rules.md` must document the unified enqueue routing decision and `sync_fallback_allowed` / `always_async` flag semantics (always-async domain ⇒ 503 on forced sync, no silent downgrade).
- CI/CD: none expected — reuse existing backend/stress/soak workflows.

## Required Tests
- unit: `EapAlarmJob` template-method overrides (chunk decomposition, progress bracket 5→15→90→100, `requires_cross_chunk_reduction=False`); unified enqueue routing per flag; `sync_fallback_allowed` flag dispatch.
- contract: env-contract default-value pin for `EAP_ALARM_USE_UNIFIED_JOB`; business-rule assertion for always-async 503-on-forced-sync.
- integration: new-vs-old worker path equivalence; Oracle connection returned via `finally: conn.close()` with no leak.
- E2E: eap_alarm async query end-to-end with flag ON yields identical result set vs flag OFF.
- visual: none
- data-boundary: spool parquet schema + rowcount parity between new and old paths.
- resilience: chunk-level Oracle fault injection — one chunk fails under parallel fan-out, no partial-result corruption.
- fuzz/monkey: none
- stress: ThreadPoolExecutor concurrency — chunk no-duplication / no-loss and connection-pool non-exhaustion under load.
- soak: sustained eap_alarm async load to confirm no connection leak and bounded memory peak over time.

## Required Agents
- spec-architect — author `design.md`: base-class template contract, unified-enqueue/flag semantics, equivalence-test strategy, concurrency/ADR-0003 reasoning (runs before implementation-planner).
- implementation-planner — convert design + contracts + tests into the execution packet before any implementation agent.
- backend-engineer — implement `EapAlarmJob`, unified enqueue entry-point, flag-gated route dispatch, connection lifecycle.
- test-strategist — design the new/old equivalence, chunk-parallel-integrity, progress-bracket, and connection-leak test surfaces; populate AC→test mapping.
- contract-reviewer — verify env + business-rule contract updates and parity acceptance criteria.
- stress-soak-engineer — execute and report the concurrency stress + soak surfaces (`stress-soak-report.md`).
- ci-cd-gatekeeper — confirm stress/soak/backend gates wire the new eap_alarm-unified cases and Tier-1 gate-readiness.
- qa-reviewer — release-readiness sign-off and known-issue / risk summary.

## Inferred Acceptance Criteria
- AC-1: With `EAP_ALARM_USE_UNIFIED_JOB=on`, an eap_alarm query produces a spool parquet whose schema AND rowcount are byte-for-row equivalent to the legacy `run_eap_alarm_query_job` path for the same query parameters.
- AC-2: `EapAlarmJob` inherits `BaseChunkedDuckDBJob` with `chunk strategy = TIME`, `always_async = True`, and `requires_cross_chunk_reduction = False`; chunk decomposition via `decompose_by_time_range` produces no duplicated and no missing rows across chunk boundaries.
- AC-3: Chunk queries execute concurrently via ThreadPoolExecutor; a cross-90-day query has measurably lower wall-time than the serial legacy path, and peak memory does not scale linearly with result-set size.
- AC-4: A forced-sync request against the always-async eap_alarm domain (`sync_fallback_allowed=False`) is rejected with HTTP 503 Service Unavailable; it is never silently downgraded to a partial synchronous response.
- AC-5: The unified enqueue entry-point replaces both Pattern A (`enqueue_job_dynamic` + registry `should_enqueue`) and Pattern B (direct `enqueue_xxx`) for eap_alarm, exposing `sync_fallback_allowed` / `always_async` flags.
- AC-6: Every Oracle connection opened during chunk execution is returned in a `finally: conn.close()`; no connection leak under sustained/soak load.
- AC-7: `EAP_ALARM_USE_UNIFIED_JOB` is registered in `env-contract.md` and `.env.example` with a default of `off`/`false`, and the env-contract test pins that default value.
- AC-8: With the flag OFF (default), behavior is byte-for-row identical to the pre-change legacy path (zero regression while both paths coexist until P4/P5 cleanup).

## Tasks Not Applicable
- not-applicable: 2.2 (CSS/UI contract — no UI surface), 4.2 (Frontend — no frontend changes), 5.1 (UI/UX review — no UI), 5.2 (Visual review — no UI)
- note: 1.3 (design decisions) is APPLICABLE and must NOT be skipped.

## Clarifications or Assumptions
- Open question resolved: For always-async domains with `sync_fallback_allowed=False` (eap_alarm), a sync fallback request MUST be rejected with HTTP 503 Service Unavailable, not silently downgraded.
- Assumption: `unified-query-core-infra` has already landed (P0 merged, CI green). This is a hard downstream dependency.
- Assumption: P0's `tier-floor-override` deferred-stress rationale is now invalidated because P1 wires a real domain caller. Stress and soak are therefore required at this tier.
- Assumption: Spool parquet schema is unchanged (explicit non-goal). If implementation discovers a forced schema change, re-classify upward.
- Assumption: AC-8 (flag-OFF zero-regression) is a standing gate for the entire P1–P4/P5 coexistence window.
