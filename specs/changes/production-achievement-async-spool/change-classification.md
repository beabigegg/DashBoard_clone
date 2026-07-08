# Change Classification

## Change Types
- primary: `migration` (synchronous request-path Oracle query → RQ background job + DuckDB parquet spool + browser DuckDB-WASM aggregation) + `feature-enhancement` (re-architecture of the existing production-achievement report)
- secondary: `api-change` (sync `/report` → enqueue 202+job_id + poll + spool-download URL), `data-shape-change` (new SPECNAME-grain spool parquet schema + `_SCHEMA_VERSION`), `env-change` (new worker feature flag + gunicorn↔worker env parity + `env.schema.json` enum/default), `business-logic-change` (PA-06/PA-07 computation LOCATION backend→frontend, semantics unchanged), `ui-change` (sync data table → async job/poll/progress + empty/error states), `ci-cd-change` (new systemd worker unit + worker env-parity coverage)

## Lane
- feature

Rationale: originates from a production timeout defect (DPY-4024), but root cause and code location are already known and the fix is a deliberate re-architecture — not a symptom hunt. Per the mixed/edge-case rule, a fix that requires contract changes (api, data, env, business) is promoted out of the `bug-fix` lane to `feature-enhancement` to force the contract path.

## Risk Level
- high

## Impact Radius
- cross-module (system-wide risk surface: the new worker hooks the shared global `heavy_query_slot` semaphore governing every Oracle-bound async job, plus a new browser-served spool namespace and cross-process env-flag parity — a wiring/parity defect could degrade other async features even though this feature is pre-launch)

## Tier
- 1

Weighing: touches RQ queues, background workers, DuckDB spool concurrency, a new browser-served spool namespace, the shared Oracle-bound concurrency semaphore, and cross-process env-flag parity — all high-risk operational gates. "Feature not yet launched, no live users" keeps it off Tier 0 (no rewrite of the semaphore/base job; it adds a new consumer of an established pattern), but the shared-infra blast radius plus multi-contract span classify it upward to Tier 1.

## Architecture Review Required
- yes
- reason: new async architecture for this domain plus three unresolved design decisions that must be pinned before implementation — Q1 the `duckdb-activation-policy` 5000-row threshold vs a server-side aggregation fallback for sub-5000-row PA result sets; Q2 the carrier for the targets map + spec→workcenter_group mapping to the frontend; Q3 spool delivery option A (browser parquet download) vs option B (server-side DuckDB read). Also a module-boundary + data-flow change (PA-06/PA-07 computation relocates backend→frontend) touching shared concurrency infrastructure. `spec-architect` must write `design.md` before `implementation-planner` runs.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current output + parity baseline captured in `design.md` migration mapping + dual-tier parity fixture; no separate product investigation. |
| proposal.md | no | Approach already decided (async spool mirroring `resource_history`). |
| spec.md | no | Behavior spec covered by `api-contract.md` + `business-rules.md` (PA-01..PA-07). |
| design.md | yes | Architecture review required — new async architecture, unresolved Q1/Q2/Q3, backend→frontend compute-location move, module-boundary + data-flow change. |
| qa-report.md | no | Release readiness recorded as a `qa-reviewer` agent-log pointer; promote only on blocking/approved-with-risk. |
| regression-report.md | no | Regression scope lives in `test-plan.md`; parity enforced by automated dual-tier business-key diff; promote only if the diff mismatches. |
| visual-review-report.md | no | Reuses shared async progress/loading components; `visual-reviewer` records evidence in agent-log; promote only on visual regressions. |
| monkey-test-report.md | no | Monkey result recorded as an agent-log pointer unless blocking. |
| stress-soak-report.md | yes | New worker contends on the shared global `heavy_query_slot` semaphore + spool store; durable load/soak evidence required to prove no concurrency regression to other async workers. |

