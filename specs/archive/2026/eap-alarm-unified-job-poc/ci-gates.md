# CI/CD Gate Plan

## Change ID
eap-alarm-unified-job-poc

## Required Gates for This Change
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local/PR | `ruff check .` | — |
| contract-validate | 0 | yes | local/PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push/PR | `cdd-kit validate --contracts` (contract-driven-gates.yml) | — |
| unit-mock-integration | 1 | yes | push/PR | `pytest tests/ tests/stress/test_chunk_boundary.py -k "TestChunkSeam or TestOrderByTieStability" --ignore=tests/e2e --ignore=tests/stress` (backend-tests.yml `unit-and-integration-tests`) | junit XML, 30d |
| cdd-gate | 1 | yes | PR | `cdd-kit gate eap-alarm-unified-job-poc` (contract-driven-gates.yml) | — |
| eap-alarm-e2e | 1 | yes | manual dispatch | `pytest tests/e2e/test_eap_alarm_e2e.py -m e2e` (e2e-tests.yml) | — |
| type-check | 2 | informational | push/PR | `mypy src/` | — |
| nightly-integration | 3 | yes (nightly) | schedule/dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` (backend-tests.yml `nightly-integration-real`) | test report, 30d |
| oracle-fault-injection | 3 | yes (nightly) | schedule/dispatch | `pytest tests/integration/test_eap_alarm_resilience.py tests/integration/test_oracle_arrow_pool_lifecycle.py --run-integration-real` (backend-tests.yml `oracle-fault-injection`) | logs, 7d on fail |
| stress-load | 4 | yes (weekly) | schedule/dispatch | `pytest tests/stress/ -v -m stress --run-stress` (stress-tests.yml) | perf report, 90d |
| soak | 4 | yes (weekly) | schedule/dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` (soak-tests.yml) | soak metrics JSON, 90d |

## CI/CD Workflow

1. **Tier 0 (local, pre-push)**: `ruff check .` + `cdd-kit validate` must be clean before opening a PR.
2. **Tier 1 (PR gate)**: On every push/PR touching `src/mes_dashboard/{core,services,workers,routes}/**` or `tests/**`, `backend-tests.yml` (`unit-and-integration-tests` job) runs the full unit + mock-integration suite including:
   - `tests/test_eap_alarm_service.py`, `tests/test_base_chunked_duckdb_job.py`, `tests/test_async_query_job_service.py`
   - `tests/stress/test_chunk_boundary.py` seam subset (`TestChunkSeam`, `TestOrderByTieStability`)
   - `tests/contract/` via `cdd-kit gate eap-alarm-unified-job-poc`
   - `cdd-kit validate --contracts` (response-shape-validate)
   All Tier 1 jobs must be green before the PR is eligible for merge.
3. **Tier 2 (informational)**: `mypy src/` runs on PR; failures visible but do not block merge until promoted.
4. **Tier 3 (nightly)**: `backend-tests.yml` schedule (`nightly-integration-real`, `oracle-fault-injection`, `multi-worker-concurrency`) runs tests requiring real Oracle/Redis including `tests/integration/test_eap_alarm_rq_async.py`, `test_eap_alarm_data_boundary.py`, `test_eap_alarm_resilience.py`, `test_oracle_arrow_pool_lifecycle.py`, `test_rowcount_flag_parity.py`. Failures must be triaged within 1 business day.
5. **Tier 4 (weekly/manual)**: `stress-tests.yml` covers `tests/stress/test_async_job_stress.py` + full `test_chunk_boundary.py`; `soak-tests.yml` covers `tests/integration/test_soak_workload.py`. These are not pre-merge gates.
6. **E2E dispatch**: `e2e-tests.yml` (manual dispatch) runs `tests/e2e/test_eap_alarm_e2e.py`; must be verified green before merge on Tier-1 high-risk changes per change-classification.md §Tier: 1.

## Workflow Changes Applied
No new workflow files are required. All new tests fall within existing workflow commands per `contracts/ci/ci-gate-contract.md §eap-alarm-analysis` (ci 1.3.25):
- `unit-mock-integration` gate already runs `tests/` root and `tests/stress/test_chunk_boundary.py` seam subset.
- `nightly-integration` gate already runs `tests/integration/` with `--run-integration-real`.
- `oracle-fault-injection` job already covers fault-injection tests; eap-alarm resilience + pool lifecycle tests are added to its scope without a command change.
- `stress-tests.yml` already runs `tests/stress/ -m stress --run-stress`.
- `soak-tests.yml` already runs `tests/integration/test_soak_workload.py -m soak`.
- `e2e-tests.yml` already runs `tests/e2e/ -m e2e`.

Schema-version bump to `contracts/ci/ci-gate-contract.md` is required in the same PR (additive gate-compatibility note for eap-alarm-unified-job-poc; no gate tier, command, or status changes).

## Promotion Policy
This change is gate-ready and eligible for merge when ALL of the following are true:
- Tier 0: `ruff check .` clean; `cdd-kit validate` clean locally.
- Tier 1: `unit-and-integration-tests` job green (all test files in §Required Tests from change-classification.md that carry no `integration_real`/`stress`/`soak` marker); `cdd-kit gate eap-alarm-unified-job-poc` passes; `cdd-kit validate --contracts` passes.
- Tier 1 E2E: `e2e-tests.yml` dispatch run for `tests/e2e/test_eap_alarm_e2e.py` is green (manually triggered once per PR cycle for this Tier-1 high-risk change).
- AC-7 env-contract pin test passes within `unit-mock-integration` gate.
- AC-4 503 dispatch unit test passes within `unit-mock-integration` gate.
- `stress-soak-report.md` authored by stress-soak-engineer (IP-8) and committed to `specs/changes/eap-alarm-unified-job-poc/`; Tier 4 gates are not required to be green pre-merge but the report must confirm no connection leak or OOM signal from local/dispatch runs.

## Rollback Policy
Flag-off path (zero-downtime, preferred):
1. Set `EAP_ALARM_USE_UNIFIED_JOB=off` (or `false`) in environment.
2. Reload gunicorn (`kill -HUP`). All eap_alarm queries fall back to legacy `run_eap_alarm_query_job`; no RQ dispatch via `enqueue_query_job`.
3. No parquet cleanup required — spool schema is identical to legacy path (explicit non-goal; ADR-0008, no `_SCHEMA_VERSION` bump).
4. No 503 path will be triggered (flag-OFF bypasses `enqueue_query_job` entirely).

Hard rollback (revert commit):
1. Revert the PR on main.
2. Restart RQ workers — in-flight `EapAlarmJob` tasks are abandoned; frontend receives 410 `CACHE_EXPIRED` and will retry on next query (pre-existing graceful behavior per ci-gate-contract §eap-alarm-analysis rollback).
3. Do NOT run `rm tmp/query_spool/eap_alarm/*.parquet` unless a forced schema change was detected — schema is held equivalent (AC-1, ADR-0008).
4. Tier 3/4 failure post-merge: open incident ticket; set flag=off within 1 business day; defer hard rollback to the next planned deploy window.

## Merge Eligibility
mergeable when all Tier 0 and Tier 1 gates are green and the E2E dispatch run is confirmed green; Tier 3/4 gates are informational-risk until the first nightly/weekly run post-merge.
