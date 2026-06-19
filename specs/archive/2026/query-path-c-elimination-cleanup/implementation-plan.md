---
change-id: query-path-c-elimination-cleanup
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Implementation Plan: query-path-c-elimination-cleanup

## Objective

Close the query-dataflow-unification migration (P4+P5): eliminate the last
gunicorn-blocking synchronous "Path C". Concretely:
1. `query_tool_routes` enqueues oversized queries to RQ (202 + job_id) behind
   `QUERY_TOOL_USE_RQ` (default off) instead of blocking a worker up to 300s.
2. `wip_routes` performs a COUNT(*) rowcount pre-check and routes >= L3 (200,000)
   queries to RQ.
3. `batch_query_engine.merge_chunks` is marked `@deprecated` (additive only).
4. The 4 already-deprecated `*_ASYNC_DAY_THRESHOLD` env vars are removed; routing
   reads `classify_query_cost` / `CostPolicy` uniformly.
5. `global_concurrency` semaphore role is re-documented (docs/contract only).

All design decisions are fixed in `design.md` (D1–D5). Do not re-derive them.

## Execution Scope

### In Scope
- Files listed in `## File-Level Plan` only.
- New `query-tool` RQ job type (D1), new wip COUNT(*) estimator (D2),
  merge_chunks deprecation marker (D5), env-var removal (D4), semaphore
  docstring/contract update (D3).
- Contract updates: env, api, business-rules, ci-gate-contract (per classification
  Required Contracts).
- All test updates that must ship in the same PR as each code change
  (per CLAUDE.md same-PR rules).

### Out of Scope
- Migrating any domain service to RQ (owned by P1–P3; already done).
- Deleting `batch_query_engine.py` or `merge_chunks` (deprecation only — non-goal).
- Any runtime change to `global_concurrency` Lua/fail-open/TTL mechanics (D3:
  docs only). Do NOT move the slot-acquire call as part of this change.
- Changing `merge_chunks` signature or behavior.
- Frontend, CSS, spool/parquet schema, DuckDB job files (none introduced).
- Opportunistic refactors in any touched file.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | feature flag | Add `QUERY_TOOL_USE_RQ` flag (default off) via `resolve_bool_flag`; mirror to env-contract + env.schema.json | backend-engineer |
| IP-2 | job registry | Register new `query-tool` JobTypeConfig (D1) with own queue + worker_fn + `always_async=False` | backend-engineer |
| IP-3 | wip service | Add lightweight `SELECT COUNT(*)` estimator over the filtered predicate (D2) | backend-engineer |
| IP-4 | query_tool route | When flag on + `classify_query_cost`==ASYNC → `enqueue_query_job(job_type="query-tool", ...)` returning 202+job_id; else inline as today (D1, AC-1/AC-2) | backend-engineer |
| IP-5 | wip route | Rowcount pre-check via `classify_query_cost(domain="wip", row_count_fn=...)`; >= L3 → RQ; fail-open stays SYNC (D2, AC-3) | backend-engineer |
| IP-6 | batch engine | Mark `merge_chunks` `@deprecated` + emit `DeprecationWarning` + "no new callers" docstring; no behavior/signature change (D5, AC-4) | backend-engineer |
| IP-7 | env cleanup | Remove all 4 `*_ASYNC_DAY_THRESHOLD` reads from 6 source files + remove `_DEPRECATED_THRESHOLD_VARS` and `_check_deprecated_threshold_env` call from query_cost_policy.py (D4, AC-5) | backend-engineer |
| IP-8 | concurrency docs | Update `global_concurrency.py` module/function docstrings to "limit RQ Oracle concurrency"; runtime unchanged (D3, AC-6) | backend-engineer |
| IP-9 | contracts | env (remove 4 vars + add flag), api (202 async shape + rowcount pre-check), business-rules (cost-routing + semaphore semantics + merge_chunks no-new-callers), ci-gate-contract (env-var removal sync) | contract-reviewer |
| IP-10 | example env | Remove 4 vars + add `QUERY_TOOL_USE_RQ` in `.env.example` and `contracts/env/.env.example.template` | backend-engineer |
| IP-11 | tests | env-pin contract tests, dispatch/pre-check unit tests, bump `test_job_registry` count 10→11, update `test_query_cost_policy` (`_APPROVED_CALLERS` only if a new caller file is added) | test-strategist |
| IP-12 | stress/e2e | Stress: RQ Oracle-concurrency bound + no worker starvation (AC-8). E2E: small query inline / flag-off unchanged (AC-2) | stress-soak-engineer, e2e-resilience-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (new query-tool job type) | IP-2/IP-4 constraint; do not reuse a generic type |
| design.md | D2 (COUNT estimator, L3=200000, fail OPEN) | IP-3/IP-5 constraint |
| design.md | D3 (semaphore doc-only) | IP-8 constraint; no runtime change |
| design.md | D4 (env removal, no migration guide) | IP-7/IP-9/IP-10 constraint |
| design.md | D5 (merge_chunks zero callers, additive) | IP-6 constraint |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-8 | acceptance mapping |
| change-classification.md | Required Contracts / Required Tests | IP-9/IP-11/IP-12 scope |
| current-behavior.md | per-file line table for the 4 vars | IP-7 exact read-sites |
| current-behavior.md | merge_chunks caller inventory | IP-6 backward-compat assertion |
| test-plan.md | AC→test mapping + ladder | IP-11/IP-12 test selection |
| ci-gates.md | Required Gates table | verification commands |
| contracts/business/business-rules.md | cost-threshold routing / semaphore / deprecation rule | IP-9 |
| docs/architecture/query-dataflow-unification.md §4.2 | semaphore slot acquired inside RQ worker | IP-8 wording |

