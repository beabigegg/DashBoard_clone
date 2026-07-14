# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Backend / Oracle: `src/mes_dashboard/sql/production_achievement.sql`, `workers/production_achievement_worker.py`
- Backend / services + cache: `services/production_achievement_service.py`, 3 new services (`_package_lf_service.py`, `_workcenter_merge_service.py`, `_daily_plan_service.py`), `services/filter_cache.py`, new `services/production_achievement_daily_cache.py`, `services/async_query_job_service.py` (progress-trap reference)
- Backend / core + routes: `core/spool_warmup_scheduler.py`, `core/base_chunked_duckdb_job.py`, `core/permissions.py`, `core/mysql_client.py`, `routes/production_achievement_routes.py`
- MySQL DDL: `scripts/sql/production_achievement_tables.sql`
- Frontend / report app: `frontend/src/production-achievement/` (App.vue, composables, components incl. deleted `AchievementChart.vue` + new `PlanAchievementStackedChart.vue`)
- Frontend / new settings app: `frontend/src/production-achievement-settings/` (to be created)
- Frontend / registration: `portal-shell/navigationState.js` (`STANDALONE_DRILLDOWN_ROUTES`), `portal-shell/routeContracts.js`, `portal-shell/nativeModuleRegistry.js`, `vite.config.ts`, `admin-dashboard/tabs/PermissionsTab.vue`
- Contracts + docs: `contracts/{api,css,data,business}/`, `contracts/openapi.json`, `docs/adr/0016-*.md`
- Registries: `data/page_status.json`, `docs/migration/full-modernization-architecture-blueprint/{route_scope_matrix.json,asset_readiness_manifest.json}`
- Tests: backend (`tests/`, `tests/contract/`, `tests/integration/`, `tests/stress/`, `tests/acceptance/`), frontend (`frontend/tests/`)

## Allowed Paths
- specs/changes/production-achievement-overhaul/
- specs/context/project-map.md
- specs/context/contracts-index.md
- specs/archive/2026/production-achievement-async-spool/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- scripts/sql/
- frontend/src/production-achievement/
- frontend/src/production-achievement-settings/
- frontend/src/portal-shell/
- frontend/src/admin-dashboard/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/resource-history/
- frontend/src/styles/
- frontend/tests/
- frontend/scripts/
- frontend/vite.config.ts
- frontend/tailwind.config.js
- frontend/tsconfig.json
- frontend/playwright.config.js
- frontend/vitest.config.js
- frontend/package.json
- contracts/
- docs/adr/
- docs/architecture/
- docs/migration/full-modernization-architecture-blueprint/
- data/
- tests/
- tests/contract/
- tests/integration/
- tests/stress/
- tests/acceptance/
- tests/property/
- .github/workflows/
- ci/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- docs/adr/0016-production-achievement-async-spool-seam-reduction.md (extension addendum)

## Required Tests
- tests/ (test_production_achievement_service.py, test_production_achievement_target_service.py, new 3-service tests, new test_production_achievement_daily_cache.py, test_base_chunked_duckdb_job.py, test_async_query_job_service.py, test_app_startup.py)
- tests/contract/ (test_api_contract.py, new test_production_achievement_contract.py, test_env_production_achievement_unified_flag.py, samples/, test_schema_coverage.py, test_openapi_schema_resolution.py)
- tests/integration/ (test_production_achievement_mysql_roundtrip.py, test_production_achievement_resilience.py, test_production_achievement_rq_async.py, test_production_achievement_filter_cache_reuse.py)
- tests/stress/ (test_production_achievement_stress.py, test_chunk_boundary.py)
- tests/acceptance/ (acceptance-driver test for this change)
- frontend/tests/ (playwright/production-achievement*.spec.*, playwright/production-achievement-monkey.spec.ts, new settings-page spec, components/ + composable unit tests)

## Agent Work Packets

### change-classifier
- specs/changes/production-achievement-overhaul/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/production-achievement-overhaul/
- specs/context/project-map.md
- specs/context/contracts-index.md
- specs/archive/2026/production-achievement-async-spool/
- contracts/
- docs/adr/
- docs/architecture/
- docs/migration/full-modernization-architecture-blueprint/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/core/
- frontend/src/production-achievement/
- frontend/src/portal-shell/
- scripts/sql/

### implementation-planner
- specs/changes/production-achievement-overhaul/
- contracts/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- scripts/sql/
- frontend/src/production-achievement/
- frontend/src/portal-shell/
- frontend/src/admin-dashboard/
- data/
- docs/adr/
- docs/migration/full-modernization-architecture-blueprint/

### backend-engineer
- specs/changes/production-achievement-overhaul/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- scripts/sql/
- contracts/api/
- contracts/business/
- contracts/data/
- docs/architecture/
- docs/adr/
- tests/
- tests/contract/
- tests/integration/
- tests/stress/
- tests/acceptance/

### frontend-engineer
- specs/changes/production-achievement-overhaul/
- frontend/src/production-achievement/
- frontend/src/production-achievement-settings/
- frontend/src/portal-shell/
- frontend/src/admin-dashboard/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/resource-history/
- frontend/src/styles/
- frontend/tests/
- frontend/vite.config.ts
- frontend/tailwind.config.js
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/playwright.config.js
- frontend/package.json
- data/
- docs/migration/full-modernization-architecture-blueprint/
- docs/architecture/
- contracts/api/
- contracts/css/
- contracts/data/

### test-strategist
- specs/changes/production-achievement-overhaul/
- tests/
- tests/contract/
- tests/integration/
- tests/stress/
- tests/acceptance/
- tests/property/
- frontend/tests/
- contracts/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/core/
- frontend/src/production-achievement/
- frontend/src/production-achievement-settings/

### contract-reviewer
- specs/changes/production-achievement-overhaul/
- contracts/
- docs/adr/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- frontend/src/core/
- frontend/src/production-achievement/

### ui-ux-reviewer
- specs/changes/production-achievement-overhaul/
- frontend/src/production-achievement/
- frontend/src/production-achievement-settings/
- frontend/src/portal-shell/
- frontend/src/admin-dashboard/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- contracts/css/

### visual-reviewer
- specs/changes/production-achievement-overhaul/
- frontend/src/production-achievement/
- frontend/src/production-achievement-settings/
- frontend/src/resource-history/
- frontend/src/styles/
- frontend/tests/
- contracts/css/

### e2e-resilience-engineer
- specs/changes/production-achievement-overhaul/
- frontend/tests/
- tests/integration/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- src/mes_dashboard/workers/
- frontend/src/production-achievement/

### stress-soak-engineer
- specs/changes/production-achievement-overhaul/
- tests/stress/
- src/mes_dashboard/core/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- contracts/ci/

### qa-reviewer
- specs/changes/production-achievement-overhaul/
- contracts/
- tests/
- frontend/tests/
- docs/architecture/
- scripts/sql/

### ci-cd-gatekeeper
- specs/changes/production-achievement-overhaul/
- contracts/
- .github/workflows/
- ci/
- frontend/scripts/
- tests/contract/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - specs/archive/2026/production-achievement-async-spool/
  reason: Approved plan Phase 0 directs mirroring this archived artifact set as the template for design.md / implementation-plan.md / test-plan.md; specs/archive is outside the default project-map paths so it must be explicitly authorized for spec-architect / implementation-planner.
  status: approved

## Approved Expansions
- CER-001: specs/archive/2026/production-achievement-async-spool/ — approved for spec-architect and implementation-planner read access (see Allowed Paths above).
