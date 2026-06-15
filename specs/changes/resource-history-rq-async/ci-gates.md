# CI Gates — resource-history-rq-async

## Required Gates (pre-merge, blocking)

| gate | tier | trigger | command/workflow | artifact |
|---|---:|---|---|---|
| contract-validate | 0 | local pre-PR | `cdd-kit validate` | — |
| lint | 0 | local / PR | `ruff check .` | — |
| unit-mock-integration | 1 | PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | PR | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | PR | `cd frontend && npm run css:check` | governance report |
| playwright-resilience | 1 | PR | `cd frontend && npx playwright test tests/playwright/resilience/` | playwright trace |
| playwright-data-boundary | 1 | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` | playwright trace |
| resource-history-async-e2e | 1 | PR | `cd frontend && npx playwright test tests/playwright/resource-history-async.spec.ts` | playwright trace |

Unit gate covers: test-plan.md rows TP-01 to TP-07 (AC-1/AC-2 threshold branch, AC-5 env-var defaults via `monkeypatch.setattr`, AC-6 flag-off fallback, AC-7 owner-in-params, `register_job_type()` reload pattern).

`resource-history-async-e2e` covers: test-plan.md rows TP-E2E-01 (long-span → 202 → poll → result), TP-E2E-02 (short-span → 200 sync unaffected), TP-E2E-03 (AC-4 `useAsyncJobPolling` wiring, no duplicated polling). Requires `npx playwright install --with-deps chromium` step added before this spec in `frontend-tests.yml` (per CLAUDE.md CI Workflow Note — "New Playwright specs: add install step in CI before running tests"; precedent: downtime-rq-async gate-compat note in ci-gate-contract.md).

## Informational Gates (pre-merge, non-blocking)

| gate | tier | trigger | command/workflow | artifact |
|---|---:|---|---|---|
| frontend-type-check | 2 | PR | `cd frontend && npm run type-check` | — |
| visual-regression | 2 | PR | Playwright screenshot diff (existing AsyncQueryProgress.vue reused; no new visual surface expected) | screenshot diff |

Both gates use `continue-on-error: true`. Promotion to required follows standard policy (20 calendar days / 60 runs, pass rate above threshold, failures triaged, runtime within limit, owner assigned).

## Nightly / Weekly Gates

| gate | tier | trigger | command/workflow | notes |
|---|---:|---|---|---|
| nightly-integration | 3 | nightly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | includes `test_resource_history_rq_async.py`; enqueue→poll→view round trip + parity (AC-3, AC-8); failure triage within 1 business day |
| stress-load | 4 | weekly schedule / dispatch | `pytest tests/stress/ -m "stress or load"` | `test_resource_history_stress.py` concurrent async-job load (test-plan.md TP-ST-01) |
| soak | 4 | weekly schedule / dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` | long-running worker soak evidence for `stress-soak-report.md` |

## Manual Gates

| gate | tier | trigger | notes |
|---|---:|---|---|
| worker-registration-verify | 5 | pre-deploy manual | Confirm `resource-history-query` RQ worker is registered in `scripts/start_server.sh` AND `supervisord.conf` (AC-8); no automated gate can verify deployment topology. Operator must also confirm `rq_monitor_service._QUEUE_NAMES` includes `os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")`. |
| admin-dashboard-queue-verify | 5 | post-deploy manual | Verify Admin Dashboard `/admin/api/worker/status` shows `resource-history-query` queue with ≥ 1 active worker before serving traffic. |

## Workflow

All gates map to existing workflow jobs. No new workflow files are required.

| job | file | gates covered |
|---|---|---|
| `unit-and-integration-tests` | `backend-tests.yml` | `lint`, `unit-mock-integration` |
| `e2e-critical` (existing) | `frontend-tests.yml` | `playwright-resilience`, `playwright-data-boundary`, `resource-history-async-e2e` |
| `frontend-unit-tests` | `frontend-tests.yml` | `frontend-unit`, `css-governance`, `frontend-type-check` |
| `nightly-integration-real` | `backend-tests.yml` | `nightly-integration` |
| `stress-tests` | `stress-tests.yml` | `stress-load`, `soak` |

**Required workflow edit** — add `npx playwright install --with-deps chromium` before the `resource-history-async-e2e` spec invocation in `frontend-tests.yml` `e2e-critical` job (if not already present for the job run). Concurrency for `e2e-critical` (already configured):

```yaml
concurrency:
  group: ${{ github.ref }}-e2e-critical
  cancel-in-progress: true
```

Artifact retention: Playwright traces → `retention-days: 7` (30 on failure); nightly test report → `retention-days: 30`; stress/soak reports → `retention-days: 90`.

## Promotion Policy

`resource-history-async-e2e` enters as required (Tier 1) immediately — same precedent as `hold-history-rq-async` (hold-history-e2e required from day one). Informational gates (`frontend-type-check`, `visual-regression`) promote to required after: 20 calendar days or 60 runs, pass rate above threshold, failures triaged, runtime within limit, owner assigned. Nightly gate failures must be triaged within 1 business day per ci-gate-contract.md §Rollback Policy. Weekly soak failure triggers production-readiness review.

## Rollback Policy

**Soft rollback** (zero-downtime): Set `RESOURCE_ASYNC_ENABLED=false` in environment; `kill -HUP <gunicorn-pid>`. All `POST /api/resource-history/query` calls return HTTP 200 synchronously regardless of day span. No spool cleanup required when rolling back to sync — the `resource_history` spool namespace is path-identical between sync and async paths.

**Hard rollback** (worker removal): Stop the `resource-history-query` RQ worker systemd unit. In-flight jobs time out at `RESOURCE_JOB_TIMEOUT_SECONDS` (default value TBD by spec-architect / backend-engineer); frontend receives terminal error status and retries on next user query; `is_async_available()` returns False so all subsequent queries fall back to sync automatically.

**Parquet cleanup** (schema-breaking rollback only): If the async spool schema ships and must be abandoned, run `rm -f tmp/query_spool/resource_history/*.parquet` and bump `_SCHEMA_VERSION` in the worker service (per cache-spool-patterns.md). Not required for flag-off rollback.

## Merge Eligibility

Mergeable when all Tier 1 required gates pass: `contract-validate`, `lint`, `unit-mock-integration`, `frontend-unit`, `css-governance`, `playwright-resilience`, `playwright-data-boundary`, `resource-history-async-e2e`. Informational gates do not block merge. Nightly gate failure after merge must be triaged within 1 business day.
