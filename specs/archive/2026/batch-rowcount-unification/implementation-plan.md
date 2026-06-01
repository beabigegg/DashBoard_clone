---
change-id: batch-rowcount-unification
schema-version: 0.1.0
last-changed: 2026-06-01
---

# Implementation Plan: batch-rowcount-unification

## Objective
Unify all 7 large-query report services onto `BatchQueryEngine → execute_plan → merge_chunks_to_spool → Spool Parquet`. Add a default-off `USE_ROW_COUNT_CHUNKING` flag that switches the 6 engine-backed services from date-range chunking to `ROW_NUMBER() CTE` row-count paging; migrate `downtime_analysis_service` onto `execute_plan` (whole-dataset, no flag); add HOLD/JOB/MSD engine-parallelism env vars. Deliver test-first (red → green) per `test-plan.md`.

## Execution Scope

### In Scope
- Phase 0: 3 ENGINE_PARALLEL env entries (env files only)
- Phase 1: `decompose_by_row_count` + `BATCH_QUERY_ROWS_PER_CHUNK`; flag-gated row-count branch in 6 services + paired SQL runtimes; 11 new SQL files (12 minus the reused production_history count_query.sql); env entries for `USE_ROW_COUNT_CHUNKING=false` and `BATCH_QUERY_ROWS_PER_CHUNK=50000`
- Phase 2: downtime_analysis migration to `execute_plan` whole-dataset dispatch; `base_events.sql` ORDER BY reconciliation to BQE-03

### Out of Scope
- `yield_alert_dataset_cache`, `material_trace_service`, `material_consumption_service` — do NOT modify (AC-8)
- Any frontend file; any API endpoint shape; any DB schema
- Re-authoring env-contract.md BQE rows / business-rules.md BQE-01..07 (already written)
- Adding paged ROW_NUMBER() SQL for downtime (ADR-0003 forbids it)
- Any spool namespace, cache-key, or parquet-schema change (BQE-07 / AC-5 / DA-06 — all UNCHANGED)
- `DOWNTIME_ENGINE_PARALLEL` — NOT in env-contract.md; do not add until contract gap is closed (see Known Risks)

## Required Changes

| id | area | required action |
|---|---|---|
| IP-1 | env (Phase 0) | Add HOLD/JOB/MSD_ENGINE_PARALLEL=1 to `.env`, `.env.example`, `.env.production`, `.env.development`, `contracts/env/.env.example.template`; mirror existing REJECT_ENGINE_PARALLEL convention |
| IP-2 | engine | Add `decompose_by_row_count(total_rows, rows_per_chunk=50000)` → list of `{start_row, end_row}` 1-based inclusive (BQE-02); add `BATCH_QUERY_ROWS_PER_CHUNK` env (default 50000) |
| IP-3 | engine | Flag-gated dispatch reading `USE_ROW_COUNT_CHUNKING`; flag-off path byte-for-byte unchanged (BQE-04) |
| IP-4 | SQL (×6 svc) | Add `count_query.sql` + `*_paged.sql` per service (production_history reuses existing count_query.sql → add only `main_query_paged.sql`); paged SQL uses `ROW_NUMBER() OVER (ORDER BY <BQE-03 key>) AS rn` + `WHERE rn BETWEEN :start_row AND :end_row` |
| IP-5 | services (×6) | Flag-gated row-count branch: count SQL → `decompose_by_row_count` → `execute_plan` with paged query_fn; existing date-range branch untouched |
| IP-6 | downtime (Phase 2) | Replace `read_sql_df_slow`→`store_downtime_events` with `execute_plan` whole-dataset → `merge_chunks_to_spool` → `register_spool_file`; apply `_merge_cross_shift_events` + `_bridge_jobid` as post-merge stage (BQE-07, ADR-0003) |
| IP-7 | downtime SQL | Reconcile `base_events.sql` ORDER BY to BQE-03 key (`OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC`); pin with sort-order test; NO paged ROW_NUMBER() |
| IP-8 | env (Phase 1) | Add `USE_ROW_COUNT_CHUNKING=false` + `BATCH_QUERY_ROWS_PER_CHUNK=50000` to all env files + template |
| IP-9 | CHANGELOG | Add version entries to `contracts/CHANGELOG.md` ONLY (never individual contract files per CLAUDE.md) |

