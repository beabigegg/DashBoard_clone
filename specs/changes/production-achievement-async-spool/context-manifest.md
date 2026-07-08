# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Backend shared async machinery — `BaseChunkedDuckDBJob`, `oracle_arrow_reader`, global concurrency semaphore, `query_spool_store`, `async_query_job_service`, `spool_routes`, `job_routes`, `job_registry`, `query_cost_policy`
- production-achievement backend — service, target-service, permission-service, routes, `sql/production_achievement.sql`
- Reference domain (read-only) — `resource_history` worker/cache/routes/sql
- Frontend production-achievement app + shared DuckDB core — `duckdb-client`, `duckdb-activation-policy`, `useAsyncJobPolling`, `duckdb-worker`, reference `useResourceHistoryDuckDB`
- Contracts — api, data, env (+ `env.schema.json`, `.env.example.template`), business, ci, openapi mirror
- Tests — query-cost policy, job registry, base job, new unified-job + rq-async integration, dual-tier parity, e2e/resilience/stress/soak, frontend duckdb/composable
- Deploy / CI — `deploy/*.service` systemd units, `.github/workflows/`, worker env parity (`gunicorn.conf.py`, `config/settings.py`)

## Allowed Paths
- specs/changes/production-achievement-async-spool/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/services/production_achievement_service.py
- src/mes_dashboard/services/production_achievement_target_service.py
- src/mes_dashboard/services/production_achievement_permission_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/routes/spool_routes.py
- src/mes_dashboard/routes/job_routes.py
- src/mes_dashboard/routes/production_achievement_routes.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/workers/
- src/mes_dashboard/sql/production_achievement.sql
- src/mes_dashboard/sql/resource_history/
- src/mes_dashboard/config/settings.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/rq_worker_preload.py
- scripts/sql/production_achievement_tables.sql
- scripts/start_server.sh
- gunicorn.conf.py
- frontend/src/production-achievement/
- frontend/src/resource-history/
- frontend/src/core/duckdb-client.ts
- frontend/src/core/duckdb-activation-policy.ts
- frontend/src/core/api.ts
- frontend/src/core/unwrap-api-result.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/shared-composables/useAsyncJobPolling.ts
- frontend/src/workers/duckdb-worker.js
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- .env.example
- tests/test_query_cost_policy.py
- tests/test_job_registry.py
- tests/test_base_chunked_duckdb_job.py
- tests/test_production_achievement_unified_job.py
- tests/test_production_achievement_routes.py
- tests/test_production_achievement_service.py
- tests/test_spool_routes.py
- tests/test_env_contract.py
- tests/test_frontend_production_achievement_parity.py
- tests/integration/
- tests/stress/
- tests/contract/
- tests/e2e/
- tests/fixtures/frontend_compute_parity.json
- frontend/tests/playwright/
- frontend/tests/validation/
- frontend/tests/legacy/resource-history.test.js
- deploy/
- .github/workflows/
- ci/
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- docs/architecture/test-discipline.md
- docs/architecture/ci-workflow.md
- docs/architecture/base-job-semaphore-wiring-stress-soak-report.md
- docs/adr/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json (+ contracts/openapi.json mirror)
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/test_query_cost_policy.py (`_APPROVED_CALLERS`)
- tests/test_job_registry.py
- tests/test_base_chunked_duckdb_job.py
- tests/integration/test_production_achievement_rq_async.py (new)
- tests/test_production_achievement_unified_job.py (new; dual-tier mock chunk-seam unit)
- tests/integration/test_resource_history_rq_async.py (reference)
- tests/integration/test_production_achievement_filter_cache_reuse.py
- tests/integration/test_production_achievement_mysql_roundtrip.py
- tests/integration/test_soak_workload.py
- tests/stress/ (async job stress, base-job semaphore stress, resource-history stress — reference)
- tests/contract/ (env default/enum, schema coverage, openapi resolution)
- tests/e2e/ (resource-history browser e2e — reference)
- tests/fixtures/frontend_compute_parity.json
- frontend/tests/playwright/production-achievement-async.spec.ts (new; mirror resource-history-async.spec.ts)
- frontend/tests/validation/

