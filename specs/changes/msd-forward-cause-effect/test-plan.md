---
change-id: msd-forward-cause-effect
schema-version: 0.1.0
last-changed: 2026-06-30
risk: high
tier: 1
---

# Test Plan: msd-forward-cause-effect

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | `tests/test_mid_section_defect_service.py::test_by_detection_loss_reason_aggregation` | 0 |
| AC-1 | unit | `tests/test_mid_section_defect_service.py::test_by_detection_loss_reason_top_n_truncation` | 0 |
| AC-2 | unit | `tests/test_mid_section_defect_service.py::test_loss_reason_workcenter_crosstab_builder` | 0 |
| AC-2 | unit | `tests/test_mid_section_defect_service.py::test_crosstab_top_n_folds_remainder_to_other` | 0 |
| AC-3 | unit | `tests/test_mid_section_defect_service.py::test_downstream_reject_trend_no_control_cohort` | 0 |
| AC-4 | unit (TDD – must fail before impl) | `tests/test_mid_section_defect_service.py::test_attribute_forward_defects_drops_split_descendant_FAILING` | 0 |
| AC-4 | unit (regression after fix) | `tests/test_mid_section_defect_service.py::test_attribute_forward_defects_lineage_rekeying_passes` | 0 |
| AC-4 | unit | `tests/test_mid_section_defect_engine.py::test_forward_lineage_spool_self_edge_included` | 0 |
| AC-5 | integration (xfail-flip) | `tests/test_unified_spool_integration.py::TestMsdChain::test_summary_from_spool` | 1 |
| AC-5 | integration (xfail-flip) | `tests/test_unified_spool_integration.py::TestMsdChain::test_full_chain_summary_detail_export_consistency` | 1 |
| AC-5 | integration | `tests/test_unified_spool_integration.py::test_forward_get_summary_duckdb_path_end_to_end` | 1 |
| AC-5 | integration | `tests/integration/test_material_trace_rq_async.py::test_forward_lineage_spool_write_read_roundtrip` | 1 |
| AC-6 | integration (tripwire removal) | `tests/test_unified_spool_integration.py::TestMsdChain::test_summary_from_spool` | 1 |
| AC-6 | integration (tripwire removal) | `tests/test_unified_spool_integration.py::TestMsdChain::test_full_chain_summary_detail_export_consistency` | 1 |
| AC-7 | data-boundary | `tests/test_mid_section_defect_service.py::test_amplification_kpi_detection_rate_zero_emits_null` | 0 |
| AC-7 | data-boundary | `tests/test_mid_section_defect_service.py::test_amplification_kpi_downstream_rate_zero_emits_zero_float` | 0 |
| AC-7 | data-boundary | `tests/test_mid_section_defect_service.py::test_amplification_kpi_both_rates_nonzero_correct_ratio` | 0 |
| AC-8 | e2e / Playwright | `frontend/tests/playwright/mid-section-defect.spec.ts::forward sankey click cross-filters heatmap` | 1 |
| AC-8 | e2e / Playwright | `frontend/tests/playwright/mid-section-defect.spec.ts::forward amplification KPI renders not dash when rates nonzero` | 1 |
| AC-8 | e2e / Playwright | `frontend/tests/playwright/mid-section-defect.spec.ts::forward detail table shows detection loss reason column` | 1 |
| AC-8 | e2e / Playwright | `frontend/tests/playwright/mid-section-defect.spec.ts::heatmap toggle switches chart type` | 1 |
| AC-8 | visual | `specs/changes/msd-forward-cause-effect/visual-review-report.md` (Sankey + heatmap + KPI screenshot bundle) | 1 |
| AC-4 + AC-5 | resilience | `tests/e2e/test_mid_section_defect_e2e.py::test_forward_spool_miss_falls_back_to_oracle` | 1 |
| AC-5 | resilience | `tests/e2e/test_mid_section_defect_e2e.py::test_rq_worker_failure_mid_orchestration_returns_error_not_500` | 1 |
| AC-4 + AC-5 | stress | `tests/stress/test_mid_section_defect_stress.py::test_spool_concurrent_forward_writes_no_collision` | 3 |
| AC-5 | stress | `tests/stress/test_mid_section_defect_stress.py::test_duckdb_forward_summary_under_load` | 3 |
| AC-1–AC-5 | contract | `tests/contract/samples/` (forward analysis + detail response-sample regen) | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Aggregation builders, lineage re-keying, amplification KPI; extend `tests/test_mid_section_defect_service.py` + new `tests/test_mid_section_defect_engine.py` |
| data-boundary | 0 | Divide-by-zero (null/"—"), empty lineage, Top-N boundary — unit-level, same files |
| contract | 1 | Response-sample regen + openapi sync; `tests/contract/samples/`; `cdd-kit validate --contracts && cdd-kit openapi export --check` |
| integration | 1 | DuckDB forward spool write→read + xfail-flip in `tests/test_unified_spool_integration.py`; RQ orchestration in `tests/integration/test_material_trace_rq_async.py` |
| e2e / Playwright | 1 | Sankey click, heatmap toggle, KPI, detail column — `frontend/tests/playwright/mid-section-defect.spec.ts` |
| visual | 1 | Sankey + heatmap + KPI screenshot bundle → `visual-review-report.md` |
| resilience | 1 | Spool-miss Oracle fallback; RQ failure mid-orchestration — `tests/e2e/test_mid_section_defect_e2e.py` |
| stress | 3 | Concurrent spool writes; DuckDB forward summary under load — `tests/stress/test_mid_section_defect_stress.py` |
| soak | 4 | Spool + concurrency surface soak — `tests/integration/test_soak_workload.py` |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_unified_spool_integration.py::TestMsdChain::test_summary_from_spool` | remove `xfail(strict=True)` marker | AC-6: DuckDB forward path now active; marker was a Phase-3 tripwire |
| `tests/test_unified_spool_integration.py::TestMsdChain::test_full_chain_summary_detail_export_consistency` | remove `xfail(strict=True)` marker | AC-6: same tripwire removal |

## Out of Scope

- Control-cohort / lift analysis (AC-3 is trend-only, no baseline cohort).
- Enlarged Oracle fetch stress (3b dropped; stress scoped to spool/DuckDB only).
- Frontend monkey-test report (cross-filter fuzz covered inline by Playwright).
- `tests/test_job_registry.py` count + `tests/test_query_cost_policy.py::_APPROVED_CALLERS` updates (backend-engineer owns per CLAUDE.md test-discipline rule; included here only as a reminder that the same PR must contain them).
- `env-contract.md` / `env.schema.json` update (no new env var unless a cutover flag is introduced).

## Notes

- AC-4 TDD order: `test_attribute_forward_defects_drops_split_descendant_FAILING` must be written first and confirmed failing against current code before the lineage re-keying fix is implemented.
- AC-6 is not a new test — it is the removal of two `xfail(strict=True)` markers; confirm both are gone and CI green.
- Playwright `@click` binding targets `<VChart>` not imperative `.on()` (frontend-patterns.md rule).
- Spool events keyed under `SEED_ID` at write time (design §Denormalize); DuckDB forward summary is single-pass GROUP BY, no per-query lineage JOIN.
- If a new `register_job_type()` call lands, `tests/test_job_registry.py` count must be updated in the same PR.
