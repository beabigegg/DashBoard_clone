# CI/CD Gate Review: rq-semaphore-wiring

## Required Gates (Tier 1 — pre-merge)

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local / PR | `ruff check .` | — |
| contract-validate | 0 | yes | local / PR | `cdd-kit validate` | — |
| unit-mock-integration | 1 | yes | push / PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| response-shape-validate | 1 | yes | push / PR | `cdd-kit validate --contracts` | — |

New Tier-1 tests auto-discovered by `unit-mock-integration` (no command change needed):

- Per-worker acquire/release wiring for `execute_query_tool_job`, `execute_hold_history_query_job`, `execute_resource_history_query_job` (AC-4, AC-6)
- `@contextmanager` helper in `global_concurrency.py`: acquire bool yielded; `release` guarded by `acquired` so fail-open never double-releases (design.md D2)
- `execute_reject_query_job` body contains no `acquire_heavy_query_slot` call (AC-6, D3)
- Flag-off parity: `*_USE_RQ=off` / `*_USE_UNIFIED_JOB=off` paths never reach acquire/release (AC-5)

## Informational Gates (Tier 3 nightly / Tier 4 stress-soak)

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| nightly-integration | 3 | yes (nightly) | weekly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report |
| stress-load | 4 | yes (weekly) | weekly schedule / dispatch | `pytest tests/stress/ -m "stress or load"` | perf report |
| soak | 4 | yes (weekly) | weekly schedule / dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` | soak report |

New files picked up by existing commands (no gate command change):

- `tests/integration/test_rq_semaphore_wiring.py` (Tier 3, `integration_real` marker): N=8 concurrent workers across all four job types; asserts peak simultaneous Oracle-phase executions ≤ `HEAVY_QUERY_MAX_CONCURRENT` (3) (AC-1); all N reach terminal state with no deadlock (AC-2); post-completion semaphore full availability, zero slot leak (AC-3); exception-path slot release (AC-4).
- `tests/stress/test_rq_semaphore_stress.py` (Tier 4, `stress` marker): high-concurrency burst across all four worker types; confirms cap sustained without leak or deadlock.

## Manual / Pre-Production Gates

`stress-soak-report.md` is a required pre-production gate artifact (not a merge blocker).

It must demonstrate, via `get_active_slot_count()` sampling under load:

- `peak_concurrent ≤ 3` at all times across all four worker types simultaneously (AC-1)
- Zero slot leak after all jobs terminate (AC-3)
- No deadlock across any combination of job types

This evidence must exist and be reviewed before any `*_USE_RQ` or `*_USE_UNIFIED_JOB` flag is promoted to `on` in production (design.md Migration/Rollback; ci-gate-contract.md §rq-semaphore-wiring, ASYNC-15).

## Workflow Changes Applied

No new workflow YAML files required. All three new test files fall within existing gate discovery:

- `unit-mock-integration` (Tier 1) auto-discovers new unit tests under `tests/` root.
- `nightly-integration` (Tier 3) auto-discovers `tests/integration/test_rq_semaphore_wiring.py`.
- `stress-load` (Tier 4) auto-discovers `tests/stress/test_rq_semaphore_stress.py`.

ci-gate-contract.md gate-compatibility note written at schema-version 1.3.32 (patch, additive).

## Promotion Policy

- Deploy with all `*_USE_RQ` and `*_USE_UNIFIED_JOB` flags at their current defaults (`off` or unchanged). The semaphore wiring is inert until a flag routes traffic into the worker.
- Flag-on promotion for any worker requires: Tier-1 green, Tier-3 nightly green (at least one run post-merge), and `stress-soak-report.md` signed off showing `peak_concurrent ≤ 3`, no leak, no deadlock for all four worker types under simultaneous load.
- resource worker flag-on additionally requires DBA confirmation that `HEAVY_QUERY_MAX_CONCURRENT × 2` (resource fans 2 connections per slot) is within `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` headroom (design.md open risk).

## Rollback Policy

- **Code rollback**: revert the wrapper lines (and `@contextmanager` helper if added). No state, key, or flag cleanup required.
- **Semaphore key**: `heavy_query_slots` self-expires via its 600 s Redis TTL. No manual `DEL` needed.
- **No parquet cleanup**: this change has no spool writes; do not add parquet cleanup to rollback steps (query-tool has no persistent spool; ci-gate-contract.md §material-part-consumption).
- **In-flight jobs**: acquire is context-managed and exception-safe; any in-flight job that was mid-Oracle-phase at rollback time will complete its `finally` release normally.
- If a main-branch Tier-1 gate turns red after merge, no new PRs merge until fixed (ci-gate-contract.md §Rollback Policy).

## Merge Eligibility

**Mergeable** when:

- `unit-mock-integration` green (all per-worker wiring assertions, flag-off parity, CM helper, reject absence)
- `response-shape-validate` green (no response-shape change; gate passes trivially)
- `lint` green
- `contract-validate` green

Tier-3 and Tier-4 gates run post-merge on schedule; `stress-soak-report.md` is a pre-production gate, not a pre-merge blocker.