NOTE: `test-plan.md` and `ci-gates.md` are still scaffold templates at plan time.
test-strategist (IP-11) and ci-cd-gatekeeper must fill them from the AC list and
`## Test Execution Plan` below BEFORE the gate runs; this plan supplies the
selector fallback table the gate needs.

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/core/feature_flags.py | reuse | call `resolve_bool_flag("QUERY_TOOL_USE_RQ", default=False)` from the route; no new helper needed |
| src/mes_dashboard/services/job_registry.py | none | registry API already supports D1; registration lives in the worker module |
| src/mes_dashboard/services/query_tool_service.py | modify | add row-count fn for L3 + worker entry-point `execute_query_tool_job`; append `register_job_type(JobTypeConfig(job_type="query-tool", queue_name="query-tool", worker_fn=execute_query_tool_job, always_async=False))` at module end (pattern: reject_query_job_service.py:195-199) |
| src/mes_dashboard/services/wip_service.py | modify | add `count_wip_rows(...)` COUNT(*) over the same filtered predicate as get_wip_detail (D2) |
| src/mes_dashboard/routes/query_tool_routes.py | modify | flag-gated branch in oversized data endpoints: classify → `enqueue_query_job` (async_query_job_service:381) → 202+job_id; preserve `map_service_errors` inline path when flag off (AC-1/AC-2) |
| src/mes_dashboard/routes/wip_routes.py | modify | api_detail (lines 243-330): rowcount pre-check before service call; >= L3 → RQ |
| src/mes_dashboard/services/async_query_job_service.py | reuse | `enqueue_query_job` unchanged (CER-001); pass `job_type="query-tool"` |
| src/mes_dashboard/services/batch_query_engine.py | modify | `merge_chunks` (line 631): add `@deprecated` + `warnings.warn(..., DeprecationWarning, stacklevel=2)` + no-new-callers docstring; update module docstring example (lines 22/29) to merge_chunks_to_spool |
| src/mes_dashboard/core/query_cost_policy.py | modify | remove `_DEPRECATED_THRESHOLD_VARS` (lines 34-51), `_check_deprecated_threshold_env` (57-66) and its call (line 110); keep CostPolicy + classify_query_cost intact |
| src/mes_dashboard/routes/downtime_analysis_routes.py | modify | remove DOWNTIME_ASYNC_DAY_THRESHOLD reads (lines 73,247); use CostPolicy.day_threshold via classify |
| src/mes_dashboard/routes/hold_history_routes.py | modify | remove HOLD_ASYNC_DAY_THRESHOLD reads (lines 66,239) |
| src/mes_dashboard/routes/resource_history_routes.py | modify | remove RESOURCE_ASYNC_DAY_THRESHOLD reads (lines 64,261) |
| src/mes_dashboard/services/hold_query_job_service.py | modify | remove HOLD_ASYNC_DAY_THRESHOLD reads (lines 37,69) |
| src/mes_dashboard/services/resource_query_job_service.py | modify | remove RESOURCE_ASYNC_DAY_THRESHOLD reads (lines 37,69) |
| src/mes_dashboard/services/reject_query_job_service.py | modify | remove REJECT_ASYNC_DAY_THRESHOLD reads (lines 38,76); inverted `days <= threshold` becomes CostPolicy day_threshold routing |
| src/mes_dashboard/core/global_concurrency.py | modify | docstrings only (module + acquire/release fns); runtime unchanged (D3) |
| contracts/env/env-contract.md | modify | remove 4 vars; add QUERY_TOOL_USE_RQ (default off); add semaphore semantics note |
| contracts/env/env.schema.json | modify | delete 4 var entries; add QUERY_TOOL_USE_RQ with enum + default off |
| contracts/env/.env.example.template | modify | remove 4 vars; add flag |
| .env.example | modify | remove 4 vars; add flag |
| contracts/api/api-contract.md | modify | add 202+job_id async-dispatch shape (flag-gated) + wip rowcount pre-check note |
| contracts/api/openapi.json | regen | regenerate after api-contract endpoint/schema edits |
| contracts/business/business-rules.md | modify | cost-threshold routing rule; semaphore "limit RQ Oracle concurrency"; merge_chunks no-new-callers |
| contracts/ci/ci-gate-contract.md | modify | record env-var removal sync requirement |
| tests/contract/ | add | env-pin: absence of 4 vars in env.schema.json; QUERY_TOOL_USE_RQ present default off |
| tests/test_job_registry.py | modify | bump expected count 10→11 (line 226) and add "query-tool" to expected_types set (line 230) |
| tests/test_query_cost_policy.py | modify | drop/adjust any `_DEPRECATED_THRESHOLD_VARS` assertions; add to `_APPROVED_CALLERS` ONLY if a new oracle_arrow_reader/base_chunked_duckdb_job caller file is introduced (none expected) |
| tests/test_batch_query_engine.py | modify | assert merge_chunks emits DeprecationWarning + backward-compatible result (AC-4) |
| tests/integration/ | add | RQ async dispatch parity (flag on/off) + worker-blocking-elimination (AC-1) |
| tests/e2e/test_query_tool_e2e.py | modify | small query inline; flag-off behavior unchanged (AC-2) |
| tests/e2e/test_wip_hold_pages_e2e.py | modify | sub-L3 WIP inline (AC-3) |
| tests/stress/ | add | RQ Oracle-concurrency bound; no gunicorn worker starvation (AC-8) |

