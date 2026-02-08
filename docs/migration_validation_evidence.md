# Migration Validation Evidence

Date: 2026-02-07

## Build

Command:
- `npm --prefix frontend run build`

Result:
- PASS
- Generated page bundles:
  - `portal.js`
  - `resource-status.js`
  - `resource-history.js`
  - `job-query.js`
  - `excel-query.js`
  - `tables.js`

## Root Startup Smoke

Command:
- `PYTHONPATH=src python -c \"from mes_dashboard.app import create_app; app=create_app('testing'); print('routes', len(list(app.url_map.iter_rules())))\"`

Result:
- PASS
- `routes 71`
- Redis/Oracle warnings observed in this local environment; app factory and route registration still completed.

## Focused Test Gate (root project)

Command:
- `python -m pytest -q tests/test_app_factory.py tests/test_template_integration.py tests/test_cache.py tests/test_health_routes.py tests/test_field_contracts.py tests/test_frontend_compute_parity.py tests/test_job_query_service.py tests/test_resource_history_service.py`

Result:
- PASS
- `107 passed`

## Extended Regression Spot-check

Command:
- `python -m pytest -q tests/test_job_query_routes.py tests/test_resource_history_routes.py tests/test_cache_integration.py`

Result:
- PARTIAL
- `45 passed, 2 failed`
- Failed tests:
  - `tests/test_cache_integration.py::TestWipApiWithCache::test_wip_matrix_uses_cache`
  - `tests/test_cache_integration.py::TestWipApiWithCache::test_packages_uses_cache`

Failure profile:
- cache-fallback path hit Oracle in local environment and returned ORA connectivity/thick-mode errors.
- categorized as environment-dependent (see `docs/environment_gaps_and_mitigation.md`).

## Health/Telemetry Coverage

Validated by tests:
- `/health` includes `route_cache` telemetry and degraded warnings
- `/health/deep` includes route-cache telemetry block
- cache telemetry includes L1/L2 mode, hit/miss counters, degraded state
