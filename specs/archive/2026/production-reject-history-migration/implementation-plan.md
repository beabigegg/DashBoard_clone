---
change-id: production-reject-history-migration
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Implementation Plan: production-reject-history-migration

## Objective
Migrate Production History and Reject History primary queries from pandas hot-paths (BatchQueryEngine `execute_plan`/`merge_chunks_to_spool` + reject `execute_primary_query`) onto `BaseChunkedDuckDBJob` subclasses (P2 of query-dataflow-unification.md §3), flag-gated and default-off, with spool schema and all view endpoints UNCHANGED. Follow the P1 `EapAlarmJob` pattern exactly (ADR-0009).

## Execution Scope

### In Scope
- Two new worker classes: `ProductionHistoryJob`, `RejectHistoryJob` (both `BaseChunkedDuckDBJob`, `ChunkStrategy.TIME`, row-level).
- Two feature flags (default `off`): `PRODUCTION_HISTORY_USE_UNIFIED_JOB`, `REJECT_HISTORY_USE_UNIFIED_JOB`.
- Route flag dispatch mirroring `eap_alarm_routes.py` L167-206 (`enqueue_query_job` on / legacy enqueue off).
- Remove AC-4 (6 post-hoc OOM guards) and AC-5 (route RSS sync-fallback pandas SELECT).
- Contract edits: env, business (ASYNC-07/08), ci (note), data-shape (unchanged assertion).
- Test wiring per test-plan.md.

### Out of Scope
- No frontend/Vue/CSS/i18n change; no view-endpoint behavior change (AC-8).
- No spool schema change (parquet columns identical to legacy).
- No new ADR; no change to `BaseChunkedDuckDBJob` core, `query_cost_policy.py` source, `oracle_arrow_reader.py`.
- No P3+ domains (resource/material-trace/downtime). No removal of legacy services (flag-off path must run verbatim).
- Do NOT add production_history to `spool_warmup_scheduler._WARMUP_JOBS` (on-demand only).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | tests (trip-wire) | Extend `_APPROVED_CALLERS` + add registry/shell tests (RED first) | backend-engineer |
| IP-2 | contracts/env + flags | Add 2 flags to env contract + schema + .env examples; read via module-level constant | backend-engineer |
| IP-3 | workers | New `ProductionHistoryJob` + registry `always_async=False` | backend-engineer |
| IP-4 | workers | New `RejectHistoryJob` (DuckDB groupby/pareto/trend) + registry | backend-engineer |
| IP-5 | routes | Flag dispatch in production_history_routes; remove RSS sync-fallback pandas SELECT | backend-engineer |
| IP-6 | routes | Flag dispatch in reject_history_routes | backend-engineer |
| IP-7 | tests | Extend `_APPROVED_CALLERS` (see divergence note — lives in test, not source) | backend-engineer |
| IP-8 | contracts/business | Add ASYNC-07 + ASYNC-08; bump 1.23.0 | backend-engineer |
| IP-9 | contracts/ci | Gate compatibility note; bump 1.3.26→1.3.27 | backend-engineer |
| IP-10 | deploy | Add `deploy/mes-dashboard-production-history-worker.service` (new unit needed); reject reuses existing unit | backend-engineer |
| IP-11 | spool_routes | No new namespace (schema unchanged) — verify only; see note | backend-engineer |
| IP-12 | tests | Implement parity + ast-absence test bodies (AC-1/2/4/5) | backend-engineer |
| IP-13 | gate | Run test-evidence ladder; pass `cdd-kit gate` | backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| query-dataflow-unification.md | §3 P2 row; §4.1 hooks; §2.3 chunk table; §5.5 rollback | migration constraints |
| change-classification.md | AC-1..AC-8; Required Contracts | acceptance + contract scope |
| test-plan.md | AC→test map; "Test Files"; Parity Strategy; Notes | tests to write/run |
| ci-gates.md | Required Gates; Rollback/Promotion; Deploy Checklist | verification + deploy |
| cache-spool-patterns.md | `_ALLOWED_NAMESPACES` rule; Type-B brackets | namespace + progress |
| `workers/eap_alarm_worker.py` L285-528 | EapAlarmJob class + `execute_*_unified_job` + `register_job_type` | exact pattern to copy |
| `routes/eap_alarm_routes.py` L167-206 | flag dispatch branch | IP-5/IP-6 template |