## Contract Updates

- API: 202 + job_id async-dispatch shape for query_tool oversized endpoints under
  `QUERY_TOOL_USE_RQ=on`; wip rowcount pre-check behavior; flag-gated.
  Regen `contracts/api/openapi.json` after edits.
- CSS/UI: none.
- Env: remove DOWNTIME_/HOLD_/RESOURCE_/REJECT_`_ASYNC_DAY_THRESHOLD`; add
  `QUERY_TOOL_USE_RQ` (bool, default off) to env-contract.md + env.schema.json
  (enum + default) + .env.example.template + .env.example. Add global_concurrency
  semantics note.
- Data shape: none.
- Business logic: cost-threshold routing rule (classify_query_cost is the single
  routing authority); global_concurrency semaphore = "limit RQ Oracle
  concurrency"; merge_chunks deprecation / no-new-callers rule.
- CI/CD: ci-gate-contract.md records env-var removal sync; ci-cd-gatekeeper checks
  `.github/workflows/backend-tests.yml` / `contract-driven-gates.yml` no longer set
  removed vars.

## Test Execution Plan

Required phases (floor): collect, targeted, changed-area; contract (env/api/business
affected); stress is weekly/manual (AC-8, owned by stress-soak-engineer).
Generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/integration/ | flag-on oversized query → 202+job_id, no worker block |
| AC-2 | tests/e2e/test_query_tool_e2e.py | flag-off path identical to pre-change |
| AC-3 | tests/e2e/test_wip_hold_pages_e2e.py | sub-L3 WIP inline; >= L3 routes to RQ |
| AC-4 | tests/test_batch_query_engine.py | merge_chunks emits DeprecationWarning; result unchanged |
| AC-5 | tests/contract/ | 4 vars absent from env.schema.json; routes use classify |
| AC-6 | tests/contract/ | business-rules semaphore semantics pinned |
| AC-7 | tests/contract/ | QUERY_TOOL_USE_RQ present in schema, default off |
| AC-8 | tests/stress/ | RQ Oracle concurrency <= semaphore bound; no worker starvation |
| (registry) | tests/test_job_registry.py | 11 registered job types incl. "query-tool" |

