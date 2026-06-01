# Design: batch-rowcount-unification

## Summary
This change unifies all large-query report services onto a single `BatchQueryEngine → execute_plan → merge_chunks_to_spool → Spool Parquet` path, eliminating the divergent direct-Oracle→spool path that `downtime_analysis_service` currently uses. It introduces a `USE_ROW_COUNT_CHUNKING` env flag (default `false`) that switches the six already-engine-backed services from fixed date-range chunking (`grain_days=31`) to fixed-row-count chunking via a `ROW_NUMBER() CTE + rn BETWEEN :start AND :end` paged SQL, giving each chunk uniform memory footprint. It also adds `HOLD_/JOB_/MSD_ENGINE_PARALLEL` settings. `downtime_analysis` is migrated onto `execute_plan` for path uniformity and progress tracking, but is permanently excluded from row-count chunking because its Python global reductions cannot tolerate chunk seams (see ADR-0003).

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Batch engine | `src/mes_dashboard/services/batch_query_engine.py` | add `decompose_by_row_count`; flag-gated dispatch between date-range and row-count plans (BQE-02, BQE-04) |
| Downtime service | `src/mes_dashboard/services/downtime_analysis_service.py` | replace direct `read_sql_df_slow`→spool with `execute_plan` whole-dataset dispatch; merge/bridge become post-merge stage (BQE-07, ADR-0003) |
| Downtime SQL | `src/mes_dashboard/sql/downtime_analysis/base_events.sql` | reconcile ORDER BY with BQE-03 spool sort key; NO paged ROW_NUMBER() SQL added (ADR-0003) |
| Prod-history runtime | `src/mes_dashboard/services/production_history_sql_runtime.py`, `sql/production_history/` | add paged ROW_NUMBER() SQL (reuse existing `count_query.sql`); flag-gated path |
| Reject runtime | `src/mes_dashboard/services/reject_cache_sql_runtime.py`, `sql/reject_history/` | add count + paged ROW_NUMBER() SQL; flag-gated path |
| Resource / hold runtimes | `resource_history_sql_runtime.py`, `hold_history_sql_runtime.py`, `sql/resource/`, `sql/hold_history/` | add count + paged ROW_NUMBER() SQL; flag-gated path |
| Job / MSD runtimes | `job_query_service.py`, `mid_section_defect_service.py`, `msd_duckdb_runtime.py`, `sql/job_query/`, `sql/mid_section_defect/` | add count + paged ROW_NUMBER() SQL; add `*_ENGINE_PARALLEL` plumbing |
| Env contract | `contracts/env/env-contract.md`, `.env.*` | add `USE_ROW_COUNT_CHUNKING`, `HOLD_/JOB_/MSD_ENGINE_PARALLEL` (BQE-05 ceiling) — already updated |

## Key Decisions

**Single engine path for all services** — route every large query through `execute_plan → merge_chunks_to_spool` for uniform spool TTL, cleanup, and progress tracking. Rejected keeping downtime's bespoke direct-Oracle path: it duplicated spool-write logic and bypassed progress tracking.

**Row-count chunking behind a default-off flag** — `USE_ROW_COUNT_CHUNKING=false` preserves date-range chunking byte-for-byte (BQE-04), enabling per-service validation and zero-downtime rollback. Rejected immediate hard cutover: no safe fallback if a paged-SQL parity bug ships.

**`{start_row, end_row}` chunk dict (1-based inclusive)** — maps symmetrically to `rn BETWEEN :start_row AND :end_row`; first chunk is `start_row=1` not 0. Rejected `{offset, limit}` (0-based OFFSET/FETCH): forces boundary arithmetic and is harder to assert in seam tests.

**ROW_NUMBER() CTE paging over OFFSET/FETCH** — Oracle `OFFSET N ROWS` rescans 0..N for every later chunk (O(N) per chunk, quadratic over the job); ROW_NUMBER() lets the optimizer use the ORDER BY index and accepts `FIRST_ROWS(N)` hints. Cost noted: ROW_NUMBER() materializes the ordered set once per chunk (O(total)), still better than late OFFSET pages. Rejected keyset pagination: stateful cursor incompatible with stateless parallel dispatch.

**Pre-COUNT per service** — `SELECT COUNT(*)` with identical WHERE clause before decomposing; known `total_rows` enables full parallel dispatch of all chunks at once. Rejected streaming page-until-empty: serializes execution, eliminates parallelism benefit. BQE-06 race accepted: COUNT and paged fetches are not one transaction; concurrent inserts may drift total.

**Fully tie-breaking ORDER BY per service (BQE-03)** — each `ROW_NUMBER()` key must be total across the dataset. The downtime spool sort key (`OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC`) differs from `base_events.sql`'s current grouping ORDER BY (`HISTORYID, OLDSTATUSNAME, OLDREASONNAME, OLDLASTSTATUSCHANGEDATE`); backend-engineer must reconcile and pin with a sort-order test.

**downtime_analysis permanently excluded from `USE_ROW_COUNT_CHUNKING` (ADR-0003)** — `_merge_cross_shift_events` sums HOURS across contiguous fragments by `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)` within a 60s window; `_bridge_jobid` performs a cross-product overlap join — both are whole-dataset global reductions. Row-count chunking splits logical events at chunk seams → halved hours, silent bug. Downtime uses whole-dataset single-chunk dispatch with merge/bridge applied as a post-merge stage. Fallback for very large date ranges: HISTORYID-aligned partitioning (safe because merge keys never cross HISTORYID boundaries).

**Spool schema and namespace unchanged for downtime (BQE-07)** — `tmp/query_spool/downtime_analysis/`, column schema, and `DOWNTIME_BRIDGE_VERSION` cache key are all preserved (DA-06 unaffected). Rejected re-keying the spool: forces parquet purge with no benefit.

## Migration / Rollback

**Phase 0** (immediately deployable): add `HOLD_/JOB_/MSD_ENGINE_PARALLEL` env settings; behavior unchanged at default 1.

**Phase 1**: add count + paged ROW_NUMBER() SQL and flag-gated dispatch for the six engine-backed services; ship with `USE_ROW_COUNT_CHUNKING=false`. Validate per-service in staging by toggling the flag and running parity tests (BQE-01) before any production enable. Production enable requires all Tier 1+2 parity tests green (ci-gates.md §Promotion Policy).

**Phase 2**: migrate `downtime_analysis_service` onto `execute_plan` with whole-dataset dispatch and post-merge stage; independent of the row-count flag.

**Rollback**: set `USE_ROW_COUNT_CHUNKING=false` to instantly revert the six services (no redeploy). Downtime migration has no flag; rollback is a code revert. No spool parquet purge required for any service — schemas are preserved.

## Open Risks

- **Paged ROW_NUMBER() parity bugs at chunk seams are silent** — wrong row set, green happy-path tests. Mitigated by BQE-01 parity tests; pin a tie-stability fixture per service.
- **BQE-03 ORDER BY reconciliation for downtime** — if `base_events.sql` keeps the grouping sort while the spool expects the BQE-03 key, the spool sort is wrong but no error fires; backend-engineer must reconcile and pin with a sort-order test.
- **Whole-dataset downtime dispatch removes row-uniformity benefit** — very large date range could exceed memory; fallback is HISTORYID-aligned partitioning.
- **`ENGINE_PARALLEL` misconfiguration above `DB_SLOW_POOL_SIZE`** — silently saturates the slow pool; mitigated by BQE-05 env-validation test.