## Agent Work Packets

### spec-architect
- specs/changes/production-achievement-async-spool/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/production_achievement_service.py
- frontend/src/core/duckdb-activation-policy.ts
- frontend/src/resource-history/
- docs/adr/
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md

### implementation-planner
- specs/changes/production-achievement-async-spool/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/services/production_achievement_service.py
- src/mes_dashboard/routes/production_achievement_routes.py
- src/mes_dashboard/workers/
- frontend/src/production-achievement/

### backend-engineer
- specs/changes/production-achievement-async-spool/
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/services/production_achievement_service.py
- src/mes_dashboard/services/production_achievement_target_service.py
- src/mes_dashboard/services/production_achievement_permission_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/routes/spool_routes.py
- src/mes_dashboard/routes/job_routes.py
- src/mes_dashboard/routes/production_achievement_routes.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/workers/
- src/mes_dashboard/sql/production_achievement.sql
- src/mes_dashboard/sql/resource_history/
- src/mes_dashboard/config/settings.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/rq_worker_preload.py
- scripts/sql/production_achievement_tables.sql
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/business/business-rules.md

### frontend-engineer
- specs/changes/production-achievement-async-spool/
- frontend/src/production-achievement/
- frontend/src/resource-history/
- frontend/src/core/duckdb-client.ts
- frontend/src/core/duckdb-activation-policy.ts
- frontend/src/core/api.ts
- frontend/src/core/unwrap-api-result.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/shared-composables/useAsyncJobPolling.ts
- frontend/src/workers/duckdb-worker.js
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### contract-reviewer
- specs/changes/production-achievement-async-spool/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### test-strategist
- specs/changes/production-achievement-async-spool/
- tests/test_query_cost_policy.py
- tests/test_job_registry.py
- tests/test_base_chunked_duckdb_job.py
- tests/integration/
- tests/stress/
- tests/contract/
- tests/e2e/
- tests/fixtures/frontend_compute_parity.json
- frontend/tests/playwright/
- frontend/tests/validation/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- docs/architecture/test-discipline.md

### ci-cd-gatekeeper
- specs/changes/production-achievement-async-spool/
- deploy/
- .github/workflows/
- ci/
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- gunicorn.conf.py
- src/mes_dashboard/rq_worker_preload.py
- docs/architecture/ci-workflow.md

### e2e-resilience-engineer
- specs/changes/production-achievement-async-spool/
- tests/e2e/
- tests/integration/
- frontend/tests/playwright/
- src/mes_dashboard/routes/production_achievement_routes.py
- src/mes_dashboard/routes/spool_routes.py
- src/mes_dashboard/routes/job_routes.py
- frontend/src/production-achievement/

### stress-soak-engineer
- specs/changes/production-achievement-async-spool/
- tests/stress/
- tests/integration/test_soak_workload.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/workers/
- docs/architecture/base-job-semaphore-wiring-stress-soak-report.md

### monkey-test-engineer
- specs/changes/production-achievement-async-spool/
- frontend/tests/playwright/
- frontend/src/production-achievement/

### ui-ux-reviewer
- specs/changes/production-achievement-async-spool/
- frontend/src/production-achievement/
- frontend/src/shared-composables/useAsyncJobPolling.ts

### visual-reviewer
- specs/changes/production-achievement-async-spool/
- frontend/src/production-achievement/
- frontend/tests/playwright/

### qa-reviewer
- specs/changes/production-achievement-async-spool/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- tests/integration/
- tests/e2e/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/resource_dataset_cache.py
    - src/mes_dashboard/core/spool_pipeline.py
  reason: The project-map `services/` listing is truncated after `production_achievement_target_service.py`, so the reference canonical-spool cache module and any production-achievement spool-cache/pipeline module cannot be confirmed by name from the index alone. These paths are asserted from pre-researched pattern facts; both are already listed in Allowed Paths above.
  status: approved