## Required Contracts
- API: yes — `contracts/api/api-contract.md` (+ `api-inventory.md`, `contracts/api/openapi.json` and root `contracts/openapi.json` mirror): sync report → enqueue (202 + `job_id`) → poll → `spool_download_url = /api/spool/production_achievement/<id>.parquet`.
- CSS/UI: no — reuses existing shared async progress/loading components; no new tokens or governed CSS source. (UI/UX + visual review still required for the new async states.)
- Env: yes — `contracts/env/env-contract.md` (§Worker Feature-Flag Env-Var Parity), `contracts/env/env.schema.json` (new worker flag `enum` + `default`), `contracts/env/.env.example.template` (+ root `.env.example`).
- Data shape: yes — `contracts/data/data-shape-contract.md`: new SPECNAME-grain spool parquet schema `(output_date, shift_code, SPECNAME, actual_output_qty)` + `_SCHEMA_VERSION` + schema-break/rollback (`rm`) policy.
- Business logic: yes — `contracts/business/business-rules.md` (PA-01..PA-07): record PA-06/PA-07 computation LOCATION moves backend→frontend, semantics unchanged.
- CI/CD: yes — new `deploy/mes-dashboard-production-achievement-worker.service` + worker env parity; `ci-cd-gatekeeper` confirms whether `contracts/ci/ci-gate-contract.md` and soak/stress/e2e workflows need a new worker/spool entry.

## Required Tests
- unit: yes — new `tests/test_production_achievement_unified_job.py` (mock chunk-seam); `_APPROVED_CALLERS` membership in `tests/test_query_cost_policy.py`; job-registry count in `tests/test_job_registry.py`; `spool_routes._ALLOWED_NAMESPACES` allowlist test; env default/enum test; frontend `useProductionAchievementDuckDB` rollup/target-join/rate unit test.
- contract: yes — api-contract endpoint tests, data-shape parquet-schema tests, env-contract default/enum tests, openapi resolution/sync.
- integration: yes — new `tests/integration/test_production_achievement_rq_async.py` (enqueue→job→spool round-trip); dual-tier parity (real-path parquet business-key diff vs current synchronous output); semaphore-wiring reuse.
- E2E: yes — new `frontend/tests/playwright/production-achievement-async.spec.ts` + backend browser-DuckDB e2e (job+poll+progress → table render), mirroring `resource-history-async`.
- visual: yes — new async job/poll/progress + empty/error states (ui-ux + visual review; evidence in agent-log unless regressions).
- data-boundary: yes — report/data-shape boundary tests (empty result, missing targets, SPECNAME-grain edges, malformed spool rows).
- resilience: yes — worker crash, Redis down, job timeout, missing/late spool, semaphore contention (Tier 1).
- fuzz/monkey: yes — operation-sequence monkey over the async job flow (scoped; report optional).
- stress: yes — concurrent async jobs contending on the global `heavy_query_slot` semaphore + spool store.
- soak: yes — long-running worker + spool accumulation; may reuse `tests/integration/test_soak_workload.py` harness.

## Required Agents
- `spec-architect` — writes `design.md`: async architecture + Q1 activation-threshold, Q2 targets/mapping carrier, Q3 spool delivery option A/B, PA-06/PA-07 compute-location move.
- `implementation-planner` — execution packet from contracts/decisions/tests before any implementation agent runs.
- `backend-engineer` — new `BaseChunkedDuckDBJob` subclass worker (`chunk_strategy=TIME`, `requires_cross_chunk_reduction=False`, `always_async=True`), `acquire_heavy_query_slot` wiring, route enqueue/poll, spool namespace allowlist, `_APPROVED_CALLERS`, env flag, systemd unit input.
- `frontend-engineer` — new `useProductionAchievementDuckDB.ts`, App.vue async states, activation-policy handling, spec→workcenter_group + targets join in DuckDB-WASM.
- `contract-reviewer` — multi-contract review: api, data, env (+ `env.schema.json`), business, openapi mirror.
- `test-strategist` — test plan, AC→test mapping, dual-tier parity design, data-boundary + env-parity coverage.
- `ci-cd-gatekeeper` — systemd worker unit, gunicorn↔worker env parity, backend/e2e/soak/stress workflow coverage, ci-gate-contract entry decision.
- `e2e-resilience-engineer` — browser async e2e + resilience (worker/Redis/timeout/spool) (Tier 1 heavy).
- `stress-soak-engineer` — semaphore-contention stress + spool soak; owns `stress-soak-report.md` (Tier 1 heavy).
- `monkey-test-engineer` — operation-sequence fuzz over the async job/poll flow (Tier 1 heavy; report optional).
- `ui-ux-reviewer` — interaction/copy/accessibility of the new async states.
- `visual-reviewer` — visual evidence of async/progress/empty/error states.
- `qa-reviewer` — release readiness / gate sign-off.

