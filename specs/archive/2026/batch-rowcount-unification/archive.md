---
change-id: batch-rowcount-unification
archived: 2026-06-01
pr: beabigegg/DashBoard_clone#3
status: merged
---

# Archive: batch-rowcount-unification

## Change Summary

Unified 7 large-query report services onto a consistent `BatchQueryEngine → execute_plan → merge_chunks_to_spool → Spool` pattern. Added `USE_ROW_COUNT_CHUNKING` flag (default `false`) that switches 6 engine-backed services from date-range chunking to `ROW_NUMBER() CTE` row-count paging — giving uniform chunk sizes regardless of data density across seasons. Migrated `downtime_analysis_service` onto `execute_plan` whole-dataset dispatch while permanently excluding it from row-count paging (ADR-0003) due to global cross-row reduction semantics. Added `HOLD/JOB/MSD_ENGINE_PARALLEL`, `BATCH_QUERY_ROWS_PER_CHUNK` env vars for the three previously unparallelized services.

## Final Behavior

- `USE_ROW_COUNT_CHUNKING=false` (default): all 7 services behave identically to pre-change. Zero deploy risk.
- `USE_ROW_COUNT_CHUNKING=true`: `production_history`, `reject_dataset`, `resource_dataset`, `hold_dataset`, `job_query`, `mid_section_defect` run `COUNT(*) → decompose_by_row_count → execute_plan(paged SQL)` instead of `decompose_by_time_range → execute_plan`.
- `downtime_analysis_service` now uses `execute_plan(whole-dataset single chunk) → merge_chunks_to_spool`; `_merge_cross_shift_events` and `_bridge_jobid` applied as post-merge stage.
- `HOLD/JOB/MSD_ENGINE_PARALLEL` are now env-configurable (default `1`; prev hard-coded `1`).
- `base_events.sql` ORDER BY reconciled to `OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC`.

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| `contracts/business/business-rules.md` | 1.13.0 → 1.13.1 | BQE-01..07 added; BQE-02 dict notation fix; BQE-05 pool size accuracy fix |
| `contracts/env/env-contract.md` | 1.0.2 → 1.0.4 | 5 new vars: USE_ROW_COUNT_CHUNKING, BATCH_QUERY_ROWS_PER_CHUNK, HOLD/JOB/MSD_ENGINE_PARALLEL |
| `contracts/data/data-shape-contract.md` | 1.12.1 → 1.12.2 | §3.12.7 clarification: downtime migration does not change parquet schema |
| `docs/adr/0003-downtime-rowcount-chunking-exclusion.md` | new | downtime permanently excluded from USE_ROW_COUNT_CHUNKING |

## Final Tests Added / Updated

| file | classes added | count |
|---|---|---|
| `tests/test_batch_query_engine.py` | TestDecomposeByRowCount, TestShouldDecomposeByRowCount, TestEngineParallelCeiling, TestFlagGating, TestExcludedServicesUnmodified | 22 |
| `tests/test_downtime_analysis_service.py` | TestDowntimeMigration | 4 |
| `tests/stress/test_chunk_boundary.py` | TestChunkSeam, TestOrderByTieStability | 8 |
| `tests/integration/test_rowcount_flag_parity.py` | TestFlagFalseRegression, TestFlagTrueParity, TestSpoolSchemaParity, TestSpoolLifecycle, TestPartialChunkFailure | 23 |
| `tests/test_env_contract.py` | TestNewEnvVarsDocumented, TestEngineDefaultsMatchContract | 10 |

Total: 67 new tests. Full suite: 4331 passed, 0 regressions.

## Final CI/CD Gates

All Tier 0+1 gates green on CI (PR #3). Tier 3/4 informational gates pending (nightly/weekly schedule). `USE_ROW_COUNT_CHUNKING=true` production enable blocked until Tier 3/4 evidence complete (see `stress-soak-report.md`).

## Production Reality Findings

- **Contract gap caught by tests**: `BATCH_QUERY_ROWS_PER_CHUNK` was implemented in `batch_query_engine.py` but omitted from `env-contract.md` table in 1.0.3. Discovered when writing `TestNewEnvVarsDocumented`. Fixed in 1.0.4.
- **BQE-05 pool size inaccuracy**: Contract originally stated "production=3, development=2" confusing configured ENGINE_PARALLEL values with DB_SLOW_POOL_SIZE defaults. Actual production default is 5 (settings.py `ProductionConfig`). Fixed in business-rules.md 1.13.1.
- **TestPartialChunkFailure placement**: placed in `test_rowcount_flag_parity.py` not `test_oracle_error_path.py` because the oracle_error_path file has module-level `pytestmark = pytest.mark.integration_real` which skips mock-only tests.
- **resource_dataset execute_plan called twice**: base query (flag-gated paged) + OEE query (always date-range). OEE always uses date-range per design (OEE SQL uses chunk_start/chunk_end bind vars).
- **downtime local imports**: `has_downtime_events` / `store_downtime_events` imported inside `query_downtime_dataset` function; tests must patch at `mes_dashboard.services.downtime_analysis_cache` boundary, not at service module-level.

## Lessons Promoted to Standards

All four learnings promoted to `CLAUDE.md`:

| lesson | target | section |
|---|---|---|
| L1: ROW_NUMBER() chunking incompatible with global cross-row reductions | CLAUDE.md | new `## BatchQueryEngine Architecture Notes` |
| L2: module-level constants frozen at import — patch attribute, not env | CLAUDE.md | `## Test Coverage Discipline` |
| L5: env-var contract tests must pin default values, not just presence | CLAUDE.md | `## Test Coverage Discipline` |
| L7: module-level `pytestmark` silently skips mock tests in integration files | CLAUDE.md | `## Test Coverage Discipline` |

Evidence paths: `docs/adr/0003-downtime-rowcount-chunking-exclusion.md` (L1), `tests/integration/test_rowcount_flag_parity.py` (L2, L7), `tests/test_env_contract.py` + BQE-05 inaccuracy (L5).

## Follow-up Work

- **Tier 3/4 stress-soak evidence**: `stress-soak-report.md` documents required evidence before `USE_ROW_COUNT_CHUNKING=true` in production. Run after at least one full nightly Tier 3 cycle.
- **`material_consumption_service`**: low-priority candidate for BatchQueryEngine adoption if data volume grows. Currently excluded (aggregate query, small result set).
- **HISTORYID-aligned partitioning for downtime**: if a very large date range exceeds memory for whole-dataset dispatch, implement HISTORYID-aligned chunking as fallback (design.md §Open Risks).

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`). Do not treat this file as a specification.
