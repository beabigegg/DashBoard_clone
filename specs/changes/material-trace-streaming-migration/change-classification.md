# Change Classification

## Change Types
- primary: `migration` (streaming Arrow→DuckDB execution-path migration in `material_trace_service`)
- secondary: `business-logic-change` (semaphore semantics doc/contract update), `env-change` (new feature flag `MATERIAL_TRACE_USE_UNIFIED_JOB`), `performance` (OOM-prevention via on-disk spill replacing post-hoc memory guard)

## Lane
- feature

## Risk Level
- high

Rationale: touches a worker/RQ async execution path, Oracle-bound concurrency semaphore semantics, memory-guard removal, and DuckDB on-disk spill behavior. Per the high-risk gate list (queues, caches, long-running jobs, concurrency, OOM), this classifies upward even though it is flag-gated and difficulty-M.

## Impact Radius
- cross-module

Touches `services/material_trace_service.py`, `core/global_concurrency.py` (semantics only), `core/base_chunked_duckdb_job.py` (consumer of existing base class), the material-trace RQ worker path, and the spool pipeline. Frontend explicitly out of scope; spool schema unchanged.

## Tier
- 1

Rationale: high risk + cross-module → Tier 0–1. The flag default-off and unchanged spool schema bound the blast radius, and the concurrency-critical base class already exists and was hardened by the POC, so Tier 1 (not 0) with full stress/soak consideration deferred behind the flag is appropriate.

## Architecture Review Required
- yes
- reason: Migration/rollback decision (flag-gated cutover from `pd.concat` to streaming Arrow→DuckDB), data-flow change (per-batch streaming + on-disk spill), and an operational-risk decision (removing the post-hoc `_check_memory_guard()` and re-purposing the cross-worker semaphore from "protect sync path" to "limit RQ concurrency to Oracle"). The open question about cross-lot aggregation (`requires_cross_chunk_reduction`) is a non-obvious design decision per ADR-0003 precedent that must be resolved before implementation. `spec-architect` must write `design.md` before `implementation-planner` runs.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | captured in change-request and will be restated in design.md |
| proposal.md | no | decision already made in `docs/architecture/query-dataflow-unification.md` §3 P3 |
| spec.md | no | no user-facing behavior decision; backend execution-path change behind a flag |
| design.md | yes | Architecture Review Required = yes; migration/rollback, data-flow, semaphore-semantics, and cross-chunk-reduction decisions need durable design record (mirrors ADR-0003/0009 pattern) |
| qa-report.md | no | routine pass/fail belongs in `agent-log/qa-reviewer.yml`; promote to yes only if blocking findings |
| regression-report.md | no | flag-off parity covered by required tests |
| visual-review-report.md | no | no frontend/UI change |
| monkey-test-report.md | no | no interactive UI surface changed |
| stress-soak-report.md | yes | high-risk OOM/memory claim (AC-5 peak-heap non-linearity, DuckDB spill) plus RQ-to-Oracle concurrency cap need durable load/soak evidence |

## Required Contracts
- API: none expected (no endpoint behavior change; contract-reviewer must confirm)
- CSS/UI: none
- Env: `contracts/env/env-contract.md` + `contracts/env/env.schema.json` + `contracts/env/.env.example.template` — add `MATERIAL_TRACE_USE_UNIFIED_JOB` (boolean, default `off`, with `enum`+`default` per env test-discipline rule)
- Data shape: none expected (spool parquet schema unchanged — AC-4; contract-reviewer must confirm)
- Business logic: `contracts/business/business-rules.md` — update semaphore semantics from "protect sync path" to "limit RQ concurrency to Oracle"; record in `contracts/CHANGELOG.md`
- CI/CD: none expected (existing async/stress/soak gates cover it; ci-cd-gatekeeper confirms)

