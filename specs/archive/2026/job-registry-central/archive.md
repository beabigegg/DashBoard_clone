# Archive — job-registry-central

## Change Summary

Phase 2 of the dynamic-RQ migration plan: introduced a central async-job
registry (`job_registry.py`) so all RQ job types are declared in one place and
dispatchable by `job_type` string. Added `enqueue_job_dynamic()` to
`async_query_job_service.py` as a thin dispatcher that looks up a
`JobTypeConfig` by type string and delegates to the existing `enqueue_job()`
machinery. Appended one declarative `register_job_type()` call at module end
of each of the 8 existing job services. No route dispatch logic, no existing
`enqueue_xxx()` functions, no Redis schema, no API endpoints, and no contracts
were changed — the change is purely additive and fully backward-compatible.

## Final Behavior

- `job_registry.get_job_type_config("reject")` returns the `JobTypeConfig` for
  the reject job; returns `None` for an unknown type string.
- `enqueue_job_dynamic(job_type, owner, params)` dispatches any registered job
  type without the caller knowing the queue name or worker function reference.
- All 8 job types are self-registering at import time: reject, yield_alert,
  production_history, trace-lineage, msd-seed, msd-lineage, material-consumption,
  material-trace.
- Pre-existing `enqueue_xxx()` routes continue to work unchanged (AC-5).

## Final Contracts Updated

None. `contract-reviewer` verdict: CONTRACTS-UNCHANGED. No API, data-shape,
env, business, CSS, or CI/CD contract file was modified.

## Final Tests Added / Updated

New file — `tests/test_job_registry.py` (8 test nodes):
- `TestJobRegistryModule::test_module_exports_required_symbols`
- `TestJobRegistryModule::test_register_returns_stored_config`
- `TestJobRegistryModule::test_get_returns_none_for_unknown_job_type`
- `TestJobRegistryModule::test_list_returns_all_registered_types`
- `TestEnqueueJobDynamic::test_dispatches_registered_job_type`
- `TestEnqueueJobDynamic::test_returns_error_tuple_for_unregistered_type`
- `TestEnqueueJobDynamic::test_respects_should_enqueue_false`
- `TestJobServiceRegistrations::test_each_service_registers_exactly_one_job_type`

No changes to `tests/test_async_query_job_service.py` — 40 existing tests ran
as no-regression suite, all green.

Total: 48 passed (8 new + 40 existing).

## Final CI/CD Gates

3 Tier-1 required gates (all green on CI): `unit-and-integration-tests`,
`contract-validate`, `ruff-lint`. Nightly Tier-3 gates
(`nightly-real-infra`, `multi-worker-concurrency`) apply automatically on merge.

## Production Reality Findings

- **Test count drift**: classification spec said "5 new tests"; implementation
  delivered 8 nodes (test-plan AC mapping already listed 8 — plan and implementation
  were consistent, classification wording was optimistic). Non-blocking; no gap
  in coverage. Reconciled in Lessons Promoted.
- **importlib.reload() pattern**: `test_each_service_registers_exactly_one_job_type`
  requires `importlib.reload()` to re-execute module-level `register_job_type()`
  calls after `_REGISTRY` is cleared between tests. Standard pattern for
  module-level side-effect testing; no prod risk.
- **Private worker function references**: `trace_lineage_job_service.py` and
  `msd_seed/lineage_job_service.py` register private `_execute_xxx_job` functions.
  These remain callable from the dispatcher; no encapsulation violation.

## Lessons Promoted to Standards

1. **CLAUDE.md test-discipline entry extended** — folded `importlib.reload()` pattern for module-level side-effects into the existing "Module-level constants" line. Rule: when a module-level side-effect (e.g. `register_job_type()`) must be re-executed between tests, use `importlib.reload()` after clearing the registry dict; `monkeypatch.setattr(_REGISTRY, …)` alone does not re-run the call.
   Evidence: `agent-log/backend-engineer.yml` Known Risks + `tests/test_job_registry.py::TestJobServiceRegistrations::test_each_service_registers_exactly_one_job_type`.

## Follow-up Work

- Phase 3-A: Downtime Analysis 遷移至 RQ (next in migration plan)
- Phase 3-B: Hold History 遷移至 RQ
- `enqueue_job_dynamic()` is unused by any route as of this change; Phase 3
  wires the first real consumer.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance.
