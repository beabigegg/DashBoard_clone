# Design: query-path-c-elimination-cleanup

## Summary
P4+P5 closes the query-dataflow-unification migration. It eliminates the last
gunicorn-blocking synchronous "Path C" by routing oversized queries to RQ:
`query_tool_routes` (behind `QUERY_TOOL_USE_RQ`, default off) enqueues when
`classify_query_cost` returns ASYNC instead of blocking a worker up to 300s on
`QueryTimeoutError`; `wip_routes` gains a COUNT-based rowcount pre-check that
routes ≥ L3 (200,000-row) queries to RQ. `batch_query_engine.merge_chunks` (the
unused pandas-concat path, OOM #2) is marked `@deprecated` (additive only). The 4
already-deprecated `*_ASYNC_DAY_THRESHOLD` env vars are removed; routes/services
read `classify_query_cost`/`CostPolicy` uniformly. The `global_concurrency`
semaphore is re-documented from "protect sync path" to "limit RQ Oracle
concurrency" — runtime mechanics unchanged.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| query_tool routes | src/mes_dashboard/routes/query_tool_routes.py | flag-gated cost classify → enqueue RQ (202+job_id); else inline as today |
| query_tool service | src/mes_dashboard/services/query_tool_service.py | expose COUNT/row_count_fn for L3; worker entry-point for new job type |
| wip routes | src/mes_dashboard/routes/wip_routes.py | rowcount pre-check; ≥ L3 → RQ |
| wip service | src/mes_dashboard/services/wip_service.py | add lightweight COUNT(*) estimator (none exists today) |
| async dispatch | src/mes_dashboard/services/async_query_job_service.py | reuse `enqueue_query_job` (no new API) |
| job registry | src/mes_dashboard/services/job_registry.py | register new query_tool job type (+test count update) |
| cost policy | src/mes_dashboard/core/query_cost_policy.py | remove `_DEPRECATED_THRESHOLD_VARS`; callers use classify directly |
| global concurrency | src/mes_dashboard/core/global_concurrency.py | docstring semantics update only (no runtime change) |
| batch engine | src/mes_dashboard/services/batch_query_engine.py | `merge_chunks` @deprecated + DeprecationWarning + no-new-callers docstring |
| threshold callers | routes/{downtime_analysis,hold_history,resource_history}_routes.py; services/{hold,reject,resource}_query_job_service.py | remove `*_ASYNC_DAY_THRESHOLD` reads; use CostPolicy.day_threshold |
| contracts | contracts/env/{env-contract.md,env.schema.json,.env.example.template}, .env.example, contracts/api/api-contract.md, contracts/business/business-rules.md, contracts/ci/ci-gate-contract.md | remove 4 vars; add QUERY_TOOL_USE_RQ; document semaphore + merge_chunks rules |

## Key Decisions

**D1 — RQ job type for query_tool: CHOICE = create a new `query-tool` job type.**
job_registry.py has no existing query_tool/wip job type and no "generic heavy"
type (each registered type is domain-specific with its own worker_fn/queue). The
generic `enqueue_query_job` entry-point is reused, but it requires a registered
`JobTypeConfig`. Register `job_type="query-tool"` (own queue, `always_async=False`
so sync fallback stays allowed under flag-off semantics). Adding a registration
increments the `register_job_type()` count asserted in tests/test_job_registry.py
— must be updated in the same PR.

**D2 — wip_routes rowcount pre-check: CHOICE = add a new COUNT(*) estimator to
wip_service; threshold = L3 200,000; fail OPEN (stay SYNC) on Oracle error.**
wip_service has no count function today, so one must be added (lightweight
`SELECT COUNT(*)` over the same filtered predicate). Wired via
`classify_query_cost(domain="wip", row_count_fn=...)`; WIP has no date range so L2
never fires — only L3 matters. Fail-open matches `classify_query_cost`'s existing
L3 contract (COUNT failure → SYNC), preserving today's behavior when the
pre-check cannot run; it does not introduce a new failure mode.

**D3 — global_concurrency semantics: CHOICE = docs/contract update only; no
runtime behavior change.** New statement: "`HEAVY_QUERY_MAX_CONCURRENT` bounds the
number of RQ heavy jobs concurrently hitting Oracle (cross-job semaphore), not
synchronous request workers." The slot is acquired inside the RQ worker around the
Oracle fetch (per blueprint §4.2), not at route enqueue time. Lua/fail-open/TTL
mechanics are unchanged. Captured in ADR-0011 (see ADR rule).

**D4 — env-removal rollback: ANSWER = NO migration guide / breaking-change notice
needed beyond the changelog entry.** The 4 vars were marked
`Deprecated (removal P5)` by `unified-query-core-infra` with runtime
`DeprecationWarning` already emitted — the deprecate-2-minors policy is satisfied.
This change is the final removal step. Rollback is git revert; no operator action
because behavior already ignored these vars (routing came from `classify_query_cost`).

**D5 — merge_chunks deprecation: ANSWER = YES all callers already migrated.**
`merge_chunks` has ZERO production callers (verified): every dataset cache /
service uses `merge_chunks_to_spool`. Remaining references are the module docstring
example (batch_query_engine.py lines 22/29) and tests/test_batch_query_engine.py
(6 occurrences). Backward-compat guarantee: add `@deprecated` + emit
`DeprecationWarning` + "no new callers" docstring; **no behavior change**, no
signature change, function not removed (per non-goal).

## Migration / Rollback
- **Flag-off rollback (query_tool):** set `QUERY_TOOL_USE_RQ=off`, restart gunicorn
  + worker. Default is off, so the merged state is already the safe state.
- **wip rowcount pre-check:** no flag; rollback is git revert. Fail-open on COUNT
  error means a degraded Oracle never makes WIP stricter than today.
- **Env-var removal:** nothing to roll back operationally — vars were already
  inert (routing via CostPolicy). Re-introduction would be a git revert + changelog.
- **merge_chunks:** none needed; additive deprecation only.
- No spool/parquet schema changes → frontend view paths untouched; no DuckDB job
  files introduced by this change.

## Open Risks
- **R1 (medium):** wip COUNT(*) pre-check adds one Oracle round-trip per WIP query.
  Mitigation: only run when no spool/cache short-circuit; ensure the COUNT uses the
  same indexed predicate as the detail query. Stress test must confirm no new
  worker contention.
- **R2 (medium):** semaphore role change is doc-only, but if the slot is acquired
  at the wrong layer (route vs worker) it could either re-block workers or fail to
  bound Oracle. Pin via ADR-0011 + stress evidence (no worker starvation; bounded
  Oracle concurrency).
- **R3 (low):** new `query-tool` job type breaks tests/test_job_registry.py count
  and tests/test_query_cost_policy._APPROVED_CALLERS expectations if not updated in
  the same PR.
- **R4 (low):** removing the 4 vars while a deployed `.env` still sets them is
  silent (vars simply ignored). Contract tests must pin their *absence* from
  env.schema.json so the typo-guard does not regress.
