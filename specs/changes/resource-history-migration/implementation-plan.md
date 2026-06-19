---
change-id: resource-history-migration
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Implementation Plan: resource-history-migration

## Objective
Migrate resource-history query execution off the in-gunicorn full-DataFrame reads onto the unified `BaseChunkedDuckDBJob` pipeline, behind `RESOURCE_HISTORY_USE_UNIFIED_JOB` (default `off`). Ship TWO new chunked jobs — `ResourceHistoryBaseJob` (`requires_cross_chunk_reduction=False`) for shift/base facts and `ResourceHistoryOeeJob` (`requires_cross_chunk_reduction=True`) for OEE trackout+NG ratio-of-SUMs — both `ChunkStrategy.TIME`, writing the **same two existing spool files** (`resource_dataset`, `resource_oee`). When the flag is `on`, the export path enqueues both jobs and the `iterrows` OEE/yield computation moves to DuckDB SQL; the sync-fallback pandas SELECT is removed (degraded → 503). When `off`, every legacy path is byte-for-byte unchanged.

## Execution Scope

### In Scope
- New worker module(s) implementing the two jobs (see File-Level Plan; mirror `eap_alarm_worker.py`).
- Two new `register_job_type(...)` calls (base + OEE) at module import; route flag dispatch in the export endpoint (off→legacy `export_csv`, on→enqueue both unified jobs).
- Replace OEE `iterrows`/`groupby` (resource_history_service.export_csv lines 521-531, 612-617) and the per-row CSV stitch with a DuckDB SQL join over the two parquet spools, under flag=on only.
- Env / business / data-shape / CHANGELOG contract edits; `_APPROVED_CALLERS` extension; all new/extended tests (see Test Execution Plan).

