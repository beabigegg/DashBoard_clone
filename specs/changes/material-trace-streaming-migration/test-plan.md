---
change-id: material-trace-streaming-migration
schema-version: 0.1.0
last-changed: 2026-06-19
risk: high
tier: 1
---

# Test Plan: material-trace-streaming-migration

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path :: test function | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_material_trace_unified_job.py::test_flag_off_uses_legacy_concat_path | 1 |
| AC-2 | unit | tests/test_material_trace_unified_job.py::test_flag_on_enqueues_unified_job | 1 |
| AC-3 | unit | tests/test_material_trace_unified_job.py::test_flag_on_no_rq_returns_503_no_fallback | 1 |
| AC-4 | data-boundary | tests/test_material_trace_unified_job.py::test_spool_schema_equivalent_flag_off_vs_on | 1 |
| AC-4 | data-boundary | tests/integration/test_material_trace_rq_async.py::test_flag_parity_rowcount_and_dedup_key | 3 |
| AC-5 | soak | tests/integration/test_soak_workload.py::test_material_trace_peak_heap_nonlinear | 4 |
| AC-6 | unit | tests/test_material_trace_unified_job.py::test_no_memory_guard_call_on_unified_path_ast | 1 |
| AC-7 | contract | tests/contract/test_env_material_trace_flag.py::test_flag_default_off_pinned | 1 |
| AC-8 | data-boundary | tests/test_material_trace_unified_job.py::test_id_list_decomposes_1000_per_batch | 1 |
| AC-8 | stress | tests/stress/test_chunk_boundary.py::test_material_trace_1000_id_boundary | 4 |
| flag default | unit | tests/test_material_trace_unified_job.py::test_flag_constant_defaults_off | 1 |
| concurrency cap | stress | tests/stress/test_material_trace_stress.py::test_rq_to_oracle_concurrency_cap | 4 |
| resilience | resilience | tests/e2e/test_material_trace_e2e.py::test_oracle_redis_fault_midstream | 3 |
| e2e smoke | e2e | tests/e2e/test_material_trace_e2e.py::test_flag_on_full_trace_returns | 1 |

## Test Families Required

unit / contract / data-boundary / e2e / resilience / stress / soak  (no monkey/fuzz — no new input surface).

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | `pytest --collect-only` (includes new material-trace unified tests) | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | `pytest tests/test_material_trace_unified_job.py -v` | 1 | test-evidence.yml |
| changed-area | yes | `pytest tests/test_material_trace_*.py tests/integration/test_eap_alarm_rq_async.py -v` | 1 | test-evidence.yml |
| contract | yes (affected) | `cdd-kit validate --contracts` | 1 | test-evidence.yml |
| quality | n/a | — | 1 | — |
| full | final/CI | `cdd-kit test run --phase full` | 1 | test-evidence.yml |

Deferred: resilience+e2e-resilience → nightly (Tier 3); stress + soak (AC-5 peak-heap non-linearity, concurrency cap) → weekly (Tier 4).

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| (none) | — | flag default-off; legacy material-trace tests stay valid and must keep passing (AC-1) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Frontend material-trace specs (spool schema unchanged — non-goal).
- `base_chunked_duckdb_job` / `global_concurrency` mechanics tests (consumed unchanged).

## Notes

Pattern references: `tests/integration/test_eap_alarm_rq_async.py` (RQ-async + 503),
`tests/integration/test_rowcount_flag_parity.py` (flag parity). CI has no Redis: route
async tests must mock `is_async_available()=True` + enqueue fn (CLAUDE.md CI note).
