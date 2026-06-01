---
change-id: batch-rowcount-unification
schema-version: 0.1.0
last-changed: 2026-06-01
status: signed-off
---

# Regression Report: batch-rowcount-unification

## Scope

Flag=false (default) regression guard across all 7 services. Confirms existing
date-range path is unchanged when `USE_ROW_COUNT_CHUNKING=false`.

## Test Evidence

| test class | file | result |
|---|---|---|
| TestFlagFalseRegression (7 tests) | `tests/integration/test_rowcount_flag_parity.py` | PASS |
| TestFlagGating (4 tests) | `tests/test_batch_query_engine.py` | PASS |
| TestDowntimeMigration::test_spool_namespace_unchanged | `tests/test_downtime_analysis_service.py` | PASS |
| Full suite (4331 tests) | all test files | PASS — 0 regressions |

## Flag=false Assertion Per Service

Each `TestFlagFalseRegression` test asserts:
- `execute_plan` receives chunks with `chunk_start`/`chunk_end` keys (date-range format)
- No `start_row`/`end_row` keys present in any chunk dict
- Service entry function completes without calling `decompose_by_row_count`

| service | test method | result |
|---|---|---|
| production_history | `test_production_history_flag_false_uses_date_chunks` | PASS |
| hold_dataset | `test_hold_dataset_flag_false_uses_date_chunks` | PASS |
| reject_dataset | `test_reject_dataset_flag_false_uses_date_chunks` | PASS |
| resource_dataset | `test_resource_dataset_flag_false_uses_date_chunks` | PASS |
| job_query | `test_job_query_flag_false_uses_date_chunks` | PASS |
| mid_section_defect | `test_mid_section_defect_flag_false_uses_date_chunks` | PASS |
| downtime_analysis | `test_downtime_analysis_flag_false_uses_execute_plan` | PASS |

## Spool Namespace and Schema

`TestSpoolSchemaParity` and `TestSpoolLifecycle` confirm:
- `cache_prefix` values unchanged for all services under flag=false and flag=true
- Chunk key types are disjoint between paths (no key confusion)
- `downtime_analysis` spool namespace `downtime_analysis` preserved (DA-06)

## Conclusion

All flag=false regression assertions pass. Deployment with `USE_ROW_COUNT_CHUNKING=false`
(the default) introduces no behavioral change to any of the 7 services.

**Signed off by:** QA review (2026-06-01)
**Pre-condition for:** staging deploy and `USE_ROW_COUNT_CHUNKING=true` production enable
