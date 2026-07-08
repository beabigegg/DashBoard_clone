# Archive — production-achievement-async-spool

## Change Summary
Migrated the 生產達成率 (production-achievement) report from a synchronous request-path
Oracle query (which exceeded the 55s fast-pool `call_timeout` → DPY-4024) to the
established async pattern: an RQ `BaseChunkedDuckDBJob` worker fans Oracle out in TIME
chunks and writes a SPECNAME-grain DuckDB parquet spool; the browser polls the job,
downloads the parquet, and runs PA-06 (SPECNAME→workcenter_group rollup) + PA-07 (target
join + achievement_rate) in DuckDB-WASM. Feature was pre-launch → clean sync→async
replacement, `always_async=True`, no dual-path fallback.

## Final Behavior
- `GET /api/production-achievement/report`: spool-hit → 200 with `spool_download_url` +
  `spec_workcenter_map` + `targets_map`; spool-miss → 202 `{async, job_id, status_url}`;
  always_async + no worker → 503. Frontend polls `GET /api/job/<id>?prefix=production-achievement`,
  then re-issues `GET /report` (spool-hit) and renders via DuckDB-WASM.
- PA-06/PA-07 computation relocated backend→frontend (semantics unchanged; `build_achievement_rows()`
  retained as the test-only golden).
- No Oracle query runs on the Flask request thread anymore.

## Final Contracts Updated
- `contracts/api/api-contract.md` (+ api-inventory, openapi.json + root mirror): Type-B async endpoint.
- `contracts/data/data-shape-contract.md` §3.28: SPECNAME-grain spool schema + `_SCHEMA_VERSION`.
- `contracts/env/env-contract.md` (+ env.schema.json, .env.example.template, root .env.example):
  `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` (+ `_WORKER_QUEUE`, `_JOB_TIMEOUT_SECONDS`) + gunicorn↔worker parity.
- `contracts/business/business-rules.md`: PA-06/PA-07 compute-locus note + PA-08.
- `contracts/ci/ci-gate-contract.md`: production-achievement-async-spool gate note.
- ADR-0016: chunk-seam re-aggregation deviation.

## Final Tests Added / Updated
- `tests/test_production_achievement_unified_job.py` (chunk-seam re-aggregation KEY test).
- `tests/test_frontend_production_achievement_parity.py` (dual-tier parity vs golden).
- `tests/integration/test_production_achievement_{rq_async,resilience}.py`; `tests/stress/test_production_achievement_stress.py`.
- `tests/contract/test_env_production_achievement_unified_flag.py`; `_APPROVED_CALLERS` + job-registry + spool-allowlist + env-default assertions.
- Frontend: `useProductionAchievementDuckDB.test.ts`, `App.test.ts`, rewritten `useProductionAchievement.test.ts`.
- Playwright `production-achievement-async.spec.ts` (+ monkey spec); 3 pre-existing stale specs updated to the new shape.
- Route signature-bind regression test (`test_report_enqueue_params_bind_to_worker_signature`).

## Final CI/CD Gates
- New Tier-1 required steps: `production-achievement-async-e2e` (frontend-tests.yml, timeout-minutes: 8),
  `worker-env-parity-static` (backend-tests.yml). Stress/soak weekly/manual. New systemd unit
  `deploy/mes-dashboard-production-achievement-worker.service`. See `ci-gates.md`.

## Production Reality Findings
The mocked test suite passed the gate, but **four defects surfaced only by driving the real
enqueue→worker→Oracle flow and by the first real CI run** (see `agent-log/production-verification.yml`):
- **PV-1**: dev launcher `scripts/start_server.sh` (one RQ worker per queue) had no
  `production-achievement-query` worker — only the prod systemd unit existed. Job enqueued, never consumed.
- **PV-2**: enqueue↔worker signature mismatch — route passed flat `params={start_date,end_date}` but
  `enqueue_job_dynamic` spreads params into kwargs while the worker is `(job_id, params)` → TypeError.
  Nested as `params={"params": {...}}`. The route unit test had mocked `enqueue` and asserted the wrong
  shape, so it never caught it.
- **PV-3**: `rq worker --job-execution-timeout` is invalid under the pinned `rq>=1.16.0,<2.0.0`; removed
  from the dev launcher and all four deploy units (PA + pre-existing downtime/wip/hold-history).
- **CI stall**: `production-achievement-async.spec.ts` burned a 20s `waitForFunction` per test on the
  no-dev-server path → ~25 min slow-fail. Fixed with the sibling's sub-second body-length skip check
  (5.8s in CI now).

## Lessons Promoted to Standards
1. **New-worker deploy checklist** (PV-1 + PV-3) → `contracts/ci/ci-gate-contract.md` §New RQ Worker Deploy Checklist (schema-version 1.3.36→1.3.37 + CHANGELOG) + one-line CLAUDE.md pointer in "Service architecture": every new `execute_*_job` worker must be wired into BOTH `deploy/*.service` AND `scripts/start_server.sh`; never pass `rq worker --job-execution-timeout` (invalid under pinned rq<2.0.0).
2. **Async route↔worker signature-bind test** (PV-2) → `docs/architecture/test-discipline.md` §Async Route↔Worker Signature Contract + one-line CLAUDE.md pointer in "Test coverage discipline": mocked-enqueue route tests must `inspect.signature(worker_fn).bind(**kwargs)`.
3. **Playwright fast no-server bail** (CI-stall fix, commit a83e7331) → `docs/architecture/ci-workflow.md` §Playwright CI-Safe Specs (extended) + folded CLAUDE.md "CI workflow" bullet: fast `<50`-char body pre-check before any per-test `waitForFunction`.

Evidence: `agent-log/production-verification.yml` (PV-1/PV-2/PV-3); commits 4b48c570, a83e7331.

## Follow-up Work
- SS-1 (non-blocking): `heavy_query_slot` is advisory/fail-open; act before scaling this worker's queue to 2+ processes.
- `frontend/tsconfig.json` does not include `production-achievement` (pre-existing from the kanban change); type-check is informational.
- UX-3 (filter-only re-download efficiency), UX-4/UX-5 (pre-existing).
- ci-gates.md `dual-tier-parity` row description is slightly stale (test is stronger than described).

## Cold Data Warning
This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
