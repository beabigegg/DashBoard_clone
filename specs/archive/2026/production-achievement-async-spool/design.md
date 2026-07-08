# Design: production-achievement-async-spool

## Summary
Migrate `/api/production-achievement/report` from a synchronous fast-pool Oracle
query (now DPY-4024 at 30-day windows) to the established async pattern: a
`BaseChunkedDuckDBJob` subclass fans Oracle out in TIME chunks and writes a
SPECNAME-grain DuckDB parquet spool; the route returns 202 + job_id, the browser
polls, downloads the parquet (option A), and runs PA-06 (SPECNAME→workcenter_group
rollup) and PA-07 (target join + achievement_rate) in DuckDB-WASM. This mirrors
`resource_history` and relocates PA-06/PA-07 compute backend→frontend
(ADR-0016). Feature is pre-launch → clean sync→async replacement, `always_async=True`,
no dual-path fallback and no `*_USE_RQ` gradual flag.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Worker (new) | `src/mes_dashboard/workers/production_achievement_worker.py` | CREATE — `ProductionAchievementJob(BaseChunkedDuckDBJob)`, `chunk_strategy=TIME`, `requires_cross_chunk_reduction=False` + re-aggregating `post_aggregate`; `always_async=True`; `register_job_type()` |
| Chunk SQL | `src/mes_dashboard/sql/production_achievement.sql` | REUSE (unchanged) — bound per-chunk via `start_date`/`chunk_end_excl`; PA-05 predicate preserved verbatim |
| PA service | `src/mes_dashboard/services/production_achievement_service.py` | EDIT — add canonical spool-key helper (`_PA_SPOOL_SCHEMA_VERSION`, date-range only); retain `build_achievement_rows()` as test-only golden; `get_achievement_report()` no longer on request path |
| Target service / filter_cache | `production_achievement_target_service.py`, `filter_cache.py` | REUSE — `get_targets_map()` + `get_spec_workcenter_mapping()` read server-side for inline injection |
| Route | `src/mes_dashboard/routes/production_achievement_routes.py` | EDIT — `/report` → spool-hit check → enqueue 202/poll; inject `spool_download_url` + `spec_workcenter_map` + `targets_map`; worker-registration import |
| Spool allowlist | `src/mes_dashboard/routes/spool_routes.py` | EDIT — add `production_achievement` to `_ALLOWED_NAMESPACES` |
| Cost policy | `src/mes_dashboard/core/query_cost_policy.py` | EDIT — add worker to `_APPROVED_CALLERS` |
| Env parity | `config/settings.py`, `gunicorn.conf.py`, `rq_worker_preload.py` | EDIT — new worker feature flag frozen identically in gunicorn + RQ worker; preload imports worker so job type registers |
| Frontend compute | `frontend/src/production-achievement/useProductionAchievementDuckDB.ts` (new), `App.vue` | CREATE/EDIT — async job/poll/progress states via `useAsyncJobPolling`; DuckDB-WASM rollup + target-join + rate; activation with `threshold` override |
| Activation policy | `frontend/src/core/duckdb-activation-policy.ts` | REUSE — PA passes `threshold=0`; shared default unchanged |
| Contracts | `api-contract.md`(+inventory+`openapi.json` mirrors), `data-shape-contract.md`, `env-contract.md`(+`env.schema.json`+`.env.example.template`+root `.env.example`), `business-rules.md` | EDIT — 202/poll/spool endpoint; SPECNAME-grain schema + `_SCHEMA_VERSION`; worker flag enum/default + parity; PA-06/PA-07 location note |
| Deploy | `deploy/mes-dashboard-production-achievement-worker.service` | CREATE — systemd worker unit matching existing conventions |
| Tests | `tests/test_production_achievement_unified_job.py`, `tests/integration/test_production_achievement_rq_async.py`, dual-tier parity fixture, `_APPROVED_CALLERS`/job-registry/allowlist/env-default tests, frontend duckdb unit, `frontend/tests/playwright/production-achievement-async.spec.ts` | CREATE — pointer-level; see test-plan.md |

## Key Decisions
- **Chunk-seam correctness (RESOLVED)**: `requires_cross_chunk_reduction=False` with
  calendar-day TIME chunks, BUT `post_aggregate` MUST re-aggregate
  (`GROUP BY output_date, shift_code, SPECNAME` `SUM(actual_output_qty)` over the
  globbed chunk parquets), NOT plain-concat. PA-03/PA-04's previous-day tail rule
  makes an `(output_date, shift, SPECNAME)` group draw from `TRACKOUTTIMESTAMP`s on
  both sides of a calendar-midnight seam, so the resource_history plain-concat merge
  would emit duplicate keys. `SUM` is seam-associative → one canonical row per key.
  → rejected `requires_cross_chunk_reduction=True`: correct but adds single-writer
  DuckDB lock contention for no benefit when chunk SQL already GROUP-BYs server-side.
  → rejected aligning chunk boundaries to the 07:30/08:00 shift-cut: fragile across
  the dual shift regime and TZ-sensitive. Pinned in ADR-0016.