## Required Tests
- unit: `_execute_batched_query` flag-off legacy path (pd.concat preserved), flag-on streaming path, removal of post-hoc `_check_memory_guard()` call on unified path (use `ast.parse` to prove absence per test-discipline), feature-flag default-off assertion
- contract: env-contract test pinning `MATERIAL_TRACE_USE_UNIFIED_JOB` default value; api/data contract no-change assertions; business-rules semaphore-semantics text
- integration: material-trace RQ async (flag-on enqueues unified job; RQ-unavailable → 503, no silent fallback — mirror `test_eap_alarm_rq_async.py`); flag parity (flag-off vs flag-on produce identical result set and identical spool parquet schema)
- E2E: `tests/e2e/test_material_trace_e2e.py` smoke under flag-on (full trace pipeline still returns)
- visual: none
- data-boundary: spool parquet schema-equivalence between flag-off and flag-on paths (AC-4); ID-list >1000 decomposition boundary (`decompose_by_ids` 1000/batch)
- resilience: Oracle fault injection mid-stream + Redis chaos during multi-batch streaming; semaphore CAS contention under worker loss
- fuzz/monkey: none (no new user-facing input surface)
- stress: concurrent multi-batch jobs respect RQ-to-Oracle concurrency cap (`HEAVY_QUERY_MAX_CONCURRENT`); `test_chunk_boundary.py` for 1000-ID boundary
- soak: weekly soak workload under flag-on confirming peak heap does NOT grow linearly with chunk count (AC-5, DuckDB on-disk spill active)

## Required Agents
1. `spec-architect` — writes `design.md`: cutover/rollback strategy, data-flow, semaphore re-purpose, resolve cross-chunk-reduction open question
2. `implementation-planner` — turns design + contracts + tests into execution packet
3. `backend-engineer` — implements streaming Arrow→DuckDB path, flag gating, removes post-hoc guard, wires base class
4. `test-strategist` — designs flag-parity, data-boundary, resilience, stress/soak test matrix and AC→test mapping
5. `contract-reviewer` — verifies env + business-rules changes and confirms api/data/css contracts are genuinely unchanged
6. `e2e-resilience-engineer` — Oracle/Redis fault-injection during multi-batch streaming, 503-on-RQ-unavailable
7. `stress-soak-engineer` — peak-heap-non-linearity soak + RQ-to-Oracle concurrency-cap stress
8. `ci-cd-gatekeeper` — confirms async/stress/soak gates wired; no ci-gate-contract change needed
9. `qa-reviewer` — release readiness, flag-off regression sign-off

## Inferred Acceptance Criteria
- AC-1: With `MATERIAL_TRACE_USE_UNIFIED_JOB` off (default), `_execute_batched_query()` uses the legacy `pd.concat(chunks)` path and produces identical results (no regression).
- AC-2: With the flag on, a material-trace query enqueues the unified `BaseChunkedDuckDBJob`-derived material-trace RQ job instead of executing the sync concat path.
- AC-3: With the flag on and RQ/Redis unavailable, the request returns HTTP 503 (no silent fallback to the legacy sync path).
- AC-4: The spool parquet schema (column set, types, ordering) is equivalent between the flag-off and flag-on result paths.
- AC-5: Under the flag-on path, peak heap does NOT grow linearly with chunk count (DuckDB on-disk spill active), demonstrated by soak measurement across increasing ID-list sizes.
- AC-6: The post-hoc `_check_memory_guard()` call is removed from the unified streaming path (provable by AST-walk).
- AC-7: `contracts/business/business-rules.md` documents the semaphore role as "limit RQ concurrency to Oracle"; no code change to `global_concurrency.py` mechanics.
- AC-8: ID-list decomposition uses `decompose_by_ids` at 1000 IDs/batch; cross-lot-aggregation question resolved in design.md — if cross-chunk reduction required, `requires_cross_chunk_reduction=True` set (per ADR-0003); if not, ID_LIST parallel path confirmed safe.

## Tasks Not Applicable
- not-applicable: 2.2 (CSS/UI — no UI surface), 4.2 (Frontend — no frontend change), 5.1 (UI/UX review — no UI surface), 5.2 (Visual review — no UI surface)

## Clarifications or Assumptions
- Assumption: `BaseChunkedDuckDBJob` from `eap-alarm-unified-job-poc` is merged and stable; this change consumes it without modifying its core contract.
- Assumption: The dependency on `eap-alarm-unified-job-poc` gate-pass is satisfied before this change starts (per change-request P3 sequencing).
- Assumption: No new API endpoint or response-shape change — only internal execution path changes. contract-reviewer must confirm api/data contracts untouched.
- Open question (to be resolved by spec-architect in design.md): whether material-trace has cross-lot aggregation requiring `requires_cross_chunk_reduction=True`. This determines whether ID_LIST parallel chunking is valid (per ADR-0003, row-count chunking is incompatible with cross-row reductions).
- Assumption: `tier-floor-override` NOT needed — code has live callers and stress IS planned.
