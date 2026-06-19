# Archive: material-trace-streaming-migration

## Change Summary

Replaced the in-memory `pd.concat(chunks) + post-hoc _check_memory_guard()` path in
`material_trace_service._execute_batched_query` with a streaming Oracle→Arrow→DuckDB
pipeline (`MaterialTraceJob`) gated behind the `MATERIAL_TRACE_USE_UNIFIED_JOB`
feature flag (default=`off`). `MaterialTraceJob` fetches Oracle rows as Arrow
RecordBatches in 1000-ID batches (ID_LIST strategy), writes per-chunk parquets,
then runs a DuckDB `SELECT DISTINCT` post-aggregate to deduplicate on the exact
4-column key matching the legacy `drop_duplicates` key `[CONTAINERID, MATERIALLOTNAME,
WORKCENTERNAME, TXNDATE]`. This eliminates the peak-heap spike that made large
material-trace queries OOM-prone, replacing it with DuckDB on-disk spill.

## Final Behavior

- `MATERIAL_TRACE_USE_UNIFIED_JOB=off` (default): zero behavioral change; legacy
  `enqueue_job("material-trace", ...)` path is unchanged.
- `MATERIAL_TRACE_USE_UNIFIED_JOB=on`:
  - Always-async; RQ unavailable → 503 (no silent sync fallback).
  - `MaterialTraceJob.run()`: Oracle→Arrow per-batch → chunk parquets → DuckDB DISTINCT
    dedup → WORKCENTER_GROUP enrichment → spool parquet (same namespace + schema as legacy).
  - Semaphore role: limits RQ concurrency to Oracle (no code change; doc-only D3).
- Promotion to `on` is deferred pending Tier-3 nightly AC-4 spool parity + Tier-4 weekly
  AC-5 soak evidence (heap ratio < 1.5).

## Final Contracts Updated

| Contract | Version | Change |
|---|---|---|
| `contracts/env/env-contract.md` | 1.0.17 → 1.0.18 | Added `MATERIAL_TRACE_USE_UNIFIED_JOB` feature-flag row + internal CHANGELOG [env 1.0.18] |
| `contracts/env/env.schema.json` | — | Added enum+default for new flag |
| `contracts/env/.env.example.template` | — | Added `MATERIAL_TRACE_USE_UNIFIED_JOB=off` |
| `contracts/business/business-rules.md` | 1.25.0 → 1.26.0 | ASYNC-10 (dispatch rule), ASYNC-11 (semaphore re-statement), 3 flag decision table rows |
| `contracts/data/data-shape-contract.md` | 1.21.0 → 1.22.0 | §3.20 UNCHANGED assertion: `material_trace` spool 13-col set identical between unified and legacy paths |
| `contracts/ci/ci-gate-contract.md` | 1.3.28 → 1.3.29 | Additive gate compatibility note for material-trace |
| `contracts/CHANGELOG.md` | — | [env 1.0.18], [data 1.22.0], [business 1.26.0], [ci 1.3.29] entries |

## Final Tests Added / Updated

| File | Type | ACs |
|---|---|---|
| `tests/test_material_trace_unified_job.py` (new, 16 tests) | unit/targeted | AC-1, AC-2, AC-3, AC-4, AC-6, AC-8 |
| `tests/contract/test_env_material_trace_flag.py` (new, 11 tests) | contract | AC-7 |
| `tests/integration/test_material_trace_rq_async.py` (new, 12 tests) | resilience/integration | R-1 Oracle fault, R-2 503 no-fallback, R-3 2500-ID dedup |
| `tests/stress/test_material_trace_stress.py` (extended, 2 tests) | stress scaffold | S-1 concurrency cap, S-2 heap-ratio |
| `tests/stress/test_chunk_boundary.py` (extended) | boundary | AC-8 (999/1000/1001/2000/2001/5000) |
| `tests/test_job_registry.py` | registry count | Updated expected count 8→9 for `material-trace-unified` |
| `tests/test_query_cost_policy.py` | caller policy | Added `material_trace_duckdb_runtime` to `_APPROVED_CALLERS` for `oracle_arrow_reader` and `base_chunked_duckdb_job` |

## Final CI/CD Gates

- **Tier 0/1 (merge-blocking)**: lint, contract-validate, response-shape-validate, unit-mock-integration, e2e-critical — all green.
- **Tier 3 (nightly, not merge-blocking)**: `tests/integration/test_material_trace_rq_async.py` GunicornHarness parity — deferred.
- **Tier 4 (weekly, required before flag=on promotion)**: `tests/stress/test_material_trace_stress.py` AC-5 heap soak + `test_chunk_boundary.py` boundary — scaffolded, deferred.
- No new workflow files introduced.

## Production Reality Findings

**DEV-01**: `MaterialTraceJob` is NOT a true `BaseChunkedDuckDBJob` subclass due to
circular import constraints. Implemented as a thin wrapper with identical streaming
semantics (`pre_query → OracleArrowReader.chunk_iter → post_aggregate`). Risk: low.
All design decisions D1–D4 honored; AC coverage complete. Class docstring documents
the deviation at `material_trace_duckdb_runtime.py`.

**F-1 (fixed)**: `env-contract.md` schema-version bump (1.0.17→1.0.18) was applied to
the frontmatter but the internal CHANGELOG section inside the file was missing the
`[env 1.0.18]` entry. contract-reviewer caught this as a BLOCKING finding. Fixed before merge.

**F-2 (fixed)**: P1/P2/P3 migrations had explicit `§3.x UNCHANGED` spool-schema
assertions in `data-shape-contract.md`; P4 (material-trace) lacked one. Fixed by
adding §3.20 UNCHANGED assertion (13-col set, identical between unified and legacy paths).

**CI hang investigation**: First CI run (`30af746b`) appeared to hang for 27 minutes.
Root cause: 2 test failures (`test_query_cost_policy` caller-policy and `test_job_registry`
count) caused the full 4800-test suite to fail late; GitHub Actions runner was slow
(~27 min for suite vs ~4.5 min locally). Logs not accessible via API while job is
in-progress (`BlobNotFound`). Fixed by updating both tests + cancelling the stalled run.

## Lessons Promoted to Standards

**L-1: `_APPROVED_CALLERS` policy for controlled internal modules**
- Classification: promote-to-guidance
- Target: `docs/architecture/test-discipline.md` § _APPROVED_CALLERS (new section) + `CLAUDE.md` one-line entry in "Test coverage discipline"
- Rule: New modules that intentionally import from `oracle_arrow_reader` or `base_chunked_duckdb_job` must add their stem to `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py` in the same PR, or CI fails with AC-7 caller-policy violation. Also update `tests/test_job_registry.py` count for new `register_job_type()` calls.
- Evidence: `tests/test_query_cost_policy.py:L336–L368`; CI failure on `30af746b` required cancel + fix commit `ab8c80ea`.

## Follow-up Work

- **Flag promotion** (`MATERIAL_TRACE_USE_UNIFIED_JOB=on`): requires Tier-3 nightly
  AC-4 parity + Tier-4 weekly AC-5 soak evidence (heap ratio < 1.5). Not pre-merge.
- **True BaseChunkedDuckDBJob subclassing**: DEV-01 thin wrapper; re-evaluate when
  circular import structure is refactored (future).
- **Next P4 targets**: downtime-duckdb-join-migration, query-path-c-elimination-cleanup
  (already scaffolded in `specs/changes/`).
- **timeout-minutes on `unit-and-integration-tests` job**: no timeout set; consider
  adding `timeout-minutes: 45` to cap runaway test hangs.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and
active project guidance (`CLAUDE.md`).