(Selector fallback: bare targets/dirs above exist; do not add `cdd-kit test run`
lines here. Full ladder in test-plan.md / references/sdd-tdd-policy.md.)

## Ordering & Same-PR Constraints

- IP-1 before IP-4 (route reads the flag).
- IP-2 + IP-3 before IP-4/IP-5 (route enqueues the registered job type / calls
  the COUNT estimator).
- IP-2 must ship with the IP-11 `test_job_registry` count bump (10→11) in the
  same PR — otherwise the registry test fails.
- IP-6 must ship with the IP-11 `test_batch_query_engine` DeprecationWarning
  assertion in the same PR.
- IP-7 must ship with the IP-11 env-pin contract tests AND IP-9/IP-10 env edits
  in the same PR (removing a var without removing its schema entry fails the
  typo-guard; R4).
- IP-9 api edits must be followed by openapi.json regen in the same PR.

## Validation Steps (run order, backend-engineer)

1. `ruff check . --fix` then `ruff check .`
2. `cdd-kit validate --contracts`  (requires `pip install jsonschema`)
3. `pytest -m "not (e2e or integration_real or stress)" -x`  (bounded ladder)
4. `cdd-kit gate query-path-c-elimination-cleanup`

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Do NOT touch `global_concurrency` runtime code paths (D3 is docs-only).
- Do NOT remove `merge_chunks` or change its signature (D5 additive-only).

## Known Risks

- R1 (medium): wip COUNT(*) adds one Oracle round-trip per WIP query — run only
  when no spool/cache short-circuit; use the same indexed predicate as the detail
  query (design.md R1). Stress (AC-8) must confirm no new contention.
- R2 (medium): semaphore role is doc-only; acquiring the slot at the wrong layer
  (route vs worker) would re-block workers or fail to bound Oracle. Keep the slot
  acquired inside the RQ worker per blueprint §4.2; pin via ADR-0011 (spec-architect
  owns) + stress evidence.
- R3 (low): new `query-tool` job type breaks `test_job_registry` count (10→11) and
  `test_query_cost_policy._APPROVED_CALLERS` if not updated in the same PR.
- R4 (low): removing the 4 vars while a deployed `.env` still sets them is silent;
  contract tests must pin their absence from env.schema.json.
- code-map.yml is large (~999KB) but present and fresh (digest b25d37c8, verified
  in current-behavior.md 2026-06-19); pointers above are taken from it.
