---
change-id: job-registry-central
schema-version: 0.1.0
last-changed: 2026-06-13
risk: medium
tier: 3
---

# Test Plan: job-registry-central

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_job_registry.py::TestJobRegistryModule::test_module_exports_required_symbols | 0 |
| AC-2 | unit | tests/test_job_registry.py::TestJobRegistryModule::test_register_returns_stored_config | 0 |
| AC-2 | unit | tests/test_job_registry.py::TestJobRegistryModule::test_get_returns_none_for_unknown_job_type | 0 |
| AC-2 | unit | tests/test_job_registry.py::TestJobRegistryModule::test_list_returns_all_registered_types | 0 |
| AC-3 | unit | tests/test_job_registry.py::TestEnqueueJobDynamic::test_dispatches_registered_job_type | 0 |
| AC-3 | unit | tests/test_job_registry.py::TestEnqueueJobDynamic::test_returns_error_tuple_for_unregistered_type | 0 |
| AC-3 | unit | tests/test_job_registry.py::TestEnqueueJobDynamic::test_respects_should_enqueue_false | 0 |
| AC-4 | unit | tests/test_job_registry.py::TestJobServiceRegistrations::test_each_service_registers_exactly_one_job_type | 0 |
| AC-5 | unit | tests/test_async_query_job_service.py | 0 |
| AC-6 | unit | tests/test_job_registry.py | 0 |
| AC-7 | unit | tests/test_async_query_job_service.py | 0 |
| AC-8 | contract | tests/test_job_registry.py | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | All registry logic, dispatch behavior, and service registration; mock RQ queue at enqueue boundary |
| contract | 1 | `cdd-kit validate` gate only; no new contract files required |

## Test Execution Ladder

| phase | required | command source | max failures |
|---|---:|---|---:|
| collect | yes | `pytest tests/test_job_registry.py tests/test_async_query_job_service.py --collect-only -q` | 1 |
| targeted | yes | `pytest tests/test_job_registry.py -v` | 1 |
| changed-area | yes | `pytest tests/test_job_registry.py tests/test_async_query_job_service.py -v` | 1 |
| contract | if affected | `cdd-kit validate` | 1 |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| (none) | — | AC-5/AC-7 guarantee existing tests are unchanged |

## Out of Scope

- E2E / Playwright
- Real-Redis integration (nightly gate)
- Stress / soak
- Data-boundary / monkey
- Route dispatch tests (routes unchanged per AC-5)

## Notes

- `tests/test_job_registry.py` is a new file; backend-engineer authors it guided by this plan.
- AC-4 registration test imports all 8 service modules and asserts `list_registered_job_types()` contains all 8 type strings (count == 8).
- AC-3 `should_enqueue=False` asserts `(None, None)` returned without calling the queue mock.
- AC-7 zero-regression: run existing suite with no modifications; any failure blocks the gate.
- Registry isolation: each test must reset `_REGISTRY` via monkeypatch or autouse fixture to prevent order-dependence.
