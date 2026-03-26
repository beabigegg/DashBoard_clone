## Why

The Vite migration is functionally complete, but production runtime still has high-risk gaps in security baseline and worker lifecycle cleanup. Addressing these now prevents avoidable outages, authentication bypass risk, and unstable degradation behavior under pool pressure.

## What Changes

- Enforce production-safe startup security defaults (no weak SECRET_KEY fallback in non-development environments).
- Add first-class CSRF protection for admin forms and state-changing JSON APIs.
- Harden degradation behavior for pool exhaustion with consistent retry/backoff contract and isolated health probing.
- Ensure background workers and shared clients (cache updater, realtime sync, Redis) are explicitly stopped on worker/app shutdown.
- Fix template-to-JavaScript variable serialization in hold-detail fallback script.

## Capabilities

### New Capabilities
- `security-baseline-hardening`: Define mandatory secret/session/CSRF/XSS-safe baseline for production runtime.

### Modified Capabilities
- `runtime-resilience-recovery`: Strengthen shutdown lifecycle and degraded-response behavior for pool pressure scenarios.

## Impact

- Affected code:
  - `src/mes_dashboard/app.py`
  - `src/mes_dashboard/core/database.py`
  - `src/mes_dashboard/core/cache_updater.py`
  - `src/mes_dashboard/core/redis_client.py`
  - `src/mes_dashboard/routes/health_routes.py`
  - `src/mes_dashboard/routes/auth_routes.py`
  - `src/mes_dashboard/templates/hold_detail.html`
  - `gunicorn.conf.py`
  - `tests/`
- APIs:
  - `/health`
  - `/health/deep`
  - `/admin/login`
  - state-changing `/api/*` endpoints
- Operational behavior:
  - Keep single-port deployment model unchanged.
  - Improve degraded-state stability and startup safety gates.
