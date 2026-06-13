# CI Gates — downtime-rq-async

## Required Gates

| gate | tier | trigger | command | status | notes |
|---|---:|---|---|---|---|
| contract-validate | 0 | local pre-PR | `cdd-kit validate` | required | env-contract 4 new vars; api-contract 202 shape; data-shape-contract §3.14 |
| lint | 0 | local / PR | `ruff check .` | required | new service file + route branch |
| unit-mock-integration | 1 | PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | required | AC-1,2,4,6,7 — threshold branch, env default pins, register_job_type, pct milestone 5→15→60→90→100, DA-11 atomicity |
| frontend-unit | 1 | PR | `cd frontend && npm run test` | required | no new Vitest files expected; guards regressions in shared useAsyncJobPolling.ts |
| css-governance | 1 | PR | `cd frontend && npm run css:check` | required | AsyncQueryProgress integration must not add unscoped rules |
| playwright-resilience | 1 | PR | `cd frontend && npx playwright test tests/playwright/resilience/` | required | AC-5 long-range 202→polling→progress→results; cancel mid-job; short-range 200 sync unchanged — see downtime-rq-async Gate Compatibility Note |

## Informational Gates

| gate | tier | trigger | command | status | notes |
|---|---:|---|---|---|---|
| frontend-type-check | 1 | PR | `cd frontend && npm run type-check` | informational | useAsyncJobPolling.ts already in tsconfig include; continue-on-error: true |
| stress-load | 4 | weekly schedule | `pytest tests/stress/ -m "stress or load"` | informational | concurrent long-range async jobs on downtime queue; promote to required if soak report surfaces OOM |
| soak | 4 | weekly schedule | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` | informational | worker stability over extended job stream |

## Nightly Gates

| gate | tier | trigger | command | status | notes |
|---|---:|---|---|---|---|
| nightly-integration | 3 | weekly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | required (nightly) | AC-3 parity: `execute_downtime_query_job()` vs sync path byte/row-identical base_events + job_bridge parquets; DA-11 atomic spool write; enqueue_job_dynamic dispatch — see `tests/integration/test_downtime_rq_async.py` |

## Workflow Gates

All new tests fall within **existing** workflow commands — no new gate tier or workflow job is required for this change. This is confirmed by `contracts/ci/ci-gate-contract.md` §downtime-rq-async Gate Compatibility Note ("No new gate tier or command").

Affected workflow files:
- `.github/workflows/frontend-tests.yml` — add `npx playwright install --with-deps chromium` step before `npx playwright test tests/playwright/downtime-analysis.spec.js` (required per CLAUDE.md CI Workflow Notes; without it runners exit "Executable doesn't exist")
- `.github/workflows/contract-driven-gates.yml` — no structural change; `unit-mock-integration` and `nightly-integration` jobs already cover new test files

Concurrency block for the Playwright job running the downtime spec (add if not already present):

```yaml
concurrency:
  group: ${{ github.ref }}-downtime-e2e
  cancel-in-progress: true
```

Artifact retention for new test artifacts: playwright traces `retention-days: 7` (30 on failure); no new soak/stress report artifacts at Tier 1.

## Promotion Policy

- `frontend-type-check` may be promoted from informational to required after 20 calendar days / 60 runs with pass rate above threshold, all failures triaged, runtime within limit, and owner assigned — per `contracts/ci/ci-gate-contract.md` §Informational Gate Promotion Policy.
- `stress-load` and `soak` promote only if concurrent-job OOM risk materialises in load testing reports.
- `USE_ROW_COUNT_CHUNKING=true` (batch-rowcount-unification feature flag) must NOT be set to `true` in production until flag=true parity tests pass — this is orthogonal to this change but blocks the broader promotion of the batch engine flag.

## Rollback Policy

**Soft rollback (zero downtime, no gunicorn restart required):**
1. Set `DOWNTIME_ASYNC_ENABLED=false` in the environment; reload gunicorn (`kill -HUP`).
2. All downtime queries revert to synchronous HTTP 200 path.
3. No parquet spool cleanup required — `downtime_analysis_base_events` and `downtime_analysis_job_bridge` namespaces and schema are identical between sync and async paths.
4. Secondary lever: raise `DOWNTIME_ASYNC_DAY_THRESHOLD` to a very large value (e.g. `99999`) without a restart.

**Hard rollback (remove worker):**
1. Stop the `downtime-query` RQ worker systemd unit (`systemctl stop mes-dashboard-downtime-worker.service`).
2. In-flight jobs time out at `DOWNTIME_JOB_TIMEOUT_SECONDS` (default 1800 s); frontend retries on next query, which falls back to sync because `is_async_available()` returns False.

**Schema-breaking rollback only** (if raw-spool schema shipped and must be abandoned):
```bash
rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet
rm -f tmp/query_spool/downtime_analysis_job_bridge/*.parquet
```
Bumping `_SCHEMA_VERSION` in `downtime_analysis_cache.py` also orphans live parquets by key without a manual `rm`.

**Tier 1 gate failure** blocks merge on `main`; no new PR may merge until the gate is green — per `contracts/ci/ci-gate-contract.md` §Rollback Policy.

## Merge Eligibility

mergeable when:
- `contract-validate`, `lint`, `unit-mock-integration`, `frontend-unit`, `css-governance`, `playwright-resilience` are all green on the PR branch
- `npx playwright install --with-deps chromium` step is present in `frontend-tests.yml` before the downtime Playwright spec
- `rq_monitor_service._QUEUE_NAMES` includes `os.getenv("DOWNTIME_WORKER_QUEUE", "downtime-query")` (verified by unit test)
- `downtime-query` systemd unit file (`deploy/mes-dashboard-downtime-worker.service`) is present in the PR
- `contracts/ci/ci-gate-contract.md` schema-version bumped to 1.3.21 in the same PR (already recorded)
