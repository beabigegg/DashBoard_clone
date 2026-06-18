# CI/CD Gate Plan — eap-alarm-analysis

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local / PR | `ruff check .` | — |
| unit-mock-integration | 1 | yes | push / PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | push / PR | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | PR | `cd frontend && npm run css:check` | governance report |
| response-shape-validate | 1 | yes | push / PR | `cdd-kit validate --contracts` | — |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js tests/playwright/eap-alarm.spec.js` | playwright trace |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` | playwright trace |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` | playwright trace |
| visual-regression | 2 | informational | PR | (TBD — Playwright screenshot diff) | screenshot diff |
| nightly-integration | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report |

Tests-first stubs to write before implementation (per test-plan.md):
- `tests/test_spool_routes.py::test_eap_alarm_in_allowed_namespaces`
- `tests/test_eap_alarm_service.py::test_spool_key_composition`
- `tests/test_eap_alarm_service.py::test_missing_date_range_raises_value_error`

## workflow

No new gate tiers, job IDs, or CI commands are introduced. All new tests land in existing
gate commands:

- **unit-mock-integration** (`contract-and-fast-tests` job): covers all Tier 0/1 unit tests
  in `tests/test_eap_alarm_service.py` (spool-key composition, AlarmCategory decode, LAST_UPDATE_TIME
  mandatory-filter guard, EQP allowlist, `_SCHEMA_VERSION` pin) and
  `tests/test_spool_routes.py::test_eap_alarm_in_allowed_namespaces`.
  Also covers `tests/test_navigation_contract.py` EAP top-level category assertion.
  Frontend composable tests (`frontend/tests/unit/eap-alarm-filter.spec.js`) are picked up
  by the **frontend-unit** gate.

- **playwright-critical-journeys** (`e2e-critical` job): `tests/playwright/eap-alarm.spec.js`
  was registered in `contracts/ci/ci-gate-contract.md §1.3.25`. Spec exercises the full
  coarse-filter submit → spool → fine-filter → Pareto/trend/detail render cycle.
  Register catch-all routes FIRST, specific routes LAST (LIFO ordering rule).
  Playwright `pageRendered` guard checks `.theme-eap-alarm` presence, not body length.
  Click submit in `beforeEach` before asserting `DetailTable` content (spec pattern per
  ci-workflow.md: `DetailTable` only renders after `queryId` is set).

- **playwright-resilience** (`e2e-critical` job, resilience sub-suite): picks up
  `tests/playwright/resilience/` specs for Oracle/Redis-down, cold-spool 410, in-flight
  abort. Use `page.goto(...).catch(()=>{})` + early-return guard for ECONNREFUSED safety.

- **playwright-data-boundary** (`e2e-critical` job, data-boundary sub-suite): picks up
  `tests/playwright/data-boundary/` specs backed by synthetic parquet fixtures; covers
  null/large-text/unknown-category/empty-lot/zero-row shapes (test-plan.md data-boundary rows).

- **nightly-integration** (Tier 3): `tests/integration/test_eap_alarm_rq_async.py`
  (`pytestmark = pytest.mark.integration_real`; mirrors `test_hold_history_rq_async` style),
  `tests/integration/test_eap_alarm_resilience.py`, and `tests/integration/test_eap_alarm_data_boundary.py`.
  Per test-plan.md: assert spool-hit and spool-miss paths per fine-filter kwarg; detail row
  expansion issues no extra Oracle query; progress milestones 5→15→90→100.

## promotion policy

All Tier 1 required gates (unit-mock-integration, frontend-unit, css-governance,
response-shape-validate, playwright-critical-journeys, playwright-resilience,
playwright-data-boundary) MUST pass before merge. No exceptions.

`visual-regression` is informational and does not block merge. Promotion to required follows
the standard Informational Gate Promotion Policy in `ci-gate-contract.md §Informational Gate
Promotion Policy` (20 days / 60 runs / pass rate above threshold / runtime within limit /
owner assigned).

## rollback policy

**Zero-downtime path**: EAP ALARM has no flag-off path (always-async; no sync fallback).
Rollback requires full route removal.

**Ordered steps (complete before gunicorn restart)**:

1. Stop `mes-dashboard-eap-alarm-worker.service`. In-flight spool jobs abandon gracefully;
   frontend receives `410 CACHE_EXPIRED` and displays the standard cache-miss state.
2. `rm -f tmp/query_spool/eap_alarm/*.parquet` — parquet files are orphaned after route
   removal; schema is a breaking-change surface (EA-06 / `_SCHEMA_VERSION` pin).
3. Revert Blueprint registration in `src/mes_dashboard/app.py` (remove `eap_alarm_bp`
   import + `register_blueprint` call).
4. Revert portal-shell nav entry (remove EAP top-level category from navigation config).
5. Revert `docs/migration/` updates (`asset_readiness_manifest.json`,
   `route_scope_matrix.json`, `data/page_status.json`).

`EAP_ALARM_*` env vars (`EAP_ALARM_WORKER_QUEUE`, `EAP_ALARM_JOB_TIMEOUT_SECONDS`,
`EAP_ALARM_SPOOL_TTL`, `EAP_ALARM_SPOOL_DIR`) are default-optional in `env-contract.md`.
Leaving them set after rollback is harmless; no ops intervention required to clear them.

## Deploy Checklist

1. Set env vars (defaults sufficient if not overriding): `EAP_ALARM_WORKER_QUEUE`,
   `EAP_ALARM_JOB_TIMEOUT_SECONDS`, `EAP_ALARM_SPOOL_TTL`, `EAP_ALARM_SPOOL_DIR`
   (see `contracts/env/env-contract.md §Async Worker — EAP ALARM Spool`).
2. Start `mes-dashboard-eap-alarm-worker.service` **before** deploying/restarting gunicorn.
   New systemd unit; must be enabled and confirmed running.
3. Verify `eap_alarm` is present in `spool_routes._ALLOWED_NAMESPACES` — checked by
   `unit-mock-integration` gate via `test_eap_alarm_in_allowed_namespaces`.
4. Verify Admin Dashboard shows `eap-alarm` queue with >= 1 live worker
   (`rq_monitor_service._QUEUE_NAMES` must include `os.getenv("EAP_ALARM_WORKER_QUEUE", "eap-alarm-query")`).
5. Confirm `tests/playwright/eap-alarm.spec.js` is present in the `playwright-critical-journeys`
   gate command (already registered in `ci-gate-contract.md §1.3.25`).

## Merge Eligibility

mergeable when all Tier 1 required gates pass; visual-regression informational-risk only.
