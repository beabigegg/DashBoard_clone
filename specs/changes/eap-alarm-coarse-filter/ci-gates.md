# CI/CD Gate Review — eap-alarm-coarse-filter

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| Backend unit tests (TestAtLeastOneFilterRequired, TestLotIdNormalization, TestProductDimsFilter, TestSchemaVersionIsPinned==3, TestSpoolKeyComposition) — see test-plan.md §Test Families Required | 0 | yes | local + PR push | `pytest tests/test_eap_alarm_service.py` | pass/fail |
| Frontend unit tests (buildCoarseParams per-kwarg) — see test-plan.md AC-6 | 0 | yes | local + PR push | `cd frontend && npm run test -- eap-alarm-filter` | pass/fail |
| CSS compliance (FilterBar under .theme-eap-alarm) | 0 | yes | local + PR push | `cd frontend && npm run css:check` | pass/fail |
| Frontend type-check | 0 | yes | local + PR push | `cd frontend && npm run type-check` | pass/fail |
| Contract validation (openapi schema, business-rules EA-01/08/09/10, data-shape §3.17) | 1 | yes | PR push | `pip install jsonschema && cdd-kit validate --contracts` | pass/fail |
| OpenAPI sync check — both contracts/openapi.json AND contracts/api/openapi.json | 1 | yes | PR push | `cdd-kit openapi export --check` | pass/fail |
| Integration: coarse-filter worker SQL + route-forward (AC-1/AC-2, mock-based) | 1 | yes | PR push | `pytest tests/integration/test_eap_alarm_coarse_filter.py --run-integration` | pass/fail |
| Integration: data-boundary (whitespace/dup lot_ids, CHAR-padded CONTAINERNAME, >200 cap) — see test-plan.md AC-5 | 1 | yes | PR push | `pytest tests/integration/test_eap_alarm_data_boundary.py` | pass/fail |
| Integration: resilience (Oracle error during EXISTS, cache miss → empty arrays, all-empty → 400) — see test-plan.md AC-3/AC-7 | 1 | yes | PR push | `pytest tests/integration/test_eap_alarm_resilience.py` | pass/fail |
| E2E: LOT_ID textarea + TYPE/PKG/BOP MultiSelects + machines-optional submit — see test-plan.md AC-6 | 1 | yes | PR push | `cd frontend && npx playwright test eap-alarm-filters.spec.ts` | pass/fail |
| Real-Oracle / real-Redis integration | 3 | no | nightly schedule | existing `.github/workflows/nightly.yml` eap-alarm job | report |

## Workflow Changes Applied

No new workflow YAML is required. change-classification.md §CI/CD states "no new gate; existing eap-alarm gates cover it." All Tier-0 and Tier-1 gates execute under the existing `.github/workflows/ci.yml` PR required-check jobs. The Tier-3 nightly real-Oracle path is unchanged.

No new Makefile targets needed; all commands map to existing `pytest` and `npm run` invocations already wired in CI.

## Promotion Policy

A PR is eligible to merge when all seven Tier-1 required-status checks pass:

1. `unit-and-integration-tests` — pytest eap_alarm_service + four integration suites (test_eap_alarm_coarse_filter, test_eap_alarm_data_boundary, test_eap_alarm_resilience, test_eap_alarm_rq_async)
2. `frontend-unit-tests` — npm run test (eap-alarm-filter scope)
3. `css-check` — npm run css:check
4. `type-check` — npm run type-check
5. `contract-validation` — cdd-kit validate --contracts
6. `openapi-sync` — cdd-kit openapi export --check
7. `playwright-e2e` — eap-alarm-filters.spec.ts

The schema_version 2→3 bump self-promotes on deploy: new spool writes use v3 keys; v2 parquet ages out by Redis TTL. No manual deploy step is required.

## Rollback Policy

1. Revert the commit that bumps `_SCHEMA_VERSION` to 3 in `src/mes_dashboard/services/eap_alarm_cache.py`.
2. `rm -f tmp/query_spool/eap_alarm/*.parquet` on each gunicorn worker node to purge v3 parquet orphaned by the version downgrade. Redis spool pointers expire by TTL; no further Redis cleanup is needed.
3. `container_filter_cache` is a read-only consumer — no rollback footprint.
4. Redeploy previous image. No database migration to undo.

## Merge Eligibility

mergeable — no new workflow gates required; all Tier-1 required checks are covered by the existing CI workflow. Tier-3 real-Oracle coverage is informational and does not block merge.
