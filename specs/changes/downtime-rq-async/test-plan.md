---
change-id: downtime-rq-async
schema-version: 0.1.0
last-changed: 2026-06-13
risk: high
tier: 1
---

# Test Plan: downtime-rq-async

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1: long-range → HTTP 202 `{async,job_id,status_url}` | unit | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_long_range_returns_202` | 0 |
| AC-2a: short-range → HTTP 200 sync (no regression) | unit | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_short_range_returns_200` | 0 |
| AC-2b: flag disabled → HTTP 200 sync | unit | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_flag_disabled_returns_200` | 0 |
| AC-2c: worker unavailable → HTTP 200 fallback | unit | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_worker_unavailable_returns_200` | 0 |
| AC-3: RQ worker fn parity vs sync path | data-boundary | `tests/integration/test_downtime_rq_async.py::TestDowntimeAsyncParity::test_worker_fn_parity_vs_sync` | 3 |
| AC-4a: DOWNTIME_ASYNC_ENABLED default true | unit | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncEnvVars::test_default_async_enabled_true` | 0 |
| AC-4b: DOWNTIME_ASYNC_DAY_THRESHOLD default 30 | unit | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncEnvVars::test_default_day_threshold_30` | 0 |
| AC-4c: DOWNTIME_WORKER_QUEUE default value pinned | unit | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncEnvVars::test_default_worker_queue` | 0 |
| AC-4d: DOWNTIME_JOB_TIMEOUT_SECONDS default value pinned | unit | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncEnvVars::test_default_job_timeout` | 0 |
| AC-5a: long-range → AsyncQueryProgress renders → results load | e2e | `frontend/tests/playwright/downtime-analysis.spec.js::should show async progress for long range query` | 1 |
| AC-5b: short-range → no progress bar, results direct | e2e | `frontend/tests/playwright/downtime-analysis.spec.js::should show sync results for short range query` | 1 |
| AC-6a: pct milestones 5→15→60→90→100 emitted in order | unit | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncWorker::test_pct_milestones_sequence` | 0 |
| AC-6b: DA-11 — base hit + job bridge miss → loud 500 on worker path | unit | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncWorker::test_atomicity_base_hit_bridge_miss_raises_500` | 0 |
| AC-7a: `register_job_type("downtime",...)` fires on app startup | unit | `tests/test_downtime_analysis_routes.py::TestDowntimeJobDispatch::test_job_type_registered` | 0 |
| AC-7b: `enqueue_job_dynamic()` routes to downtime-query queue | integration | `tests/integration/test_downtime_rq_async.py::TestDowntimeAsyncDispatch::test_enqueue_to_downtime_queue` | 1 |
| Resilience: job timeout → status=failed | resilience | `tests/e2e/test_downtime_analysis_e2e.py::TestDowntimeAsyncResilience::test_job_timeout_status_failed` | 3 |
| Resilience: cancel mid-job → frontend abandon flow | resilience | `tests/e2e/test_downtime_analysis_e2e.py::TestDowntimeAsyncResilience::test_cancel_mid_job_abandon` | 3 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Threshold branch, env-var defaults (monkeypatch.setattr not setenv), pct milestones, DA-11 atomicity, job-type registration (importlib.reload) |
| contract | 1 | 202/200 response shapes vs api-contract §7; env-contract 4 DOWNTIME_* vars with pinned defaults via `cdd-kit validate` |
| integration | 1 | Dispatch via enqueue_job_dynamic to correct queue; `pytestmark = pytest.mark.integration_real` required |
| data-boundary | 3 | AC-3 worker fn vs sync path byte/row-identical base_events + job_bridge parquet; nightly gate, real Oracle |
| e2e | 1 | Playwright: long/short-range UX branches; extend existing `downtime-analysis.spec.js` |
| resilience | 3 | Job timeout + cancel mid-job; nightly gate; worker availability 60s-cache race noted in design.md |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_downtime_analysis_service.py::TestTwoParquetAtomicity` | extend | Add worker-path fixture variant for AC-6b; do not duplicate base fixture |

## Out of Scope

- Visual review (AsyncQueryProgress is a pre-existing Phase-1 shared component; no new CSS)
- Monkey/fuzz tests (not warranted per change-classification.md)
- Stress/soak (consideration only; promote to report if high-risk load results surface)
- ADR-0003 ROW_NUMBER chunking guard (already covered by `TestDowntimeMigration`; extend, do not duplicate)

## Notes

- All AC-4 env-var tests must use `monkeypatch.setattr()` on module-level constants — not `os.environ`; constants freeze at import.
- AC-7a registration must use `importlib.reload()` after clearing the registry dict; `setattr` alone skips the `register_job_type(...)` side-effect re-run.
- `tests/integration/test_downtime_rq_async.py` must carry `pytestmark = pytest.mark.integration_real` (matches every other file in tests/integration/).
- AC-3 parity depends on real Oracle + env parity between worker unit and gunicorn (open risk in design.md §Open Risks).
