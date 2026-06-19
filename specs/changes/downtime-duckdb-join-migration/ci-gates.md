# CI/CD Gate Plan

## Change ID

downtime-duckdb-join-migration

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local / PR | `ruff check .` | — |
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push / PR | `cdd-kit validate --contracts` (`contract-and-fast-tests` job) | — |
| unit-mock-integration | 1 | yes | push / PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` (`unit-and-integration-tests` job in `backend-tests.yml`) | junit XML |
| cdd-gate | 1 | yes | PR | `cdd-kit gate downtime-duckdb-join-migration` | — |
| downtime-e2e | 1 | informational | manual dispatch | `pytest tests/e2e/test_downtime_analysis_e2e.py -m e2e` (`e2e-tests.yml`) | pytest report |
| nightly-integration | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` (`nightly-integration` job) | test report |
| oracle-fault-injection | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/test_downtime_rq_async.py --run-integration-real` (GunicornHarness parity + resilience) | test report |
| stress-load | 4 | yes (weekly) | schedule / dispatch | `pytest tests/stress/test_downtime_analysis_stress.py -m "stress or load"` (`stress-tests.yml`) | perf report |
| soak | 4 | yes (weekly) | schedule / dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` (`stress-tests.yml` soak job) | soak report |

### Gate-to-AC traceability

See `test-plan.md` for the full criterion-to-test mapping.  Key bindings below:

- `unit-mock-integration` covers: `test_base_chunked_duckdb_job.py` (BaseChunkedDuckDBJob), `tests/test_query_cost_policy.py` (`DowntimeJob` stem in `_APPROVED_CALLERS`), `tests/contract/test_env_downtime_flag.py` (AC-6 env-contract pin for `DOWNTIME_USE_UNIFIED_JOB`).
- `nightly-integration` covers: `tests/integration/test_downtime_rq_async.py` (enqueue dispatch, spool write ordering, parity), `tests/integration/test_rowcount_flag_parity.py` (Path A vs Path B row-count parity under real Oracle).
- `stress-load` covers: `tests/stress/test_downtime_analysis_stress.py` (concurrent RESOURCEID-chunk throughput, DuckDB on-disk spill under load).
- `downtime-e2e` covers: `tests/e2e/test_downtime_analysis_e2e.py` (GunicornHarness end-to-end: async dispatch → polling → results; cancel mid-job; flag-off path stays on sync).

## CI/CD Workflow

No new workflow YAML files are required. All new test files are auto-discovered by existing workflow commands:

- `backend-tests.yml` (`unit-and-integration-tests` job) already discovers `tests/` root — new `tests/test_base_chunked_duckdb_job.py` extensions and `tests/contract/test_env_downtime_flag.py` are picked up automatically.
- `backend-tests.yml` nightly (`nightly-integration` job) already runs `tests/integration/ --run-integration-real` — `tests/integration/test_downtime_rq_async.py` and `tests/integration/test_rowcount_flag_parity.py` are picked up automatically.
- `stress-tests.yml` already runs `tests/stress/ -m "stress or load"` — `tests/stress/test_downtime_analysis_stress.py` is picked up automatically.
- `e2e-tests.yml` already runs `tests/e2e/ -m e2e` — `tests/e2e/test_downtime_analysis_e2e.py` is picked up automatically.

Feature flag `DOWNTIME_USE_UNIFIED_JOB=off` (default) guarantees zero behavioral change across all gate runs until explicitly set.  No runner-environment change required.

**Concurrency** (informational, already applied to existing downtime E2E jobs):
```yaml
concurrency:
  group: ${{ github.ref }}-downtime-e2e
  cancel-in-progress: true
```

**Artifact retention** (existing policy applies — no change):
- pytest / vitest reports: 30 days
- Soak / stress reports: 90 days

## Workflow Changes Applied

No new `.github/workflows/*.yml` files created or modified.  No Makefile gate targets added.

The only required file change outside `specs/` is a patch bump to `contracts/ci/ci-gate-contract.md` (schema-version 1.3.29 → 1.3.30) to record the additive gate-compatibility note for this change.  That update is applied in the same PR as the implementation.

## Promotion Policy

- **Tier 0**: `ruff check .` and `cdd-kit validate` must be clean before opening a PR.  No bypass.
- **Tier 1 (merge gate)**: all three of the following must be green before merge:
  - `unit-mock-integration` (including AC-6 env-contract pin test in `tests/contract/test_env_downtime_flag.py`)
  - `response-shape-validate` (`cdd-kit validate --contracts`)
  - `cdd-kit gate downtime-duckdb-join-migration`
- **Tier 3 (nightly)**: `nightly-integration` and `oracle-fault-injection` are not merge-blocking, but failure must be triaged within 1 business day.  The flag-off default makes pre-merge Tier 3 failure non-blocking.
- **Tier 4 (weekly)**: `stress-load` and `soak` are not merge-blocking.  However, a `stress-soak-report.md` authored and committed by the stress-soak-engineer is required before flag promotion to `on` in production.  The report must demonstrate DuckDB on-disk spill behaviour under the 184k-row stress fixture with no Python heap OOM.
- **downtime-e2e** starts as informational.  Promotion to required follows the standard Informational Gate Promotion Policy (20 days / 60 runs / pass-rate above threshold / runtime within limit / owner assigned).

## Rollback Policy

**Zero-downtime rollback (flag off — preferred):**
1. Set `DOWNTIME_USE_UNIFIED_JOB=off` in all process environments (gunicorn + `downtime-query` RQ workers).
2. Restart gunicorn and workers — this flag is a module-level constant frozen at boot; `kill -HUP` alone is insufficient.
3. All downtime queries route back to the legacy `pd.merge` (Path B) path.
4. No parquet cleanup required: the `DowntimeJob` writes to the existing `downtime_analysis_base_events` and `downtime_analysis_job_bridge` spool namespaces; spool schema is unchanged between paths.
5. No `_SCHEMA_VERSION` bump required unless a schema-breaking spool change was also shipped.

**Hard rollback (revert PR):**
1. Revert the PR on `main`; deploy the reverted build.
2. Restart RQ workers for the `downtime-query` queue.
3. In-flight `DowntimeJob` tasks that are mid-run are abandoned; the frontend receives HTTP 410 (`CACHE_EXPIRED`) on the next progress poll and retries on the next user query — this is graceful per the existing async-job contract.
4. No raw two-spool path cleanup needed (out of scope per change-request.md Non-goals).

**Schema-breaking spool rollback (if `_SCHEMA_VERSION` was bumped in the same PR):**
```bash
rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet
rm -f tmp/query_spool/downtime_analysis_job_bridge/*.parquet
```
Bumping `_SCHEMA_VERSION` in `downtime_analysis_cache.py` also orphans live parquets by key without a manual `rm` (design.md D4 / existing downtime-browser-duckdb precedent).

## Merge Eligibility

**Blocked until ALL of the following are green:**
- `lint` (Tier 0)
- `contract-validate` (Tier 0)
- `response-shape-validate` (Tier 1)
- `unit-mock-integration` (Tier 1) — must include passing `tests/contract/test_env_downtime_flag.py` (AC-6)
- `cdd-kit gate downtime-duckdb-join-migration` (Tier 1)

**Informational risk (does not block merge):**
- `downtime-e2e` (Tier 1, informational until promotion criteria met)
- `nightly-integration` / `oracle-fault-injection` (Tier 3)
- `stress-load` / `soak` (Tier 4) — `stress-soak-report.md` required before flag promotion to `on`, not before merge