### Out of Scope
- Frontend / Vue / Playwright (flag off, no UI change — classification Tasks-Not-Applicable 2.2/3.3/4.2/5.1/5.2).
- API contract edits (confirm-only; no response shape change).
- Modifying `execute_primary_query`'s legacy `batch_query_engine` path, `decompose_by_time_range`, or `_query_and_store_canonical_dataset` (legacy path must stay intact for AC-1).
- Adding `resource_oee` to `spool_routes._ALLOWED_NAMESPACES` (OEE spool is read internally via `get_spool_file_path`, never over `/api/spool/<ns>` HTTP — verify-only, do NOT add). `resource_dataset` is already whitelisted.
- New CI workflow files; stress/soak (deferred via tier-floor-override).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | worker | New `ResourceHistoryBaseJob(BaseChunkedDuckDBJob)`: `namespace="resource_dataset"`, `chunk_strategy=TIME`, `requires_cross_chunk_reduction=False`; `pre_query` builds whole-day TIME chunks; `build_chunk_sql` loads `base_facts.sql` and binds per-chunk `:start_date`/`:end_date` + `HISTORYID_FILTER`; `post_aggregate(None)` merges per-chunk parquets → `resource_dataset` spool (legacy column set). | backend-engineer |
| IP-2 | worker | New `ResourceHistoryOeeJob(BaseChunkedDuckDBJob)`: `namespace="resource_oee"`, `chunk_strategy=TIME`, `requires_cross_chunk_reduction=True`; each chunk's `build_chunk_sql` binds production `:start_date`/`:end_date` to chunk dates AND extends `:reject_start`/`:reject_end` ±30d around the chunk range; `post_aggregate(job_duckdb_path)` runs `GROUP BY EQUIPMENTID` ratio-of-SUMs in job-temp DuckDB → `resource_oee` spool. | backend-engineer |
| IP-3 | dispatch | Two `register_job_type(JobTypeConfig(...))` calls at module import (job types e.g. `resource-history-base`, `resource-history-oee`), `queue_name=RESOURCE_WORKER_QUEUE` (`resource-history-query`), `always_async=True` (mirror EapAlarm). Add RQ entry-point fns wrapping `Job.run()` + `complete_job`. | backend-engineer |
| IP-4 | route | In `api_resource_history_export` (resource_history_routes.py:377-450) add a module-level `RESOURCE_HISTORY_USE_UNIFIED_JOB` flag read; flag=on → enqueue both jobs via `enqueue_job_dynamic`, await both spools, stream CSV from spool join; if `not is_async_available()` → return 503 (AC-7). flag=off → unchanged `export_csv(...)` stream. | backend-engineer |
| IP-5 | service | Flag-gated DuckDB-SQL replacement of the OEE `groupby`+`iterrows` (resource_history_service.export_csv) reading from the two spools; legacy `iterrows` path retained for flag=off (AC-1/AC-4). Sync-fallback pandas SELECT removed from flag=on path (AC-7, ast.parse-provable). | backend-engineer |
| IP-6 | contracts | env flag default-pin (`off`, Restart) + `.env.example` + env.schema.json; ASYNC-09 in business-rules.md; spool-schema-UNCHANGED assertion in data-shape-contract.md; ci-gate-contract patch note; version entry → contracts/CHANGELOG.md only. | backend-engineer |
| IP-7 | tests | Extend `_APPROVED_CALLERS["base_chunked_duckdb_job"]` with the new worker module stem(s); write/extend all test files per Test Execution Plan. | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | "Key Design Decision: Job Topology" (TWO jobs); "requires_cross_chunk_reduction Decision"; "Open Risks" (±30d) | topology + flag constraints |
| test-plan.md | AC→Test Mapping table; "Test File Paths and Test Names"; "Data-Boundary Strategy" | tests to write |
| ci-gates.md | "Required Gates" table; "Promotion Policy"; "Deploy Checklist" #2/#3/#5 | verification + worker-unit env parity |
| change-classification.md | AC-1…AC-9; "Required Contracts" | acceptance + contract scope |
| eap_alarm_worker.py | `EapAlarmJob` (l.285) + `execute_eap_alarm_unified_job` (l.483) + `register_job_type` (l.521) | canonical pattern to mirror |
| base_chunked_duckdb_job.py | `run()` template l.192-232; `post_aggregate` contract l.131-146; `_fan_out_*` l.284+ | class contract |
| docs/architecture/cache-spool-patterns.md | §spool_routes._ALLOWED_NAMESPACES (l.113); Type-B brackets | namespace verify-only + progress |

## Investigation Findings

