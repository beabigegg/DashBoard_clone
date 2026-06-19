# CI/CD Gate Plan

## Change ID

material-trace-streaming-migration

No new gate tier, command, or workflow file. All new tests fall within existing gate
commands (resource-history-migration / eap-alarm-unified-job-poc precedent). Flag
`MATERIAL_TRACE_USE_UNIFIED_JOB=off` (default) → zero behavioral change under all gate
runs until explicitly set to `on`.

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | pull_request | `ruff check .` | — |
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push/PR | `cdd-kit validate --contracts` | — |
| unit-mock-integration | 1 | yes | pull_request | existing `unit-and-integration-tests` (discovers new `tests/test_material_trace_unified_job.py`, `tests/contract/test_env_material_trace_flag.py`) | junit XML |
| e2e-critical | 1 | conditional | pull_request | existing `e2e-tests.yml` runs `tests/e2e/ -m e2e` (picks up `test_material_trace_e2e.py` flag-on smoke) | playwright trace |
| nightly-integration | 3 | yes (nightly) | weekly/dispatch | existing cmd runs `tests/integration/test_material_trace_rq_async.py` (parity + resilience) | test report |
| stress-load | 4 | yes (weekly) | weekly/dispatch | existing cmd runs `tests/stress/test_material_trace_stress.py`, `tests/stress/test_chunk_boundary.py` (concurrency cap + 1000-ID boundary) | perf report |
| soak | 4 | yes (weekly) | weekly/dispatch | existing cmd runs `tests/integration/test_soak_workload.py` (AC-5 peak-heap non-linearity) | soak report |

## New Workflow Changes

None. No new workflow file, gate tier, or command. Additive only.

## Required Check Policy

Tier 0/1 gates block merge. Tier 3 nightly failures triaged within 1 business day.
Tier 4 weekly soak/stress failures trigger production-readiness review (AC-5 evidence
must accompany flag promotion to `on`).

## Informational Gate Promotion Policy

No new informational gates introduced. Standard policy applies (ci-gate-contract.md
§Informational Gate Promotion Policy).

## Rollback Policy

Zero-downtime path: set `MATERIAL_TRACE_USE_UNIFIED_JOB=off`.
1. Set flag `off` in ALL processes (gunicorn + material-trace worker).
2. **Restart** gunicorn + worker — flag is a module-level constant frozen at boot;
   `kill -HUP` is insufficient.
3. No spool cleanup required: spool namespace `material_trace` + parquet schema are
   unchanged between unified and legacy paths (AC-4) and TTL-managed.
4. If a spool was written by a buggy unified run, `rm` that specific `query_hash`
   parquet under `{QUERY_SPOOL_DIR}/material_trace/` to force legacy-path re-query;
   also `rm` any orphan `{DUCKDB_JOB_DIR}/material_trace/*.duckdb` (design.md Migration/Rollback).

## Artifact Retention

Per ci-gate-contract.md: junit/vitest 30d; playwright traces 7d (30d on failure);
soak/stress reports 90d.

## Merge Eligibility Decision

Mergeable when Tier 0/1 gates green with flag default `off` (legacy parity).
Promotion of flag to `on` per-environment requires Tier 3 parity (AC-4) + Tier 4
soak (AC-5) evidence first.

## Notes

ci-gate-contract.md needs an additive gate-compatibility note + ci schema-version bump
(IP-8), mirroring resource-history-migration (ci-gate-contract.md L502–524). Reference
test-plan.md AC→test mapping for per-test detail; do not duplicate here.
