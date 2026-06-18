---
change-id: eap-alarm-analysis
schema-version: 0.1.0
last-changed: 2026-06-18
risk: high
tier: 1
---

# Test Plan: eap-alarm-analysis

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (EAP navigation category) | unit | tests/test_navigation_contract.py | 0 |
| AC-2 (spool-key composition, coarse-filter reuse) | unit | tests/test_eap_alarm_service.py::test_spool_key_composition | 0 |
| AC-2 (eap_alarm in _ALLOWED_NAMESPACES) | unit | tests/test_spool_routes.py::test_eap_alarm_in_allowed_namespaces | 0 |
| AC-2 (RQ job dispatch + parquet write) | integration | tests/integration/test_eap_alarm_rq_async.py | 1 |
| AC-3 (LAST_UPDATE_TIME mandatory filter guard → ValueError) | unit | tests/test_eap_alarm_service.py::test_missing_date_range_raises_value_error | 0 |
| AC-3 (Oracle JOIN → parquet write, index predicate present) | integration | tests/integration/test_eap_alarm_rq_async.py::TestEapAlarmWorkerFn | 1 |
| AC-4 (fine-filter options derived from DuckDB only) | integration | tests/integration/test_eap_alarm_rq_async.py::TestEapAlarmSpoolCacheHit | 1 |
| AC-4 (spool-miss returns 410 CACHE_EXPIRED) | integration | tests/integration/test_eap_alarm_rq_async.py::test_spool_miss_returns_410 | 1 |
| AC-4 (filter composable _lastCommitted re-sync) | unit | frontend/tests/unit/eap-alarm-filter.spec.js | 0 |
| AC-5 (AlarmCategory decode — 9 codes + unknown fallback) | unit | tests/test_eap_alarm_service.py::test_alarm_category_decode | 0 |
| AC-6 (summary/pareto/trend/detail DuckDB views) | e2e | tests/e2e/test_eap_alarm_e2e.py | 1 |
| AC-6 (Playwright: coarse-filter submit → view render cycle) | e2e | frontend/tests/playwright/eap-alarm.spec.js | 1 |
| AC-7 (detail row expansion reads DETAIL_PARAMS from spool — no extra Oracle query) | integration | tests/integration/test_eap_alarm_rq_async.py::test_detail_no_extra_oracle_query | 1 |
| AC-8 (CSS scoped to .theme-eap-alarm, css:check Rule 6) | unit | frontend/tests/playwright/eap-alarm.spec.js | 0 |
| EA-06 (_SCHEMA_VERSION constant pin) | unit | tests/test_eap_alarm_service.py::test_schema_version_is_pinned | 0 |
| EA-07 (EQP type allowlist — invalid value → 400; empty list → 400) | unit | tests/test_eap_alarm_service.py::test_eqp_type_allowlist | 0 |
| All 7 EAP endpoints (response-sample capture) | contract | tests/contract/response-samples.json | 1 |
| Oracle failure during spool | resilience | tests/integration/test_eap_alarm_resilience.py::test_oracle_failure | 1 |
| Redis failure during spool | resilience | tests/integration/test_eap_alarm_resilience.py::test_redis_failure | 1 |
| Cold spool 410 on fine-filter call | resilience | tests/integration/test_eap_alarm_resilience.py::test_cold_spool_fine_filter_returns_410 | 1 |
| In-flight job abort on page unload | resilience | tests/integration/test_eap_alarm_resilience.py::test_inflight_abort | 1 |
| Malformed alarm rows in spool | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_malformed_alarm_rows | 1 |
| Unknown AlarmCategory code → "未知" fallback | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_unknown_category_fallback | 1 |
| Null DETAIL_PARAMS — detail_params field null in response | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_null_detail_params | 1 |
| Empty LOT_ID — lot_id null in response, no crash | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_empty_lot_id | 1 |
| Large AlarmText (>500 chars) — pareto/detail render without truncation error | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_large_alarm_text | 1 |
| All-null ALARM_TEXT rows — alarm_text_options list excludes nulls | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_all_null_alarm_text | 1 |
| Zero-row spool — empty state, no 500 | data-boundary | tests/integration/test_eap_alarm_data_boundary.py::test_zero_row_spool | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | spool-key hashing (EA-01), AlarmCategory decode (EA-05, all 9 known codes + unknown), SQL builder mandatory-filter guard (EA-03), EQP allowlist (EA-07), _SCHEMA_VERSION constant pin (EA-06), navigation category presence, _ALLOWED_NAMESPACES membership |
| contract | 1 | response-samples.json capture for all 7 EAP endpoints; openapi.json regenerated after EapAlarmSpoolJobAccepted schema added |
| integration | 1 | Mirror test_hold_history_rq_async style (pytestmark = pytest.mark.integration_real); job dispatch, parquet write, progress milestones, job-failure path, spool cache-hit, spool-miss 410, fine-filter kwargs per-kwarg assertion, no Oracle re-query after spool |
| e2e | 1 | GunicornHarness + Playwright; submit button clicked in beforeEach before asserting detail table; page.goto().catch(()=>{}) + early-return guard for resilience specs |
| resilience | 1 | Oracle down during spool, Redis down, cold-spool 410 on fine-filter, in-flight abort; pageRendered guard checks .theme-eap-alarm presence |
| data-boundary | 1 | All via DuckDB spool replay with synthetic parquet fixtures (no live Oracle); null/large/unknown/empty row shapes |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_spool_routes.py | extend | add test_eap_alarm_in_allowed_namespaces alongside existing namespace membership tests |
| tests/test_navigation_contract.py | extend | assert EAP top-level category present in navigation structure |

## Out of Scope

- Stress / soak (read-only page, proven spool pattern; agent-log evidence sufficient)
- Monkey testing (not required at Tier 1 for read-only report page; per change-classification.md)
- Visual snapshot regression (evidence captured in agent-log/visual-reviewer.yml, not a pre-merge gate)
- Real Oracle integration tests (Tier 3 nightly lane only; not pre-merge)
- Export/CSV (EAP ALARM has no export endpoint)

## Notes

- `pytestmark = pytest.mark.integration_real` required on `test_eap_alarm_rq_async.py`; check before adding mock tests there.
- `_SCHEMA_VERSION` test must use `monkeypatch.setattr()` — module-level constant frozen at import; `setenv` does not work.
- Playwright spec registers catch-all routes FIRST, specific routes LAST (LIFO ordering rule from ci-workflow.md).
- Per-kwarg assertions (`call_args.kwargs[key]`) required throughout; `assert_called_once_with` whitelist forbidden.
- Test BOTH spool-hit and spool-miss paths for every fine-filter kwarg (test-discipline rule).