1. **Job service signature.** File is `src/mes_dashboard/services/resource_query_job_service.py` (NOT `resource_history_job_service.py` — that path in the manifest/tasks does not exist; see Divergences). It registers ONE legacy job type `"resource-history"` (l.196-203) via `register_job_type`, `queue_name=RESOURCE_WORKER_QUEUE` = env `RESOURCE_WORKER_QUEUE` default `"resource-history-query"` (l.39). Enqueue helper: `enqueue_resource_history_query(params, owner)` (l.78) → `enqueue_job_dynamic("resource-history", ...)`. Worker entry: `execute_resource_history_query_job(*, job_id, owner, **query_params)` (l.98), `should_enqueue=should_use_async` (l.53).
2. **SQL files.** `sql/resource_history/`: base/shift facts = `base_facts.sql` (`GROUP BY HISTORYID, TRUNC(TXNDATE)`, binds `:start_date`/`:end_date` + `{{ HISTORYID_FILTER }}` text token, l.15-30). OEE = `oee_facts.sql` (LOTWIPHISTORY⋈LOTREJECTHISTORY, `GROUP BY EQUIPMENTID, SHIFT_DATE`, output cols EQUIPMENTID/SHIFT_DATE/TRACKOUT_QTY/NG_QTY; binds `:start_date`/`:end_date` for production l.23-24 AND `:reject_start`/`:reject_end` for reject window l.39-40). **Both already date-parameterized** — chunk binds reuse existing names.
3. **iterrows loop.** In `resource_history_service.export_csv`: OEE side aggregates `oee_df.groupby('EQUIPMENTID').agg(TRACKOUT_QTY=sum, NG_QTY=sum)` then `iterrows` → `oee_by_equipment[EQUIPMENTID]={trackout_qty,ng_qty}` (l.521-531). Main `df.iterrows()` (l.578) computes per-HISTORYID: ou_pct, availability_pct=(prd+sby+egt)/(prd+sby+egt+sdt+udt+nst), per-status %, then `yield_pct=trackout/(trackout+ng)`, `oee_pct=availability*yield/100` (l.602-617). DuckDB replacement: `SUM` TRACKOUT/NG per EQUIPMENTID + ratio in SQL (matches `_calc_availability_pct`/yield formulas — required for AC-4 parity tests).
4. **Spool namespace constants.** In `resource_dataset_cache.py`: `_REDIS_NAMESPACE="resource_dataset"` (l.40), `_OEE_REDIS_NAMESPACE="resource_oee"` (l.41) — both already exist. `spool_routes._ALLOWED_NAMESPACES` (l.20-28) contains `resource_dataset` but NOT `resource_oee`. OEE spool is consumed internally (not via HTTP `/api/spool`), so `resource_oee` is correctly absent — verify-only, do not add (avoids scope creep + a failing `test_spool_routes` parametrize).
5. **Systemd worker unit.** No `deploy/` path in manifest/code-map for a resource-history unit; the worker reuses the existing **`resource-history-query`** RQ queue (`RESOURCE_WORKER_QUEUE`). Per ci-gates.md Deploy Checklist #5 / Rollback Policy, the existing `resource-history-query` systemd unit must export `RESOURCE_HISTORY_USE_UNIFIED_JOB` for gunicorn↔worker flag parity — flag this in the deploy note; do NOT create a new unit.

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/workers/resource_history_base_worker.py` | create | `ResourceHistoryBaseJob` + RQ entry fn + `register_job_type`. Mirror eap_alarm_worker.py structure. Module stem must match `_APPROVED_CALLERS`. |
| `src/mes_dashboard/workers/resource_history_oee_worker.py` | create | `ResourceHistoryOeeJob` + RQ entry fn + `register_job_type`. Per-chunk ±30d reject window in `build_chunk_sql`. |
| `src/mes_dashboard/routes/resource_history_routes.py` | edit | Add `RESOURCE_HISTORY_USE_UNIFIED_JOB` module const + flag dispatch in `api_resource_history_export` (377-450); 503 on no worker. |
| `src/mes_dashboard/services/resource_history_service.py` | edit | Flag-gated DuckDB-spool-join replacement of OEE groupby/iterrows; legacy path retained for flag=off. |
| `src/mes_dashboard/services/resource_query_job_service.py` | edit (optional) | If new job types are registered here instead of the worker modules, add the two `register_job_type` calls. Prefer registering in the worker modules (eap pattern). |
| `src/mes_dashboard/sql/resource_history/base_facts.sql`, `oee_facts.sql` | verify (no edit expected) | Already parameterized; only edit if per-chunk binds need a new alias (none anticipated). |
| `contracts/env/{env-contract.md,env.schema.json,.env.example.template}` | edit | Pin `RESOURCE_HISTORY_USE_UNIFIED_JOB` default `off`, Restart. |
| `contracts/business/business-rules.md` | edit | Add ASYNC-09. |
| `contracts/data/data-shape-contract.md` | edit | spool-schema-UNCHANGED assertion for resource_dataset + resource_oee parquet. |
| `contracts/ci/ci-gate-contract.md`, `contracts/CHANGELOG.md` | edit | Compat note; version entry (CHANGELOG only). |
| test files (per Test Execution Plan) | create/extend | see below. |

## Contract Updates
- API: none (confirm-only — no endpoint/response change).
- CSS/UI: none.
- Env: `contracts/env/env-contract.md` + `env.schema.json` + `.env.example.template` — `RESOURCE_HISTORY_USE_UNIFIED_JOB` default `off`, Restart required (env-default-pin test asserts `off`).
- Data shape: `contracts/data/data-shape-contract.md` — spool-schema-UNCHANGED for `resource_dataset` + `resource_oee` outputs (AC-6); no `_SCHEMA_VERSION` bump.
- Business logic: `contracts/business/business-rules.md` — ASYNC-09 (unified-job execution path + OEE cross-chunk-reduction semantics).
- CI/CD: `contracts/ci/ci-gate-contract.md` compat note; patch bump in `contracts/CHANGELOG.md` only.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_resource_history_service.py | flag=off export unchanged; `test_successful_export` still green |
| AC-2 / AC-3 / AC-4 / AC-6 | tests/test_resource_history_unified_job.py | chunk strategy=TIME, OEE reqs True/base False, ±30d seam parity ≤1e-6, iterrows→SQL parity, parquet cols unchanged |
| AC-5 | tests/test_resource_history_job_service.py | flag=on enqueues BOTH base+OEE in one call; flag=off uses legacy |
| AC-7 | tests/test_resource_history_service.py | flag=on + no worker → 503; ast.parse proves sync-fallback absent |
| AC-8 | tests/test_query_cost_policy.py | `_APPROVED_CALLERS` includes new worker stems; cost-policy green |
| AC-9 | tests/test_async_query_job_service.py | both job types registered (importlib.reload pattern) |
| AC-3 (parity, Tier 1) | tests/integration/test_resource_history_rq_async.py | base+OEE spool parity vs legacy (integration_real) |

Floor phases: collect, targeted, changed-area (test-plan.md / references/sdd-tdd-policy.md). Flag-toggle tests use `monkeypatch.setattr` on the module-level const (not setenv). Verify via `cdd-kit test run`.

## Divergences from P1/P2 EapAlarmJob pattern (for backend-engineer)
- **TWO jobs, not one.** EapAlarm is a single `requires_cross_chunk_reduction=False` job; here the OEE job is `True` (job-temp DuckDB `INSERT INTO raw` + `post_aggregate` GROUP BY) while base is `False` (multi-parquet append). Do not collapse into one job.
- **Service/file naming mismatch.** Manifest + tasks + design.md reference `resource_history_job_service.py`; the real file is **`resource_query_job_service.py`**. Register/dispatch against the real file. Do not create `resource_history_job_service.py`.
- **±30d reject window is per-chunk.** Unlike EapAlarm's uniform daily binds, each OEE chunk must widen `:reject_start`/`:reject_end` ±30d around its own production dates (single highest-risk item; data-boundary tests gate it).
- **Two enqueues per export.** EapAlarm enqueues one job; the export route here enqueues both and awaits both spools before streaming.
- **`always_async=True`** like EapAlarm (no day-threshold gate on the unified path); legacy `should_use_async` stays on the legacy `"resource-history"` job type.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Legacy path (flag=off) must remain byte-for-byte unchanged (AC-1): do not refactor `execute_primary_query`, `batch_query_engine`, or the existing `iterrows` while touching these files.

## Known Risks

- **OEE ±30d seam (highest).** Boundary NG lost if a chunk's reject sub-window is not widened; AC-3 seam fixtures (test-plan §Data-Boundary) must be green before flag promotion.
- **Spool join column parity.** DuckDB OEE ratio must reproduce `_calc_availability_pct` + yield formulas exactly (AC-4 ≤1e-6) — reuse the same SUM operands and division order.
- **`_APPROVED_CALLERS` gate.** Missing either new worker stem fails `test_query_cost_policy` (AC-8 / Deploy Checklist #3) — block worker ship until green.
- **Naming drift** between artifacts (`resource_history_job_service` vs real `resource_query_job_service`) risks a misplaced edit; backend-engineer must edit the real file.
- **Doubled queue traffic** (two RQ jobs/export) — acceptable while flag-gated; stress/soak deferred via tier-floor-override, prerequisite for flag-on (ci-gates Promotion Policy #3).
- Code-map generated 2026-06-19 (current); no staleness concern.