- request-id: CER-002
  requested_paths:
    - tests/test_production_achievement_routes.py
    - tests/test_production_achievement_service.py
    - tests/test_spool_routes.py
    - tests/test_env_contract.py
  reason: The `### backend-engineer` packet below lists zero test paths, and the top-level `## Allowed Paths` covers `tests/contract/`, `tests/integration/`, `tests/stress/`, `tests/e2e/`, `tests/test_query_cost_policy.py`, `tests/test_job_registry.py`, and `tests/test_base_chunked_duckdb_job.py` but omits these 4 root-level test files. implementation-plan.md's File-Level Plan and TDD Sequence (the backend-engineer's authoritative execution packet per the harness prompt) explicitly assign edits to exactly these 4 files (route 202/200/503 branch tests, service golden-test retention, spool-namespace allowlist test, env-default pin test) — all of which test source files (`production_achievement_routes.py`, `production_achievement_service.py`, `spool_routes.py`, env-contract wiring) that ARE in the approved Allowed Paths. Treated as covered by the already-approved implementation-plan.md; proceeding without a blocking wait to keep the TDD sequence for this Tier-1 change moving. Flagged here for reviewer visibility.
  status: approved
- request-id: CER-003
  requested_paths:
    - tests/test_frontend_production_achievement_parity.py
  reason: implementation-plan.md's TDD Sequence "Frontend" step 2 explicitly requires "add tests/test_frontend_production_achievement_parity.py ... mirror tests/test_frontend_hold_history_parity.py" as the dual-tier parity gate for IP-6 (owner frontend-engineer), and the frontend-engineer harness prompt explicitly instructs "mirror tests/test_frontend_hold_history_parity.py ... If writing the python parity test needs paths outside your allowed list, note it in the manifest as a CER and proceed per implementation-plan.md." This file is neither in the top-level `## Allowed Paths` nor the `### frontend-engineer` packet (only `tests/fixtures/frontend_compute_parity.json` is listed there), but it directly validates IP-6 (the frontend-engineer's own deliverable) using the `duckdb` Python package (no frontend source is imported/modified — it is a standalone new test file). Proceeding per the explicit harness-prompt authorization and the CER-002 precedent already established in this same manifest (same pattern: TDD-required test file omitted from an agent's sub-packet despite being explicitly assigned by implementation-plan.md).
  status: approved
  note: >
    Investigated whether "extend tests/test_frontend_duckdb_parity.py +
    tests/fixtures/frontend_compute_parity.json with an achievement_rate
    scalar case" (harness prompt) applies. `frontend_compute_parity.json` is
    a single-purpose fixture consumed only by `tests/test_frontend_compute_parity.py`
    for `buildResourceKpiFromHours` (prd/sby/udt/sdt/egt/nst-hours shaped
    cases) — appending a PA-shaped case would break that consumer's
    `_backend_expected()` (unconditional `case['prd_hours']` etc.) and
    `tests/test_frontend_duckdb_parity.py` does not read that fixture at all
    (its classes use hardcoded CASES lists importing a real frontend pure
    function via Node subprocess). The achievement_rate formula is expressed
    entirely as inline DuckDB SQL inside `computeView()`, not a separately
    importable pure function — extracting one solely to satisfy the Node
    -subprocess pattern would test dead code never exercised by the real
    runtime path (solution-minimalism violation, dual-maintenance risk).
    `tests/test_frontend_production_achievement_parity.py` instead executes
    the literal SQL text via the `duckdb` Python package end-to-end
    (rollup + join + rate), which is a strictly stronger parity signal than a
    Node-subprocess formula reimplementation would be. Skipped the
    `test_frontend_duckdb_parity.py` / `frontend_compute_parity.json` edits
    for this reason; flagged here for qa-reviewer visibility.

## Approved Expansions
- CER-001 (both paths already present in Allowed Paths)
- CER-002 (test files needed for TDD coverage of already-approved source-file edits; authorized by implementation-plan.md's explicit File-Level Plan/TDD Sequence)
- CER-003 (dual-tier parity test file for IP-6, explicitly assigned by implementation-plan.md's TDD Sequence and the frontend-engineer harness prompt)
