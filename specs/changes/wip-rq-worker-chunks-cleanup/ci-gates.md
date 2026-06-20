# CI/CD Gate Review — wip-rq-worker-chunks-cleanup

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local / PR | `ruff check .` | — |
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| unit-mock-integration | 1 | yes | PR / push | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| response-shape-validate | 1 | yes | PR / push | `cdd-kit validate --contracts` | — |
| nightly-integration (wip-worker) | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/test_wip_worker_integration.py --run-integration-real -m integration_real -x` | test report |
| stress-load (wip-worker) | 4 | yes (weekly) | schedule / dispatch | `pytest tests/stress/test_wip_worker_stress.py -m stress` | perf report |
| soak | 4 | yes (weekly) | schedule / dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` | soak report |
| pre-production manual gate | 5 | yes (before activation) | manual dispatch | `stress-soak-report.md` evidence review | stress-soak-report.md |

## New Test Files and Auto-Discovery

The following new test files require **no workflow YAML change** — each falls within an existing gate command's discovery scope:

| new file | auto-discovered by | gate tier |
|---|---|---|
| `tests/test_wip_worker_semaphore.py` | `unit-mock-integration` root `tests/` scan | 1 |
| `tests/test_job_registry.py` (count bump) | `unit-mock-integration` root `tests/` scan | 1 |
| `tests/test_query_cost_policy.py` (`_APPROVED_CALLERS` + spool-namespace param) | `unit-mock-integration` root `tests/` scan | 1 |
| `tests/integration/test_wip_worker_integration.py` | `nightly-integration` gate (`tests/integration/`) | 3 |
| `tests/stress/test_wip_worker_stress.py` | `stress-load` gate (`tests/stress/ -m stress`) | 4 |

## Tier-1 Unit Assertions (auto-discovered by `unit-mock-integration`)

These assertions are required by the acceptance criteria and must be covered in `tests/test_wip_worker_semaphore.py` and updated files:

- AC-1: `enqueue_job_dynamic("wip-detail")` returns a valid job id (not `(None, "Unknown job type")`); `"wip-detail"` present in `job_registry` — test with `importlib.reload()` after clearing registry dict to re-run `register_job_type()` side-effects.
- AC-4: No Oracle connection acquired at request time; `acquire_heavy_query_slot` invoked only inside worker (monkeypatch `is_async_available=True` + mock enqueue — CI has no Redis).
- AC-5: Redis-down / worker-unavailable fail-open to sync path, never 503; COUNT pre-check error fails open.
- AC-6: `merge_chunks` absence verified via `ast.parse()` walk of `batch_query_engine.py`; `grep merge_chunks` returns no hits under `src/` or `tests/`.
- AC-8: Slot acquire/release wires once around Oracle phase; release guarded on success and exception (no double-release).
- Env-var defaults pinned (monkeypatch.setattr, not setenv — module-level constants frozen at import): `WIP_WORKER_QUEUE`, timeout/ttl tuning vars as specified in env-contract.md.
- `tests/test_job_registry.py` registered-job-type count bumped by 1 (one new `"wip-detail"` entry).
- `wip_dataset` namespace in `spool_routes._ALLOWED_NAMESPACES` asserted in parametrized spool-route test (same PR requirement per CLAUDE.md).

## Workflow Changes Applied

No new workflow YAML file is required. New test files are auto-discovered by existing `unit-and-integration-tests`, `nightly-integration-real`, and `stress-tests` jobs in `backend-tests.yml` and `stress-tests.yml`.

The new `deploy/mes-dashboard-wip-worker.service` systemd unit is deploy-config only — it does not affect any CI workflow.

The `ci-gate-contract.md` compatibility note for this change is appended at schema-version 1.3.33 (see below).

## Pre-Production Manual Gate — `stress-soak-report.md`

`stress-soak-report.md` is required evidence **before activating the worker** (adding the `app.py` import line and deploying `mes-dashboard-wip-worker.service`). It must demonstrate:

1. `peak_concurrent ≤ HEAVY_QUERY_MAX_CONCURRENT` for the `"wip-detail"` worker, sampled via `get_active_slot_count()` during `test_wip_worker_stress.py` burst run.
2. Zero slot leak after all jobs reach terminal state (post-completion semaphore reports full availability).
3. DBA Oracle session headroom confirmation: WIP detail worker acquires **one** Oracle connection per slot (not two — the 2-conn resource-worker pattern does not apply here). Confirm the new quota fits within the existing session budget documented in ADR 0011.
4. No deadlock across concurrent `"wip-detail"` jobs under the stress burst.

Until this report is authored and reviewed, the `app.py` import line for `wip_query_job_service` must remain absent.

## Promotion Policy

**Deploy-inert (default):** the `wip_query_job_service` module is NOT imported in `app.py` on initial merge. `enqueue_job_dynamic("wip-detail")` returns `(None, "Unknown job type")` → route fail-opens to sync. All Tier-1 gates pass in this state.

**Activate (promotion sequence):**
1. Obtain sign-off on `stress-soak-report.md` (Pre-Production Gate 5 evidence).
2. Add `import src.mes_dashboard.services.wip_query_job_service  # noqa: F401` to `app.py` alongside sibling workers.
3. Deploy `deploy/mes-dashboard-wip-worker.service`; verify `wip-detail-query` queue appears in Admin Dashboard worker status.
4. Verify `rq_monitor_service._QUEUE_NAMES` includes `os.getenv("WIP_WORKER_QUEUE", "wip-detail-query")`.
5. Confirm `wip_dataset` in `spool_routes._ALLOWED_NAMESPACES` is live.

## Rollback Policy

**Fast rollback (no restart required equivalent):** Remove the `app.py` import line for `wip_query_job_service`; reload gunicorn. The job type vanishes from the registry → `enqueue_job_dynamic("wip-detail")` returns `(None, "Unknown job type")` → route fail-opens to sync path. No data migration; `wip_dataset` spools are TTL-bounded transient parquet — no cleanup required.

**Hard rollback:** Stop and disable `mes-dashboard-wip-worker.service`. In-flight jobs time out at `WIP_JOB_TIMEOUT_SECONDS`; frontend receives HTTP 410 (`CACHE_EXPIRED`) and retries on next query (sync fallback via `is_async_available()` returning False). The `wip_dataset` namespace entry and worker module may remain dormant with no operational impact.

**Part C rollback:** Not needed — `merge_chunks` was zero-caller dead code; git history preserves it.

## Merge Eligibility

**Mergeable** when all Tier-1 gates pass (lint, contract-validate, unit-mock-integration, response-shape-validate). The worker ships inert; `stress-soak-report.md` is required only before production activation, not before merge. Tier-3/4 informational results do not block merge.