## Investigation Findings (answers to the 5 questions)
1. **Production History chunked path already exists** — `production_history_service._run_oracle_to_spool` (L607-688) uses `batch_query_engine.decompose_by_time_range`/`decompose_by_row_count` + `execute_plan` + **pandas** `merge_chunks_to_spool`. `production_history_job_service.execute_production_history_job` (L93-139) just calls `query_production_history(params)`. This is the legacy pandas chunked path P2 REPLACES — `ProductionHistoryJob` must be written from scratch on `BaseChunkedDuckDBJob` (do NOT wrap BQE). SQL grain = raw per-partial rows (`main_query.sql`). Keep `make_canonical_spool_id` as the deterministic `query_id`.
2. **The 6 post-hoc OOM guards (AC-4):** `reject_dataset_cache.py` — (a) `pd.read_parquet(...)` L747, (b) `pd.read_parquet(...)` L1170, (c) `raise RejectPrimaryQueryOverloadError(...)` L294, (d) `raise RejectPrimaryQueryOverloadError(...)` L961, (e) `_enforce_interactive_memory_guard(filtered, ...)` L1864 (+ helper L387-395 calling `interactive_memory_guard.enforce_dataset_memory_guard`). `reject_history_service.py` — (f) the post-load pandas `groupby` aggregations (L921 trend, L950 reason-pareto, L1049 lot-daily) that the OOM guards protect. Replace all with in-DuckDB SQL on the spool (read via DuckDB `read_parquet`, never `pd.read_parquet` into heap). Prove removal with ast/grep absence test per test-plan §AC-4.
3. **RSS sync-fallback (AC-5):** `production_history_routes.py` L270-298 "Sync fallback (RQ unavailable or async disabled)" branch calls `query_production_history(body)` synchronously inside gunicorn → full Oracle BQE pandas load. Remove the large-range pandas SELECT from this branch: the degraded path must either go through chunk-to-spool (unified job) or return 503; the spool-hit branch (L222-239) which only re-reads an existing spool via DuckDB sql_runtime is allowed to stay. `record_memory_error(..., reason="rss_guard")` at L227/275 are the RSS guard markers.
4. **Production-history worker deploy gap:** queue `production-history-query` already exists in `worker_pool_manager` (L52), `rq_monitor_service._QUEUE_NAMES` (L27), and `production_history_job_service.PRODUCTION_HISTORY_WORKER_QUEUE`. But **no `deploy/mes-dashboard-production-history-worker.service` exists** (only reject/trace/msd/downtime/hold/eap-alarm/material-consumption units). IP-10: add a new unit modeled on `deploy/mes-dashboard-eap-alarm-worker.service`, running `rq worker "${PRODUCTION_HISTORY_WORKER_QUEUE:-production-history-query}"`. Reject reuses `deploy/mes-dashboard-reject-worker.service` (`reject-query` queue) — no new unit.
5. **SQL files:** `sql/production_history/` = `main_query.sql`, `main_query_paged.sql`, `count_query.sql`. `sql/reject_history/` = `primary.sql`, `count_query.sql`, `list.sql`, `list_paged.sql`, `summary.sql`, `trend.sql`, `reason_pareto.sql`, `dimension_pareto.sql`, `export.sql`, `filter_options.sql`, `reason_options.sql`, `package_options.sql`, `material_reason_option.sql`, `performance_daily.sql`, `performance_daily_lot.sql`. Chunk SQL reuses the per-domain primary/main_query (date-BETWEEN per chunk); aggregation SQL (summary/trend/pareto) moves into DuckDB `post_aggregate`.

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `tests/test_query_cost_policy.py` | edit | Add `production_history_worker`,`reject_history_worker` to `_APPROVED_CALLERS["base_chunked_duckdb_job"]` (L336-338). RED until workers exist (IP-1) |
| `tests/test_async_query_job_service.py` | edit | Add 2 `*_registered_always_async_false` tests |
| `tests/test_production_history_unified_job.py` | create | shells then bodies (test-plan §Test Files) |
| `tests/test_reject_history_unified_job.py` | create | incl. AC-4 ast-absence tests |
| `tests/test_production_history_routes.py` | edit | add `test_rss_pandas_fallback_branch_absent_in_ast` (AC-5) |
| `tests/integration/test_production_history_rq_async.py` | create | parity, mock at Oracle/Redis boundary |
| `tests/integration/test_reject_history_rq_async.py` | create | parity + pareto endpoint shape |
| `src/mes_dashboard/core/feature_flags.py` | none | generic helper; flags read as module-level constants in routes |
| `contracts/env/env-contract.md` | edit | 2 rows after L81 EAP row; bump 1.0.15 |
| `contracts/env/env.schema.json` | edit | add 2 flag properties |
| `contracts/env/.env.example.template`, `.env.example` | edit | add 2 flags = off |
| `src/mes_dashboard/workers/production_history_worker.py` | create | `ProductionHistoryJob` + `execute_production_history_unified_job` + `register_job_type` |
| `src/mes_dashboard/workers/reject_history_worker.py` | create | `RejectHistoryJob` + entry + `register_job_type` |
| `src/mes_dashboard/services/job_registry.py` | none | register at worker module bottom (eap pattern) |
| `src/mes_dashboard/routes/production_history_routes.py` | edit | flag dispatch (L241-298); remove RSS pandas SELECT |
| `src/mes_dashboard/routes/reject_history_routes.py` | edit | flag dispatch (L708-743) |
| `contracts/business/business-rules.md` | edit | ASYNC-07/08; bump 1.23.0 |
| `contracts/ci/ci-gate-contract.md` | edit | note; bump 1.3.26→1.3.27 |
| `contracts/data/data-shape-contract.md` | edit | spool-schema-UNCHANGED assertion |
| `deploy/mes-dashboard-production-history-worker.service` | create | model on eap-alarm unit (IP-10) |
| `contracts/CHANGELOG.md` | edit | one entry per contract version bump |