## Inferred Acceptance Criteria
- AC-1: A 30-day (and up to the 730-day maximum) production-achievement report request returns HTTP 202 with a `job_id` and executes NO Oracle query on the Flask request thread (no `read_sql_df`/fast-pool call), eliminating the DPY-4024 timeout path.
- AC-2: The frontend polls the job via `useAsyncJobPolling`; on completion the response provides a `spool_download_url` of the form `/api/spool/production_achievement/<id>.parquet`, and the page renders from the downloaded spool.
- AC-3: The `production_achievement` spool namespace is present in `spool_routes._ALLOWED_NAMESPACES` (same PR as the spool write) and the parquet is downloadable by an authorized browser client, while unknown/unauthorized namespaces are rejected.
- AC-4: The new worker is registered in `tests/test_query_cost_policy.py` `_APPROVED_CALLERS`, is counted in the job-registry test, and calls `acquire_heavy_query_slot` before its Oracle read (heavy-query semaphore wired before the flag ships).
- AC-5: The gunicorn process and the RQ worker process resolve identical values for the new worker feature flag / env var (Worker Feature-Flag Env-Var Parity); `env.schema.json` defines its `enum` + `default`; `.env.example.template` and root `.env.example` are updated.
- AC-6: The spool parquet schema is exactly `(output_date, shift_code, SPECNAME, actual_output_qty)` at SPECNAME grain and carries a `_SCHEMA_VERSION`; a schema break bumps the version AND adds `rm` to the rollback runbook in the same commit.
- AC-7: The frontend DuckDB-WASM computation reproduces PA-06 (SPECNAME→workcenter_group rollup via the spec→workcenter_group mapping) and PA-07 (target join + `achievement_rate`) with business semantics unchanged; for an identical date range the rendered rows `(output_date, shift_code, workcenter_group, actual_output_qty, target_qty, achievement_rate)` equal the current synchronous implementation's output, proven by a dual-tier parity business-key diff.
- AC-8: The `duckdb-activation-policy` decision for sub-5000-row PA result sets is resolved per `design.md` and enforced — either the threshold is lowered/overridden so DuckDB-WASM always activates for this page, or a documented server-side aggregation fallback is used — and the chosen path is covered by a test.
- AC-9: A new `deploy/mes-dashboard-production-achievement-worker.service` systemd unit exists and matches existing worker-unit conventions; the async job flow (enqueue→poll→spool→render) passes e2e and survives resilience faults (worker crash, Redis unavailable, job timeout, missing spool).

## Tasks Not Applicable
- not-applicable: 2.2

Note: task 1.3 (design review) is explicitly applicable (design.md required) and must NOT be skipped. All api/data/env/business/CI contract tasks (2.1, 2.3, 2.4, 2.5, 2.6), all test families (3.1–3.5), and the deploy/systemd + CI worker-parity work (4.3, 4.4) are applicable. Optional artifacts marked `no` above have no dedicated tasks.yml IDs to skip.

## Clarifications or Assumptions
- Single atomic change (worker + route + frontend ship together for a pre-launch feature with clean sync→async replacement and no dual-path fallback); no atomic-split despite multi-contract span.
- No new CSS tokens/governed CSS source — async progress/empty/error UI reuses existing shared components. If the frontend introduces new component classes, promote CSS/UI to a required contract and re-evaluate `visual-review-report.md`.
- Open (defer to `spec-architect` in `design.md`): Q1 activation-threshold vs server-side fallback; Q2 targets-map + spec→workcenter_group carrier; Q3 spool delivery option A vs B. AC-7/AC-8 are written to be testable under whichever option `design.md` selects.
- Soak coverage may reuse the existing `tests/integration/test_soak_workload.py` harness rather than a bespoke soak; `stress-soak-engineer`/`ci-cd-gatekeeper` to confirm.
- Agent name normalization: the classifier's `monkey-tester` maps to the concrete agent type `monkey-test-engineer`.

## Context Manifest Draft
See `context-manifest.md` (written verbatim from this draft).
