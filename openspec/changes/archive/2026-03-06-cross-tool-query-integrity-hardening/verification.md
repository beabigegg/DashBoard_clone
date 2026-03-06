# Cross-Tool Query Integrity Hardening — Verification Evidence

Date: 2026-03-06

## Targeted backend suites

- `pytest -q tests/test_query_tool_routes.py tests/test_query_tool_service.py tests/test_query_tool_pagination_contract.py tests/test_material_trace_service.py tests/test_material_trace_routes.py tests/test_partial_failure_contract.py tests/test_event_fetcher.py tests/test_batch_query_engine.py tests/test_reject_dataset_cache.py tests/test_trace_routes.py tests/test_trace_job_service.py tests/test_mid_section_defect_service.py`
  - Result: `326 passed`
- `pytest -q tests/test_query_quality_contract.py`
  - Result: `5 passed`

## Trace / MSD regression suites

- Included in the consolidated backend run above.

## Frontend targeted suite

- `node --test --test-name-pattern "query-tool-composables|useLotDetail|useEquipmentQuery" tests/query-tool-composables.test.js`
  - Result: `pass (2 matched tests, 2 skipped by pattern)`

## Notes

- Full `frontend npm test` currently has pre-existing unrelated failures in:
  - `portal-shell-wave-a-chart-lifecycle.test.js` (missing source file path)
  - `report-filter-strategy.test.js` (reason param assertion mismatch)
- These failures are outside this change scope and were not introduced by this hardening change.
