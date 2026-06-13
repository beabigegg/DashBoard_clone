# CI/CD Gate Plan — hold-history-rq-async

## Change ID
hold-history-rq-async (Phase 3-B dynamic-RQ migration)

## Required Gates

| gate | tier | trigger | command | status | notes |
|---|---:|---|---|---|---|
| contract-validate | 0 | local pre-PR | `cdd-kit validate` | required | env-contract + ci-gate-contract must pass |
| lint | 0 | local / PR | `ruff check .` | required | — |
| unit-mock-integration | 1 | PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | required | covers AC-1 to AC-4, AC-6, AC-7; see §hold-history-rq-async Gate Compatibility Note in ci-gate-contract.md |
| frontend-unit | 1 | PR | `cd frontend && npm run test` | required | AsyncQueryProgress.test.js hold-history assertion |
| css-governance | 1 | PR | `cd frontend && npm run css:check` | required | no new CSS layer; fast pass expected |
| playwright-resilience | 1 | PR | `cd frontend && npx playwright test tests/playwright/resilience/` | required | Redis-down / job-failure fallback (AC-8) |
| playwright-data-boundary | 1 | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` | required | malformed / empty result handling |
| hold-history-e2e | 1 | PR | `cd frontend && npx playwright test tests/playwright/hold-history-flat-table.spec.js` | required | long-range → 202 → progress bar → result; short-range → 200 unchanged (AC-5) |

## Informational Gates

| gate | tier | trigger | command | status | notes |
|---|---:|---|---|---|---|
| frontend-type-check | 2 | PR | `cd frontend && npm run type-check` | informational | continue-on-error: true; promotion follows standard policy |
| visual-regression | 2 | PR | Playwright screenshot diff (TBD) | informational | reuses AsyncQueryProgress.vue; no new visual surface expected |

## Nightly Gates

| gate | tier | trigger | command | status | notes |
|---|---:|---|---|---|---|
| nightly-integration | 3 | weekly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | required (nightly) | includes test_hold_history_rq_async.py — enqueue_job_dynamic dispatch + parity test (AC-3); failure must be triaged within 1 business day |

## Workflow Gates

No new workflow jobs or files required. All gates map to existing jobs in `.github/workflows/contract-driven-gates.yml` and `frontend-tests.yml`.

The `hold-history-e2e` gate runs in the existing `e2e-critical` job. Add `npx playwright install --with-deps chromium` before the spec invocation if not already present for the job (per CLAUDE.md CI Workflow Notes and `downtime-browser-duckdb` Gate Compatibility Note precedent).

Concurrency for `e2e-critical` job (already configured):
```yaml
concurrency:
  group: ${{ github.ref }}-e2e-critical
  cancel-in-progress: true
```

Artifact retention: Playwright traces → `retention-days: 7` (30 on failure); nightly test report → `retention-days: 30`.

## Promotion Policy

Gates start at their assigned tier. `hold-history-e2e` enters as required (Tier 1) immediately — this is the same precedent set by `downtime-rq-async` (Phase 3-A). Informational gates (`frontend-type-check`, `visual-regression`) promote to required after: 20 calendar days or 60 runs, pass rate above threshold, failures triaged, runtime within limit, owner assigned.

## Rollback Policy

**Soft rollback** (zero-downtime): Set `HOLD_ASYNC_ENABLED=false` in environment; `kill -HUP <gunicorn-pid>`. All `POST /api/hold-history/query` calls return HTTP 200 synchronously. No spool cleanup required — `hold_dataset` spool namespace is identical between sync and async paths.

**Hard rollback** (worker removal): Stop `mes-dashboard-hold-history-worker.service`. In-flight jobs time out at `HOLD_JOB_TIMEOUT_SECONDS` (default 1800 s); frontend retries on next user query; `is_async_available()` returns False; all subsequent queries fall back to sync automatically.

**No parquet cleanup**: single `hold_dataset` spool namespace is path-identical for both sync and async; no orphaned files result from either rollback variant.

## Merge Eligibility

Mergeable when all Tier 1 required gates pass: `contract-validate`, `lint`, `unit-mock-integration`, `frontend-unit`, `css-governance`, `playwright-resilience`, `playwright-data-boundary`, `hold-history-e2e`. Informational gates do not block merge. Nightly gate failure after merge must be triaged within 1 business day per ci-gate-contract.md §Rollback Policy.