- **Q1 activation threshold (RESOLVED: override to always-activate)**: PA passes
  `threshold=0` so DuckDB-WASM always activates; the route unconditionally injects
  `spool_download_url` whenever the spool exists (not gated on row-count). Single
  client compute path for PA-06/PA-07; WASM init (~100-300ms) is negligible against
  the async job wait and the tiny parquet.
  → rejected (b) server-side DuckDB aggregation fallback: reintroduces the exact
  spec→group rollup + target join the change removes and creates a second parity
  surface (Python vs SQL). → rejected a plain-JS-below-threshold path: second
  frontend compute implementation, doubling parity risk. WASM-unsupported browsers
  get an explicit unsupported state, not a hidden server rollup.
- **Q2 targets + mapping carrier (RESOLVED: inline injection)**: server injects
  `spec_workcenter_map` (SPECNAME→group, from `filter_cache`) and `targets_map`
  ((shift,group)→target_qty, from `get_targets_map()`) inline alongside
  `spool_download_url` at job completion, mirroring resource_history's
  `resource_metadata`. → rejected (ii) fetch from `/filter-options` + `/targets`:
  `/filter-options` exposes only group *enums*, not the per-SPECNAME mapping, so it
  can't supply PA-06 without a new endpoint; extra round-trips add a targets-edit
  race. → rejected (iii) new endpoint: needless contract surface. MySQL-OPS
  degradation preserved: OPS-off ships an empty/partial `targets_map` → frontend
  PA-07 yields null target/achievement_rate, never 500 (spec map is Oracle-backed,
  unaffected).
- **Q3 spool delivery (RESOLVED: option A)**: browser downloads the parquet from
  `/api/spool/production_achievement/<id>.parquet` into DuckDB-WASM; add the
  namespace to `_ALLOWED_NAMESPACES`. Consistent with Q1's always-activate and the
  compute-relocation goal. → rejected option B (server-side DuckDB read): same
  defeat-the-purpose server aggregation as Q1(b); only justified for a sub-threshold
  server path, which Q1(a) eliminates.
- **Compute-location move + parity**: PA-06/PA-07 relocate to browser DuckDB-WASM SQL.
  The dual-tier parity gate diffs the rendered rows `(output_date, shift_code,
  workcenter_group, actual_output_qty, target_qty, achievement_rate)` against
  `build_achievement_rows()` (retained as golden) for an identical date range, over
  the shared SPECNAME-grain spool + the two injected maps (AC-7).
- **Heavy-query slot (AC-4)**: `BaseChunkedDuckDBJob.run()` wraps the Oracle fan-out
  in `heavy_query_slot` automatically — the subclass inherits the semaphore for free;
  no per-worker acquire needed. Worker still added to `_APPROVED_CALLERS`.

## Migration / Rollback
Clean pre-launch replacement: the sync `/report` behavior is removed (no dual-path,
no back-compat) — `/report` now serves an existing spool immediately or enqueues
(202 + job_id); with `always_async=True` and no worker available it returns 503 (no
sync fallback), acceptable pre-launch. Worker, queue, systemd unit, job-registry
entry, `_APPROVED_CALLERS`, `_ALLOWED_NAMESPACES`, and the env feature flag ship in
one atomic PR (worker + route + frontend together). The SPECNAME-grain parquet key
carries `_PA_SPOOL_SCHEMA_VERSION`; a schema break bumps it AND adds `rm` of the
`production_achievement` spool dir to the rollback runbook in the same commit
(cache-spool-patterns). The worker flag must resolve identically in gunicorn and the
RQ worker (frozen at boot; `env.schema.json` enum + default; `.env` templates
updated). Rollback if the async path misbehaves in prod: because pre-launch there is
no data migration to undo — revert the atomic PR, remove the systemd unit, purge the
`production_achievement` spool namespace dir (`rm`), and unregister the namespace +
approved-caller. Disabling the worker leaves `/report` returning 503, which is safe
while the page is unexposed.

## Open Risks
- Empty-result / all-unmapped-SPECNAME window must still write a valid empty parquet
  (correct schema) so the browser renders an empty table, never an error.
- Payload size of inline maps is bounded (SPECNAMEs: low hundreds; targets: shift×group)
  — inline is safe, but confirm during implementation if SPECNAME cardinality grows.
- `.cdd/code-map.yml` was not consulted (not in read scope / not verified present);
  affected-components ranges were grounded by direct reads of the cited files.

## Open decisions deferred to implementation
- Exact spool TTL (reuse resource_history's historical-vs-recent split vs a flat value).
- Concrete worker feature-flag name, queue name, job-type string, and job timeout.
- Chunk width (per-day vs N-day) — pure throughput tuning; correctness is seam-safe
  either way given re-aggregating `post_aggregate`.
- JSON serialization shape of `targets_map` (tuple key → nested object vs list of rows).