## Source Artifact Pointers

| source | relevant pointer |
|---|---|
| `test-plan.md` | §Test Names — exact class/method names to write red-first |
| `test-plan.md` | §Notes — mock at read_sql_df/execute_plan; per-kwarg asserts; mid-group boundary fixture discipline |
| `ci-gates.md` | §Required Gates — PR verification commands |
| `ci-gates.md` | §Promotion Policy — flag=true production-enable preconditions (do NOT enable in CI) |
| `design.md` | §Key Decisions — 1-based inclusive dict; ROW_NUMBER vs OFFSET; pre-COUNT; ADR-0003 |
| `design.md` | §Migration/Rollback — phased delivery + rollback semantics |
| `contracts/business/business-rules.md` | §BQE-01..07 (already written) — behavior reference; do not re-author |
| `contracts/business/business-rules.md` | §BQE-03 — per-service ORDER BY keys |
| `contracts/business/business-rules.md` | §DA-02/DA-03/DA-06 — downtime merge/bridge/cache-key invariants to preserve |
| `contracts/env/env-contract.md` | §Batch Query Engine — Row-Count Chunking; §Engine Parallelism (already written) — semantics + BQE-05 ceiling |
| `docs/adr/0003-downtime-rowcount-chunking-exclusion.md` | full downtime exclusion rationale |

## File-Level Plan

| path | change type | what changes |
|---|---|---|
| `src/mes_dashboard/services/batch_query_engine.py` | modify | add `decompose_by_row_count`; `BATCH_QUERY_ROWS_PER_CHUNK` env; flag-aware dispatch |
| `src/mes_dashboard/services/production_history_sql_runtime.py` | modify | flag-gated paged path; reuse count_query.sql |
| `src/mes_dashboard/sql/production_history/main_query_paged.sql` | add | ROW_NUMBER() paged (TRACKINTIMESTAMP ASC, CONTAINERID) |
| `src/mes_dashboard/services/reject_cache_sql_runtime.py` | modify | flag-gated paged path |
| `src/mes_dashboard/sql/reject_history/count_query.sql` | add | COUNT(*) identical WHERE |
| `src/mes_dashboard/sql/reject_history/list_paged.sql` | add | ROW_NUMBER() paged (TXN_DAY DESC, CONTAINERNAME ASC) |
| `src/mes_dashboard/services/resource_history_sql_runtime.py` | modify | flag-gated paged path |
| `src/mes_dashboard/sql/resource/count_query.sql` | add | COUNT(*) |
| `src/mes_dashboard/sql/resource/dataset_paged.sql` | add | ROW_NUMBER() paged (HISTORYID ASC, DATA_DATE ASC) |
| `src/mes_dashboard/services/hold_history_sql_runtime.py` | modify | flag-gated paged path |
| `src/mes_dashboard/sql/hold_history/count_query.sql` | add | COUNT(*) |
| `src/mes_dashboard/sql/hold_history/list_paged.sql` | add | ROW_NUMBER() paged (HOLDTXNDATE DESC, CONTAINERID ASC) |
| `src/mes_dashboard/services/job_query_service.py` | modify | flag-gated paged path + JOB_ENGINE_PARALLEL plumbing |
| `src/mes_dashboard/sql/job_query/count_query.sql` | add | COUNT(*) |
| `src/mes_dashboard/sql/job_query/job_list_paged.sql` | add | ROW_NUMBER() paged (CREATEDATE DESC, JOBID ASC) |
| `src/mes_dashboard/services/mid_section_defect_service.py` | modify | flag-gated paged path + MSD_ENGINE_PARALLEL plumbing |
| `src/mes_dashboard/services/msd_duckdb_runtime.py` | modify (if needed) | paged query routing |
| `src/mes_dashboard/sql/mid_section_defect/count_query.sql` | add | COUNT(*) |
| `src/mes_dashboard/sql/mid_section_defect/dataset_paged.sql` | add | ROW_NUMBER() paged (TRACKINTIMESTAMP ASC, CONTAINERID ASC) |
| `src/mes_dashboard/services/downtime_analysis_service.py` | modify | migrate to execute_plan whole-dataset + post-merge stage (BQE-07) |
| `src/mes_dashboard/services/downtime_analysis_cache.py` | modify (if needed) | register spool via merge_chunks_to_spool output; namespace UNCHANGED |
| `src/mes_dashboard/sql/downtime_analysis/base_events.sql` | modify | ORDER BY → BQE-03 key; no ROW_NUMBER() paging |
| `.env`, `.env.example`, `.env.production`, `.env.development` | modify | add USE_ROW_COUNT_CHUNKING=false, BATCH_QUERY_ROWS_PER_CHUNK=50000, HOLD/JOB/MSD_ENGINE_PARALLEL=1 |
| `contracts/env/.env.example.template` | modify | same 4 additions as .env.example |
| `contracts/CHANGELOG.md` | modify | env + business version entries ONLY here |

