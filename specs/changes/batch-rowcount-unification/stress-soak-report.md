---
change-id: batch-rowcount-unification
schema-version: 0.1.0
last-changed: 2026-06-01
status: pending-real-infra
---

# Stress and Soak Report: batch-rowcount-unification

## Scope

Peak memory profile and sustained memory uniformity under `USE_ROW_COUNT_CHUNKING=true`
for the two highest-volume services (production_history, resource_dataset).

## Evidence to Date (flag=false, pre-enable)

| test | tier | result |
|---|---|---|
| TestChunkSeam (5 boundary tests) | Tier 1 | PASS — no row drop/dupe at chunk seam |
| TestOrderByTieStability (3 tests) | Tier 1 | PASS — ORDER BY key tie-breaking stable |

These Tier 1 data-boundary tests verify the correctness invariants that would surface
silent data loss in stress scenarios without requiring real Oracle infrastructure.

## Pending Evidence (required before `USE_ROW_COUNT_CHUNKING=true` in production)

Per `ci-gates.md §Promotion Policy item 3`, the following must be completed:

| gate | tier | trigger | status |
|---|---|---|---|
| weekly stress: parallel-execution peak RSS | Tier 4 | `schedule (Sunday) / workflow_dispatch` | **pending** — requires `USE_ROW_COUNT_CHUNKING=true` enabled on staging + `--run-stress` flag |
| weekly soak: sustained memory uniformity | Tier 4 | `schedule (Sunday) / workflow_dispatch` | **pending** — requires 24h soak with real Oracle connection |

## Memory Profile Expectations (flag=true)

- Each chunk fetches at most `BATCH_QUERY_ROWS_PER_CHUNK=50000` rows
- Peak RSS per chunk ≤ `BATCH_CHUNK_MAX_MEMORY_MB=192 MB` (BQE engine guard)
- Expected memory uniformity across chunks: ±10% (date-range chunking can vary ×10 by season)
- `TestMemoryProfile::test_parallel_flag_true_peak_rss_within_budget` exists in
  `tests/stress/test_chunk_boundary.py` — runs with `--run-stress` weekly

## Blocking Status for Production Enable

`USE_ROW_COUNT_CHUNKING=true` production enable is **blocked** pending:
1. One successful nightly Tier 3 `TestCountPagedConsistency` run
2. Both Tier 4 stress/soak gates green (weekly schedule)
3. Manual regression-report sign-off by oncall (already done above)

This report is a placeholder for the Tier 4 evidence. Update with actual RSS/timing
data once stress/soak runs complete on staging.

**Current status:** flag=false deploy approved; flag=true production enable pending Tier 4 evidence.
