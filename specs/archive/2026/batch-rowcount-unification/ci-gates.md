# CI/CD Gate Plan

## Change ID
batch-rowcount-unification

## Required Gates

| gate | tier | required | trigger | command / workflow |
|---|---:|:---:|---|---|
| unit: decompose_by_row_count, ENGINE_PARALLEL ceiling, flag-gating, excluded-services | 0 | yes | pull_request | `pytest tests/test_batch_query_engine.py` via `backend-tests.yml / unit-and-integration-tests` |
| property: no-gap-no-overlap (Hypothesis) | 0 | yes | pull_request | `pytest -m property` via `backend-tests.yml / unit-and-integration-tests` |
| unit: downtime migration (TestDowntimeMigration) | 1 | yes | pull_request | `pytest tests/test_downtime_analysis_service.py` via `backend-tests.yml / unit-and-integration-tests` |
| contract: env-contract 4 new vars | 1 | yes | pull_request | `pytest tests/test_env_contract.py` via `backend-tests.yml / unit-and-integration-tests` |
| integration: flag=false regression + flag=true parity, spool schema, spool lifecycle (7 services) | 1 | yes | pull_request | `pytest tests/integration/test_rowcount_flag_parity.py` via `backend-tests.yml / unit-and-integration-tests` |
| resilience: partial-chunk Oracle error → no partial spool | 1 | yes | pull_request | `pytest tests/integration/test_rowcount_flag_parity.py::TestPartialChunkFailure` via `backend-tests.yml / unit-and-integration-tests` |
| data-boundary: chunk seam + ORDER BY tie-stability | 1 | yes | pull_request | `pytest tests/stress/test_chunk_boundary.py -k "TestChunkSeam or TestOrderByTieStability"` via targeted step in `backend-tests.yml / unit-and-integration-tests` |
| cdd-kit validate (contract traceability) | 1 | yes | pull_request | `cdd-kit validate` via `contract-driven-gates.yml` |

## Informational Gates

| gate | tier | trigger | command / workflow |
|---|---:|---|---|
| nightly: count/paged consistency under concurrent insert | 3 | schedule (nightly 02:00 UTC) | `pytest tests/integration/test_race_conditions.py --run-integration-real` via `backend-tests.yml / nightly-integration-real` |
| weekly stress: parallel-execution peak RSS | 4 | schedule (Sunday 18:00 UTC) / workflow_dispatch | `pytest tests/stress/test_chunk_boundary.py -m stress --run-stress` via `stress-tests.yml / stress-tests` |
| weekly soak: sustained memory uniformity + spool lifecycle | 4 | schedule (Sunday) / workflow_dispatch | `pytest tests/integration/test_soak_workload.py -m soak --run-integration-real` via `soak-tests.yml / soak` |

## New Workflow Changes

No new workflow file created. One step added to `.github/workflows/backend-tests.yml` job `unit-and-integration-tests`, after "Run unit and integration tests":

```yaml
- name: Run chunk-boundary data-boundary tests (Tier 1)
  run: |
    python -m pytest tests/stress/test_chunk_boundary.py \
      -k "TestChunkSeam or TestOrderByTieStability" \
      -v --tb=short
```

`TestMemoryProfile` (Tier 4, stress-only) is not matched by the `-k` filter and remains nightly/weekly only.

`USE_ROW_COUNT_CHUNKING` is NOT set in any CI workflow env block (default `false`). The flag=true path is exercised inside `test_rowcount_flag_parity.py` via `monkeypatch.setenv`. `HOLD_/JOB_/MSD_ENGINE_PARALLEL` are validated in `tests/test_env_contract.py`, not set in CI env blocks.

## Required Check Policy

The `unit-and-integration-tests` job in `backend-tests.yml` is the binding required status check. All Tier 0 and Tier 1 gates listed above run within this job and must be green to merge.

## Informational Gate Promotion Policy

nightly Tier 3 (`TestCountPagedConsistency`) and weekly Tier 4 (stress/soak) are informational. If they fail consistently (≥2 consecutive runs), open a follow-up bug. They do not block merge but are a pre-condition for `USE_ROW_COUNT_CHUNKING=true` in production (see Promotion Policy).

## Promotion Policy

1. **Merge eligibility**: all Tier 0 and Tier 1 required gates green.

2. **Staging deploy (flag=false)**: deploy with `USE_ROW_COUNT_CHUNKING=false` (default). No behavior change; existing per-page E2E acts as regression guard.

3. **`USE_ROW_COUNT_CHUNKING=true` in production is BLOCKED** until:
   - All `TestFlagTrueParity` and `TestSpoolSchemaParity` tests pass in CI (mock) AND on real staging data via manual run.
   - At least one successful nightly Tier 3 `TestCountPagedConsistency` run.
   - `regression-report.md` reviewed and signed off.

4. **`HOLD_/JOB_/MSD_ENGINE_PARALLEL` > 1**: may be set once `TestEngineParallelCeiling` is green and the target env's `DB_SLOW_POOL_SIZE` is confirmed (prod=3, dev=2).

## Rollback Policy

**`USE_ROW_COUNT_CHUNKING=true` rollback**: set `USE_ROW_COUNT_CHUNKING=false` (or remove the env var). No redeploy, no spool purge. Column schema is identical between paths (AC-5).

**downtime_analysis migration rollback** (no flag, Phase 2): code revert only. No spool purge — spool namespace (`tmp/query_spool/downtime_analysis/`) and column schema are preserved (BQE-07, ADR-0003).

**`ENGINE_PARALLEL` rollback**: set affected var back to `1`. No redeploy.

**Do NOT add `rm tmp/query_spool/<service>/*.parquet` to any rollback runbook for this change** — spool column schemas are unchanged between paths.

## Artifact Retention

| artifact | workflow | retention |
|---|---|---|
| Hypothesis failure examples | `backend-tests.yml` | 14 days |
| Soak metrics | `soak-tests.yml` | 30 days |

## Merge Eligibility Decision

**blocked** until all Tier 0 and Tier 1 required gates are green (see Required Gates table above).

## Notes

See design.md §Migration / Rollback for phased deployment guidance. See ADR-0003 for the permanent downtime row-count exclusion rationale.