## Contract Updates
- **API**: none
- **CSS/UI**: none
- **Env**: `.env*` + `contracts/env/.env.example.template` entries only; env-contract.md var rows already authored — do not edit; CHANGELOG → `contracts/CHANGELOG.md` only
- **Data shape**: confirm-only — paged columns MUST equal date-range columns (AC-5); no edit unless drift found
- **Business logic**: BQE-01..07 already authored — do not edit; CHANGELOG → `contracts/CHANGELOG.md` only
- **CI/CD**: one step added to `backend-tests.yml` per `ci-gates.md §New Workflow Changes`

## Test Execution Plan

| criterion | test command | expected signal |
|---|---|---|
| AC-1 | `pytest tests/test_batch_query_engine.py::TestDecomposeByRowCount` + `::test_no_gap_no_overlap_property` | red first (function missing), then green |
| AC-2 | `pytest tests/integration/test_rowcount_flag_parity.py::TestFlagFalseRegression` | row-identical spool, all 7 services |
| AC-3 | `pytest tests/integration/test_rowcount_flag_parity.py::TestFlagTrueParity` + `tests/stress/test_chunk_boundary.py -k "TestChunkSeam or TestOrderByTieStability"` | same rowset; no seam drop/dupe |
| AC-4 | `pytest tests/test_downtime_analysis_service.py::TestDowntimeMigration` | execute_plan/merge_chunks_to_spool used; no direct Oracle→spool path |
| AC-5 | `pytest tests/integration/test_rowcount_flag_parity.py::TestSpoolSchemaParity` | identical column names both paths |
| AC-6 | `pytest tests/test_batch_query_engine.py::TestEngineParallelCeiling` + `tests/test_env_contract.py` | ceiling ≤ DB_SLOW_POOL_SIZE; 4 vars documented |
| AC-7 | `pytest tests/integration/test_rowcount_flag_parity.py::TestSpoolLifecycle` | TTL/cleanup unchanged |
| AC-8 | `pytest tests/test_batch_query_engine.py::TestExcludedServicesUnmodified` | yield_alert/material_trace not imported |

**Red-first requirement**: `TestDecomposeByRowCount` and `TestFlagFalseRegression` MUST fail in a clean clone before implementation starts (test-plan.md §Notes). Tier 3/4 (race/stress/soak) are nightly/weekly informational — not PR-blocking.

## Handoff Constraints
- Do not re-copy design, test, CI, or contract prose into code comments; reference Source Artifact Pointers
- Keep work within the File-Level Plan; new SQL stays inside the 6 named service dirs; any other path needs an approved Context Expansion Request
- If a required file, behavior, contract, or test is missing: stop and report `blocked`

## Known Risks
- **CONTRACT GAP**: `DOWNTIME_ENGINE_PARALLEL` (default 2) is NOT in env-contract.md. Do not silently add an undocumented env var. Downtime uses whole-dataset single-chunk dispatch (parallel=1), which needs no new env var — defer `DOWNTIME_ENGINE_PARALLEL` to a follow-up contract update.
- Silent ROW_NUMBER() seam bugs (wrong rowset, green happy path) — mitigated by TestChunkSeam + TestOrderByTieStability + mid-logical-group boundary fixture
- `base_events.sql` ORDER BY reconciliation fires no error if wrong — pin with sort-order test
- ENGINE_PARALLEL above DB_SLOW_POOL_SIZE silently saturates the slow pool — pinned by TestEngineParallelCeiling (BQE-05)
- Whole-dataset downtime dispatch loses row-uniformity for very large ranges — documented fallback: HISTORYID-aligned partitioning (design.md §Open Risks)
