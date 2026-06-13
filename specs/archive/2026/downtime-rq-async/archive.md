# Archive: downtime-rq-async

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Phase 3-A of the downtime-analysis async migration. Added an RQ async execution path to `POST /api/downtime-analysis/query`: long-range queries (≥ `DOWNTIME_ASYNC_DAY_THRESHOLD`, default 30 days) return HTTP 202 `{async, job_id, status_url}` when `DOWNTIME_ASYNC_ENABLED=true` and a worker is available; short-range queries continue returning HTTP 200 synchronously. The new `downtime_query_job_service.py` wraps the existing `query_downtime_dataset_raw()` without modification (ADR-0003/DA-11 compliance), emitting pct milestones 5→15→60→90→100. Frontend drives `AsyncQueryProgress.vue` on 202; short-range UX is unchanged. Dispatched via the Phase-2 `enqueue_job_dynamic()` / `register_job_type()` registry. Soft rollback: `DOWNTIME_ASYNC_ENABLED=false`.

## Final Behavior

- `POST /api/downtime-analysis/query` with day span ≥ 30 → HTTP 202 `{async: true, job_id, status_url: "/api/job/<id>?prefix=downtime"}` (when both flags true + worker up)
- Day span < 30 → HTTP 200 synchronous path unchanged
- Worker fn writes `downtime_analysis_base_events` then `downtime_analysis_job_bridge` parquets atomically (DA-11); completes job with `query_id`
- Frontend polls → renders progress bar → on finish loads both spools; cancel sends best-effort abandon; LoadingOverlay suppressed while async active
- New RQ queue: `downtime-query`; new systemd unit: `mes-dashboard-downtime-worker.service`

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| `contracts/api/api-contract.md` | 1.16.0 → 1.17.0 | §7 Type-B entry + §10 note: 202 async shape, prerequisite `DOWNTIME_BROWSER_DUCKDB=true` |
| `contracts/env/env-contract.md` | 1.0.7 → 1.0.8 | §Async Worker — Downtime Query: 4 new DOWNTIME_* vars with pinned defaults |
| `contracts/data/data-shape-contract.md` | 1.14.0 → 1.15.0 | §1.4 job-status note; new §3.14 (202 envelope, job result payload, pct milestones, path decision) |
| `contracts/business/business-rules.md` | 1.18.0 → 1.19.0 | ASYNC-DA-01 rule (dual-flag prerequisite); decision table 2 new rows |
| `contracts/ci/ci-gate-contract.md` | 1.3.20 → 1.3.21 | §downtime-rq-async Gate Compatibility Note (worker provisioning, parquet schema gate) |

## Final Tests Added / Updated

| file | added |
|---|---|
| `tests/test_downtime_analysis_routes.py` | `TestDowntimeAsyncQuery` (5 tests), `TestDowntimeJobDispatch::test_job_type_registered` |
| `tests/test_downtime_analysis_service.py` | `TestDowntimeAsyncWorker` (2 tests), `TestDowntimeAsyncEnvVars` (4 tests) |
| `tests/test_rq_monitor_service.py` | Updated queue count assertion 6→7 |
| `tests/integration/test_downtime_rq_async.py` | `TestDowntimeAsyncDispatch` (2 tests), `TestDowntimeAsyncParity` (2 tests) — `pytestmark=integration_real` |
| `tests/e2e/test_downtime_analysis_e2e.py` | `TestDowntimeAsyncResilience` (4 tests) |
| `frontend/tests/playwright/downtime-analysis.spec.js` | AC-5a (202→polling→progress→results), AC-5b (200 sync), resilience |

Full: 4483 unit tests pass; 183 targeted tests pass. Integration parity (AC-3, real Oracle) is nightly gate.

## Final CI/CD Gates

- **Tier 1 (PR-required)**: contract-validate, lint, unit-mock-integration, frontend-unit, css-governance, playwright-resilience
- **Tier 3 (nightly)**: `nightly-integration` — AC-3 parity + DA-11 atomic spool write vs real Oracle
- **Informational**: frontend-type-check, stress-load, soak
- Workflow edit required: add `npx playwright install --with-deps chromium` in `.github/workflows/frontend-tests.yml` before downtime spec
- Rollback: soft (`DOWNTIME_ASYNC_ENABLED=false`), hard (stop systemd unit), parquet cleanup only for schema-breaking rollback

## Production Reality Findings

- **`DOWNTIME_BROWSER_DUCKDB=true` is a prerequisite** for the async path (not just `DOWNTIME_ASYNC_ENABLED`). The route gates async on `_BROWSER_DUCKDB_ENABLED and _ASYNC_ENABLED`. This coupling was undocumented initially; contract-reviewer identified it and it was added to api-contract §10 and business-rules ASYNC-DA-01. Contracts now reflect this.
- **`register_job_type()` is a module-level side effect**: tests must use `importlib.reload()` after clearing the registry dict; `monkeypatch.setattr` alone does not re-execute it. Documented in design.md §Open Risks; test pattern applied in `TestDowntimeJobDispatch`.
- **`is_async_available()` 60s cache window**: a worker that dies mid-window can receive a 202 for up to 60s; frontend retries on next query. Acceptable per resilience tests.
- **4 pre-existing e2e failures** (`TestSummaryEndpointIntegration`, `TestEventDetailMatchSourceNoneRowsPresent`) confirmed pre-existing, not caused by this change (verified by e2e-engineer agent-log).
- **LoadingOverlay/AsyncQueryProgress overlap**: ui-ux-reviewer found LoadingOverlay showed over progress bar during initial async load. Fixed: added `&& !asyncJobProgress.active` to the v-if condition.

## Lessons Promoted to Standards

| lesson | target | what was added | evidence |
|---|---|---|---|
| Worker env-var parity | `contracts/env/env-contract.md` §Async Worker — Downtime Query (1.0.8→1.0.9) | Added note: `mes-dashboard-downtime-worker.service` must export same `DOWNTIME_*` + DuckDB env as gunicorn; drift silently breaks AC-3 parity | `design.md §Open Risks:40-41` |
| LoadingOverlay/async-progress mutual exclusion | `contracts/css/css-contract.md` Rule 4.6 (1.8.1→1.8.2) | New rule: outer `LoadingOverlay` must be gated `v-if="... && !asyncJobProgress.active"` on any 202-dispatch page | `archive.md §Production Reality Findings`, `frontend-engineer.yml App.vue:460-470` |

Lessons 1 (dual-flag prerequisite), 2 (`importlib.reload()`), and 4 (soft/hard rollback) were already fully documented in current contracts and `CLAUDE.md` — no-op promotions.

## Follow-up Work

- Deploy `mes-dashboard-downtime-worker.service` in production; verify Admin Dashboard shows `downtime-query` queue with ≥1 worker.
- Monitor `nightly-integration` AC-3 parity gate (first real-Oracle run needed post-deploy).
- UI/UX non-blocking deferred items:
  - No dwell time for failed state in AsyncQueryProgress before ErrorBanner (medium)
  - `queued` phase shows generic copy "背景查詢中..." (low)
  - Cancel button missing explicit `aria-label` context (low)
