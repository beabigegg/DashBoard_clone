---
change-id: production-achievement-async-spool
schema-version: 0.1.0
last-changed: 2026-07-08
risk: high
tier: 1
---

# Implementation Plan: production-achievement-async-spool

## Objective

Ship, in one atomic PR, the sync→async migration of `GET /api/production-achievement/report`:
1. a new `BaseChunkedDuckDBJob` worker that fans `sql/production_achievement.sql` out in TIME
   chunks and writes a SPECNAME-grain DuckDB parquet spool (namespace `production_achievement`);
2. the route rewritten to serve an existing spool immediately (200) / enqueue (202) / 503 when
   no worker is available (`always_async=True`, no sync fallback);
3. a new DuckDB-WASM frontend composable that downloads the parquet and computes PA-06
   (SPECNAME→workcenter_group rollup) + PA-07 (target join + achievement_rate) client-side.

PA-01..PA-07 business semantics are UNCHANGED; only the compute LOCATION of PA-06/PA-07 moves
backend→frontend (ADR-0016). Success = a 30/730-day report no longer runs any request-path Oracle
query (no DPY-4024) AND the rendered rows equal the current synchronous output for an identical
date range (dual-tier parity, AC-7). Worker + route + frontend + registry/allowlist/env-flag entries
all land together.

## Execution Scope

### In Scope
- New worker `production_achievement_worker.py`, route enqueue/poll/spool-hit rewrite, spool
  namespace allowlist, approved-caller whitelist, env feature-flag wiring, worker preload import.
- New frontend `useProductionAchievementDuckDB.ts`; async job/poll/progress/empty/error states in
  `useProductionAchievement.ts` + `App.vue`; DuckDB-WASM rollup + target-join + rate.
- Keeping code in sync with the already-authored contracts (openapi mirror, response samples).

### Out of Scope (do NOT touch — see change-request.md §Non-goals)
- The PA-05 qualification predicate in `sql/production_achievement.sql` (WORKFLOWNAME bridge,
  SPECNAME/processtypename branches) — reused verbatim per chunk.
- PA-01..PA-07 business semantics (shift, output_date, achievement-rate formula) — location-only move.
- No dual-path sync fallback, no `*_USE_RQ` gradual flag (`always_async=True`).
- Targets `PUT`/permission endpoints (`api_put_targets`, admin permission routes) and
  `filter-options`/`targets` GET routes — behavior unchanged.
- Contract authoring — contracts/test-plan/ci-gates are DONE (contract-reviewer/spec-architect/
  test-strategist); implementers keep code+samples+openapi-mirror in sync, they do not re-derive.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | worker | new `ProductionAchievementJob(BaseChunkedDuckDBJob)` + `execute_*_unified_job` + `register_job_type(always_async=True)` with re-aggregating `post_aggregate` | backend-engineer |
