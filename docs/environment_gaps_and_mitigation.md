# Environment-dependent Gaps and Mitigation

## Oracle-dependent checks

### Gap
- Service/integration paths that execute Oracle SQL require live DB credentials and network reachability.
- Local CI-like runs may not have Oracle connectivity.
- In this environment, `tests/test_cache_integration.py` has Oracle-dependent fallback failures when cache fixtures are insufficient.

### Mitigation
- Keep unit tests isolated with mocks for SQL entry points.
- Reserve Oracle-connected tests for gated environments.
- Use `testing` config for app factory tests where possible.

## Redis-dependent checks

### Gap
- Redis availability differs across environments.
- Health/caching behavior differs between `L1+L2` and `L1-only degraded` modes.

### Mitigation
- Expose route-cache telemetry in `/health` and `/health/deep`.
- Keep degraded mode visible and non-fatal where DB remains healthy.
- Validate both modes in unit tests (`tests/test_cache.py`, `tests/test_health_routes.py`).

## Frontend build availability

### Gap
- Node/npm may be absent on constrained runtime nodes.

### Mitigation
- Keep inline script fallback in templates when dist assets are missing.
- Build artifacts in deployment pipeline where Node is available.
- Startup script logs fallback mode explicitly on build failure.