## Contract Updates
- API: none (view endpoints + 503 unchanged).
- CSS/UI: none.
- Env: `PRODUCTION_HISTORY_USE_UNIFIED_JOB`, `REJECT_HISTORY_USE_UNIFIED_JOB` — feature, default `off`, "Restart required", default-value pinned (mirror EAP row at env-contract L81). Bump schema-version + CHANGELOG.
- Data shape: assert spool parquet schema UNCHANGED for both `production_history` and `reject_dataset` namespaces (explicit non-goal note).
- Business logic: ASYNC-07 (unified-job dispatch: `<DOMAIN>_USE_UNIFIED_JOB=on` → `enqueue_query_job` BaseChunkedDuckDBJob; off → legacy verbatim; `always_async=False`). ASYNC-08 (OOM guard shifts from post-hoc pandas guard to pre-emptive DuckDB on-disk spill). Bump schema-version + CHANGELOG.
- CI/CD: gate-compatibility note for the two new workers + flag-off legacy coverage; patch bump 1.3.27.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/test_production_history_unified_job.py` | spool row-level parity vs legacy |
| AC-2 | `tests/test_reject_history_unified_job.py` | DuckDB groupby/pareto/trend numeric parity ≤1e-6 |
| AC-3 | `tests/test_production_history_unified_job.py`, `tests/test_reject_history_unified_job.py` | flag-off routes to legacy |
| AC-4 | `tests/test_reject_history_unified_job.py` | ast: zero len(df)/memory_usage raise guards |
| AC-5 | `tests/test_production_history_routes.py` | ast: no large-range pandas SELECT in fallback |
| AC-6 | `tests/test_async_query_job_service.py` | registry `always_async=False` |
| AC-7 | `tests/test_query_cost_policy.py` | `_APPROVED_CALLERS` includes both workers |
| AC-8 | `tests/e2e/test_production_history_e2e.py`, `tests/e2e/test_reject_history_e2e.py` | green both flag states |
| AC-1+AC-2 | `tests/integration/test_production_history_rq_async.py`, `tests/integration/test_reject_history_rq_async.py` | RQ spool parity (nightly) |

Required phases (floor): collect, targeted, changed-area. Generate via `cdd-kit test select production-reject-history-migration --json` then `cdd-kit test run`. Full ladder in test-plan.md.

## Divergences from P1 / EapAlarmJob pattern (flag for backend-engineer)
- **IP-7 misdirection:** `_APPROVED_CALLERS` lives in `tests/test_query_cost_policy.py` (L336), NOT in `core/query_cost_policy.py` source. The AC-7 edit is the test extension in IP-1 — there is no `_APPROVED_CALLERS` in source. Do not add a callers set to source.
- **Production History is NOT 80% there like EAP:** it has a full pandas BQE chunked path (`_run_oracle_to_spool`) that must be replaced, not wrapped. `requires_cross_chunk_reduction=False` (row-level detail, multi-parquet append) like EapAlarm.
- **Reject History needs `requires_cross_chunk_reduction=True`:** summary/trend/pareto are cross-row aggregations — chunk rows into shared job DuckDB, then `post_aggregate` GROUP BY in DuckDB SQL and COPY to spool. Still row-level chunkable by TIME (not an ADR-0003 exclusion).
- **Two pre-existing registrations to reconcile:** `production_history_job_service.py` L147 and `reject_query_job_service.py` L195 already `register_job_type` legacy worker_fns. Decide: register the unified job under a NEW job_type (preferred — keeps legacy intact for flag-off) OR repoint via the flag in the route. The route flag branch should pick worker_fn (eap pattern keeps both registrations).
- **`always_async=False`** for both (AC-6) — differs from EapAlarm (`always_async=True`); route passes `sync_fallback_allowed=True`.
- **`progress_report` override** must call `update_job_progress("production_history"|"reject", ...)` with the correct Redis prefix (eap uses `"eap-alarm"`; prod legacy prefix is `"production_history"`, reject is `"reject"`).

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into code — follow source pointers.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- ci-gates.md names test files `test_production_history_worker.py` / `test_reject_history_worker.py`; test-plan.md (authoritative) uses `..._unified_job.py`. Use the `_unified_job` names.

## Known Risks
- **`reject_query_job_service.py` is NOT in context-manifest Allowed Paths** but is the existing reject registration site. The unified job belongs in `workers/reject_history_worker.py` (allowed). If editing `reject_query_job_service.py` is required, file a Context Expansion Request first.
- IP-11: production_history spool namespace `"production_history"` is absent from `spool_routes._ALLOWED_NAMESPACES` (L20-28); reject `"reject_dataset"` is present. P2 introduces NO new namespace, so IP-11 is verify-only — add `"production_history"` ONLY if the unified flow exposes a new spool-download path (it should not).
- Reject `post_aggregate` DuckDB SQL must reproduce pandas groupby NULL-handling (NULL `EQUIPMENT_ID` survives groupby) and deterministic pareto ordering — top parity risk (test-plan §AC-2 fixtures).
- Code-map generated 2026-06-19 (current); pointers verified against source.