| IP-2 | service | add `_PA_SPOOL_SCHEMA_VERSION` + canonical spool-key helper (date-range only); retain `build_achievement_rows()` as test-only golden | backend-engineer |
| IP-3 | route | `/report` → spool-hit 200 (inline maps) / miss 202 / no-worker 503; lazy worker import for registration | backend-engineer |
| IP-4 | infra allowlists | `spool_routes._ALLOWED_NAMESPACES += production_achievement`; approved-caller whitelist; `rq_worker_preload` imports worker | backend-engineer |
| IP-5 | env parity | `PRODUCTION_ACHIEVEMENT_*` flag read in `config/settings.py`; frozen-at-boot parity gunicorn↔worker | backend-engineer |
| IP-6 | frontend compute | new `useProductionAchievementDuckDB.ts` — activate(threshold=0)→fetch parquet→rollup+join+rate | frontend-engineer |
| IP-7 | frontend orchestration/UI | `useProductionAchievement.ts` + `App.vue` async job/poll/progress/empty/error states | frontend-engineer |
| IP-8 | deploy unit + CI workflows | systemd worker unit + env-parity/e2e workflow steps | ci-cd-gatekeeper (already scoped; not in this plan's packets) |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | AC-1..AC-9 | acceptance criteria driving every packet row |
| change-request.md | §Non-goals, §Constraints | out-of-scope boundary, same-PR allowlist rule |
| design.md | §Key Decisions (chunk-seam RESOLVED, Q1/Q2/Q3), §Affected Components table | worker/route/frontend implementation constraints |
| design.md | §Migration/Rollback | atomic PR, 503-on-no-worker, `_PA_SPOOL_SCHEMA_VERSION` rollback rule |
| test-plan.md | §AC→Test Mapping, §Test Update Contract, §Notes | which tests to write failing-first; TDD order; module-const monkeypatch note |
| ci-gates.md | §Required Gates, §Workflow Changes, §Rollback Policy | verification gates + worker-env-parity-static + kill-switch |
| data-shape-contract.md | §3.28 (.1 parquet schema, .2 spec_workcenter_map, .3 targets_map, .4 envelopes) | spool schema, inline maps, 200/202/503 shapes |
| env-contract.md | §Worker Feature-Flag Env-Var Parity; `PRODUCTION_ACHIEVEMENT_*` rows | flag names/defaults, boot parity |
| business-rules.md | PA-01..PA-07 | semantics-unchanged reference for parity |
| src/.../workers/resource_history_base_worker.py | reference implementation (whole file) | worker skeleton to mirror (pre_query/build_chunk_sql/post_aggregate/entry/register) |

## File-Level Plan

### Backend-engineer packet
Reference skeleton to mirror throughout: `src/mes_dashboard/workers/resource_history_base_worker.py`
(`ResourceHistoryBaseJob`, lines 44-229). Reuse `eap_alarm_worker.py` only for the seam-safe
`post_aggregate` re-aggregation idea (this worker's differentiator).

| path | action | what to do | AC / contract |
|---|---|---|---|
| `src/mes_dashboard/workers/production_achievement_worker.py` | CREATE | `ProductionAchievementJob(BaseChunkedDuckDBJob)`: `namespace="production_achievement"`, `chunk_strategy=ChunkStrategy.TIME`, `requires_cross_chunk_reduction=False`. `pre_query()`: parse `start_date`/`end_date`, compute spool key via IP-2 helper, build daily TIME chunks (mirror ref lines 68-101). `build_chunk_sql()`: `SQLLoader.load_with_params("production_achievement", CONTAINERNAME_FILTER="")`, bind `start_date`+`chunk_end_excl` per chunk. `post_aggregate()`: glob `chunk-*.parquet` and **re-aggregate `GROUP BY output_date, shift_code, SPECNAME` `SUM(actual_output_qty)`** into the canonical spool (NOT a plain `COPY (SELECT *)` concat — this is the chunk-seam correctness point: PA-03/PA-04 previous-day tail makes a group straddle a calendar-midnight seam, so plain-concat would emit duplicate keys); `register_spool_file`. Empty/no-parquet path writes a VALID empty parquet with the exact §3.28.1 schema. `execute_production_achievement_unified_job(job_id, params)` RQ entry (mirror ref 188-216). Module-level `register_job_type(JobTypeConfig(job_type="production-achievement", queue_name=PRODUCTION_ACHIEVEMENT_WORKER_QUEUE, worker_fn=..., timeout_seconds=..., always_async=True))`. Heavy-query slot is inherited from `BaseChunkedDuckDBJob.run()` — NO manual `acquire_heavy_query_slot`. | AC-1, AC-4, AC-6, AC-7; data §3.28.1 |
| `src/mes_dashboard/sql/production_achievement.sql` | REUSE (no edit) | Bound per-chunk via `start_date`/`chunk_end_excl`; PA-05 predicate verbatim. | AC-7; change-request §Non-goals |
| `src/mes_dashboard/services/production_achievement_service.py` | EDIT | Add `_PA_SPOOL_SCHEMA_VERSION` int constant + `make_canonical_pa_spool_id(start_date, end_date)` (date-range only, participates in key; shift/workcenter params do NOT — §3.28 canonical-key rule) shared by route + worker. Retain `build_achievement_rows()` (lines 112-169) + `_compute_achievement_rate()` (172-180) as test-only golden. Remove `get_achievement_report()` (199-230) from the request path (route no longer calls it; keep only if the golden/parity test imports it). | AC-6, AC-7; data §3.28 |
| `src/mes_dashboard/routes/production_achievement_routes.py` | EDIT | Rewrite `api_get_report` (lines 73-93): validate date range (reuse `_validate_date_range`); lazy-import the worker module (registration side-effect); compute spool key via IP-2 helper; **spool exists →** 200 `data={query_id, spool_download_url:"/api/spool/production_achievement/<id>.parquet", spec_workcenter_map (filter_cache.get_spec_workcenter_mapping → [{SPECNAME, workcenter_group}]), targets_map (get_targets_map → [{shift_code, workcenter_group, target_qty}])}` — injected UNCONDITIONALLY, not row-count gated (Q1); **miss + worker available →** enqueue via `async_query_job_service`, return 202 `{async:true, job_id, status_url:"/api/job/<id>?prefix=production-achievement"}`; **miss + `not is_async_available()` →** 503 `SERVICE_UNAVAILABLE`. Leave `filter-options`/`targets`/permissions routes untouched. NOTE the hyphen/underscore split: spool namespace + path use `production_achievement` (underscore); job status prefix uses `production-achievement` (hyphen). | AC-1, AC-2, AC-8; api-contract §, data §3.28.4 |
| `src/mes_dashboard/routes/spool_routes.py` | EDIT | Add `"production_achievement"` to `_ALLOWED_NAMESPACES` used by `download_spool_parquet` (line ~36). Same PR as the spool write. | AC-3 |
| `src/mes_dashboard/services/job_registry.py` | REUSE (no edit) | Registration via `register_job_type()` in the worker module; do not modify the registry itself. | AC-4 |
| `src/mes_dashboard/core/query_cost_policy.py` | VERIFY (likely no edit) | The Oracle read inherits `caller="base_chunked_duckdb_job"` from `BaseChunkedDuckDBJob.run()`. `_APPROVED_CALLERS` is NOT a symbol in this module (code-map: only `classify_query_cost`/`_default_policy_for`/`_date_span_days`) — the enforcing whitelist lives in `tests/test_query_cost_policy.py` (see test packet). Edit here ONLY if design.md's Affected-Components row requires a code-side policy classification for the new caller. | AC-4 |
| `src/mes_dashboard/config/settings.py` | EDIT | Read/expose `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` (default `on`), and `PRODUCTION_ACHIEVEMENT_WORKER_QUEUE` (`production-achievement-query`) / `PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS` (`1800`) if centralized here; the worker may also `os.getenv` these directly (mirror ref lines 33-39). Flag frozen at boot; must resolve identically in gunicorn and RQ worker. | AC-5; env §Worker Feature-Flag Env-Var Parity |
| `src/mes_dashboard/rq_worker_preload.py` | EDIT | Import `production_achievement_worker` so `register_job_type()` fires in the worker process (mirror the existing resource/eap-alarm preload imports). | AC-4, AC-5 |

Deploy systemd unit + gunicorn.conf env + workflow steps are owned by **ci-cd-gatekeeper** (ci-gates.md §Workflow Changes); not in this backend packet.

### Frontend-engineer packet
Reference to mirror: resource-history's `useResourceHistoryDuckDB.ts` + async spec (out of this
packet's read scope; described in design.md §Affected Components). Reuse shared `duckdb-client.ts`,
`duckdb-activation-policy.ts`, `useAsyncJobPolling.ts` as-is (no edits).

| path | action | what to do | AC / contract |
|---|---|---|---|
| `frontend/src/production-achievement/composables/useProductionAchievementDuckDB.ts` | CREATE | On a 200 spool-hit response: call the activation policy with **`threshold=0`** (always activate DuckDB-WASM; Q1); `fetchParquetBuffer(spool_download_url)` → `registerParquet` → `computeView()` running SQL that: JOINs `spool.SPECNAME = map.SPECNAME` via **`UPPER(TRIM(SPECNAME))`** (must equal backend `str(specname).strip().upper()`), excludes unmapped SPECNAMEs (PA-06), `GROUP BY output_date, shift_code, workcenter_group SUM(actual_output_qty)`, LEFT JOINs `targets_map` on `(shift_code, workcenter_group)`, computes `achievement_rate` with guards: target null → null, target 0 → null (NOT Infinity), actual 0 + target>0 → 0.0. Output rows match `ProductionAchievementReportRow`. Empty parquet → empty rows, never an error. WASM-unsupported browser → explicit unsupported state (no hidden server rollup). | AC-2, AC-7, AC-8; data §3.28.1/.2/.3 |
| `frontend/src/production-achievement/composables/useProductionAchievement.ts` | EDIT | Replace synchronous `runQuery()` (lines 150-176): GET `/report` → **200 spool-hit** → hand `spool_download_url`+maps to `useProductionAchievementDuckDB` and render; **202** `{job_id, status_url}` → drive `useAsyncJobPolling`; on `finished` re-issue the identical GET `/report` (now 200 spool-hit at zero Oracle cost — data §3.28.4) then activate DuckDB; **503** → surface worker-unavailable error. Add async progress/empty/error state. `saveTarget()` re-query (lines 178-207): re-issue the async report OR recompute client-side from the cached spool + refreshed `targets_map` (targets PUT itself unchanged). Preserve filters/filter-options/targets logic. | AC-1, AC-2, AC-8, AC-9 |
| `frontend/src/production-achievement/App.vue` | EDIT | Wire the new async job/poll/progress + empty + error states into the template; render the table from DuckDB-computed rows; loading→progress indicator; empty spool→empty table (not error); 503/error→error banner. Reuse existing shared async progress/loading components — NO new CSS tokens/classes (else promote CSS/UI to a required contract). | AC-2, AC-9; ui-change |
| `frontend/src/core/endpoint-schemas.ts` | VERIFY/EDIT | If `/report` has a registered response schema, update it for the 200 spool-hit shape (`query_id`, `spool_download_url`, `spec_workcenter_map`, `targets_map`) and the 202 async envelope; otherwise no edit. | AC-2; data §3.28.4 |

## Contract Updates

Contracts are already authored (contract-reviewer / spec-architect / test-strategist). Implementers
MUST keep code and generated artifacts in sync — they do NOT re-author prose.

- API: `contracts/api/api-contract.md` (+ `api-inventory.md`) — `/report` 202/200-spool-hit/503 + `status_url`. Sync BOTH `contracts/api/openapi.json` AND the root `contracts/openapi.json` mirror; regenerate response samples for the 202 + 200 shapes.
- CSS/UI: none — async states reuse existing shared components; no new governed CSS source.
- Env: `contracts/env/env-contract.md` §Worker Feature-Flag Env-Var Parity; `env.schema.json` (flag `enum`+`default`); `.env.example.template` + root `.env.example`. Verify the 3 `PRODUCTION_ACHIEVEMENT_*` vars are present with pinned defaults; do not drift code from them.
- Data shape: `contracts/data/data-shape-contract.md` §3.28 — SPECNAME-grain parquet `(output_date, shift_code, SPECNAME, actual_output_qty)` + `_PA_SPOOL_SCHEMA_VERSION`; §3.25 retained as parity-golden row shape only.
- Business logic: `contracts/business/business-rules.md` PA-01..PA-07 — PA-06/PA-07 compute LOCATION moves backend→frontend; semantics unchanged.
- CI/CD: `contracts/ci/ci-gate-contract.md` — new `deploy/mes-dashboard-production-achievement-worker.service` + worker env-parity (ci-cd-gatekeeper).

## TDD Sequence (write failing-first, then implement)

Bounded ladder for every phase: `cdd-kit test select` → `cdd-kit test run --phase <collect|targeted|changed-area|contract>`. Floor is always **collect / targeted / changed-area**; add **contract** (api+data+env changed) and **quality** if configured. Full suite runs at CI. See test-plan.md §Test Execution Ladder — do not restate.

Backend:
1. Route branches — write `tests/test_production_achievement_routes.py::TestReportRoute` (202 miss / 200 spool-hit shape / 503 no-worker / unconditional injection / never-calls-`read_sql_df`) failing, mocking `is_async_available()`+enqueue fn (CI has no Redis) → implement IP-3.
2. **Chunk-seam re-aggregation (HIGHEST-VALUE unit test)** — write `tests/test_production_achievement_unified_job.py::TestChunkSeamReaggregation` with a fixture whose one `(output_date, shift_code, SPECNAME)` group has `TRACKOUTTIMESTAMP` rows in BOTH pre-midnight (chunk-1) and post-midnight (chunk-2); assert exactly ONE row after `post_aggregate` → implement the re-aggregating `post_aggregate` (IP-1).
3. Worker structure — `TestSpoolSchema` (columns + `_SCHEMA_VERSION`), `TestProductionAchievementJob` (`always_async` registered, `pre_query` builds TIME chunks with no direct `read_sql_df`, run wraps heavy-query slot) → finish IP-1/IP-2.
4. Infra whitelists — extend `tests/test_query_cost_policy.py` `_APPROVED_CALLERS["base_chunked_duckdb_job"]`; add `tests/test_job_registry.py::TestAlwaysAsyncField` method (do NOT bump the 12-count); extend `tests/test_spool_routes.py` allowed-namespaces param → implement IP-4.
5. Env — `tests/contract/test_env_production_achievement_unified_flag.py` + `tests/test_env_contract.py::test_production_achievement_async_env_vars_pinned_defaults` + gunicorn↔worker parity (use `monkeypatch.setattr`, module-level constants) → implement IP-5.
6. Service golden — update `tests/test_production_achievement_service.py` to pin `build_achievement_rows()` as test-only golden (IP-2).
7. Integration/resilience/data-boundary (nightly `integration_real`) — `tests/integration/test_production_achievement_rq_async.py` (enqueue→job→spool round-trip + dual-tier parquet business-key diff vs golden) and `tests/integration/test_production_achievement_resilience.py` (empty-parquet, Oracle/Redis/timeout/missing-spool).

Frontend:
1. `frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts` (rollup groups by workcenter_group; target join yields rate; missing target→null; zero target→null not Infinity; zero actual+nonzero target→0.0; empty spool→empty table; activation threshold=0) failing → implement IP-6.
2. Dual-tier parity — extend `tests/test_frontend_duckdb_parity.py` + add `tests/test_frontend_production_achievement_parity.py` + PA cases in `tests/fixtures/frontend_compute_parity.json` (Node subprocess vs real TS formula) → confirms IP-6 matches golden.
3. E2E — `frontend/tests/playwright/production-achievement-async.spec.ts` (async flow / empty / error), mirroring resource-history-async → after IP-7 (build `dist/` first).

## Constraints / Gotchas (hand to implementers)

- Heavy-query slot is INHERITED from `BaseChunkedDuckDBJob.run()` — no manual `acquire_heavy_query_slot`; but the worker MUST be in the `_APPROVED_CALLERS["base_chunked_duckdb_job"]` whitelist (AC-4), else `test_query_cost_policy` fails.
- Job-registry count test MUST NOT be bumped — worker-registered types are excluded from the 12-count in `TestJobServiceRegistrations`; add a `TestAlwaysAsyncField` method only (eap-alarm/resource-history precedent).
- Route unit tests mock `is_async_available()=True` + the enqueue fn (CI has no Redis); the real enqueue→spool round-trip is deferred to the nightly `integration_real` gate (`pytestmark = pytest.mark.integration_real`).
- Hyphen/underscore split: spool namespace + `/api/spool/...` path + `_ALLOWED_NAMESPACES` use `production_achievement` (underscore); job type + `status_url` prefix use `production-achievement` (hyphen). Do not conflate.
- SPECNAME join key MUST match exactly on both sides: backend `str(specname).strip().upper()` == frontend `UPPER(TRIM(SPECNAME))`; a mismatch silently drops rows and fails the parity diff.
- Empty / all-unmapped-SPECNAME window: worker still writes a valid empty parquet with the exact §3.28.1 schema; browser renders an empty table, never an error (data §3.28.1 empty-result invariant).
- `_PA_SPOOL_SCHEMA_VERSION` participates in the spool key; ordinary bumps orphan stale parquets by key, but a schema-BREAKING bump must add `rm -f tmp/query_spool/production_achievement/*.parquet` to the rollback runbook in the same commit (cache-spool-patterns).
- Env parity: the systemd worker unit relies solely on the shared `EnvironmentFile`; it MUST NOT hardcode a `*_USE_UNIFIED_JOB`/`*_USE_RQ` `Environment=` override — the `worker-env-parity-static` gate greps for exactly that (ci-gates.md §Workflow Changes). Flags are frozen at boot in both processes.
- `_ALLOWED_NAMESPACES`, `_APPROVED_CALLERS`, and the `always_async` registry assertion land in the SAME PR as the worker/spool-write.
- Build `dist/` (`npm run build`) before Playwright — local specs serve pre-built `dist/`, not live source. Playwright `page.route()` is LIFO — register catch-all routes first, specific routes last.
- Concurrent backend+frontend agents both calling `cdd-kit test run` race on `test-evidence.yml` — the last agent must re-run combining both stacks' commands.
- A full pytest run regenerates the whole contract sample set — `git checkout tests/contract/samples/`, then re-stage only this change's samples (202 + 200 shapes).

## Test Execution Plan

Full AC→test mapping and update contract live in test-plan.md §AC→Test Mapping / §Test Update Contract — this table is the `cdd-kit test select` fallback only.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_production_achievement_routes.py | 202 + job_id on spool miss; no request-path `read_sql_df` |
| AC-1/AC-7 | tests/test_production_achievement_unified_job.py | chunk-seam group → exactly one row; TIME-chunk pre_query |
| AC-2/AC-8 | tests/test_production_achievement_routes.py | 200 spool-hit shape has spool_download_url+maps, injected unconditionally |
| AC-3 | tests/test_spool_routes.py | production_achievement in allowed namespaces; unknown rejected |
| AC-4 | tests/test_query_cost_policy.py | worker in `_APPROVED_CALLERS` |
| AC-4 | tests/test_job_registry.py | always_async registered; 12-count NOT bumped |
| AC-5 | tests/contract/test_env_production_achievement_unified_flag.py | 3 vars pinned defaults; gunicorn↔worker flag-name parity |
| AC-5 | tests/test_env_contract.py | `PRODUCTION_ACHIEVEMENT_*` defaults pinned |
| AC-6 | tests/test_production_achievement_unified_job.py | parquet columns + `_SCHEMA_VERSION` pinned |
| AC-7 | tests/test_frontend_production_achievement_parity.py | DuckDB rollup+join business-key diff vs golden |
| AC-7 | tests/test_frontend_duckdb_parity.py | achievement_rate formula matches backend |
| AC-7/AC-8 | frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts | rollup/join/rate guards; empty spool; threshold=0 |
| AC-7 (nightly) | tests/integration/test_production_achievement_rq_async.py | real-path parquet business-key diff vs `build_achievement_rows()` |
| AC-9 | frontend/tests/playwright/production-achievement-async.spec.ts | async flow + empty + error states render |
| AC-9 | tests/integration/test_production_achievement_resilience.py | empty-parquet / Redis-down 503 / timeout / missing-spool |

CI gate reference: ci-gates.md §Required Gates (`unit-mock-integration`, `worker-env-parity-static`, `dual-tier-parity`, `frontend-unit`, `production-achievement-async-e2e`, `playwright-*`, `css-governance` block merge; stress/soak are Tier-4 pre-activation). Do not duplicate here.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- The worker MUST subclass the existing `BaseChunkedDuckDBJob` and reuse `query_spool_store` / `async_query_job_service` / `spool_routes` / frontend `duckdb-client` + `useAsyncJobPolling` — no bespoke async machinery (change-request §Constraints).

## Known Risks

- Chunk-seam re-aggregation is the single correctness lynchpin — a plain-concat `post_aggregate` would pass a naive "rows exist" test but silently duplicate keys across midnight seams. The `TestChunkSeamReaggregation` fixture is the tripwire; prioritize it.
- Backend `str(specname).strip().upper()` vs frontend `UPPER(TRIM(SPECNAME))` divergence would drop rows without erroring — only the dual-tier parity diff catches it.
- Inline `spec_workcenter_map` payload size is bounded (SPECNAMEs low hundreds) but unbounded in principle — confirm cardinality during implementation (design.md §Open Risks).
- `.cdd/code-map.yml` (generated 2026-07-08, cdd-kit 3.6.0) was consulted for line ranges; if it drifts before implementation, re-read the cited ranges. `_APPROVED_CALLERS` was confirmed absent from `core/query_cost_policy.py` symbols — treat design.md's Affected-Components row for that file as "test-file whitelist", not a code edit, unless a policy classification is genuinely required.
- Deferred-to-implementation decisions (design.md §Open decisions): exact spool TTL, concrete queue/job-type/timeout values, chunk width (per-day vs N-day; correctness is seam-safe either way), and `targets_map` JSON serialization shape (§3.28.3 fixes it to a list of `{shift_code, workcenter_group, target_qty}` rows).
