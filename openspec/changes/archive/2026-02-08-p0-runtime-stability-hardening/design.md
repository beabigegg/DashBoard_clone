## Context

The current architecture already supports single-port Gunicorn runtime, circuit-breaker-aware degraded responses, and watchdog-assisted recovery. However, critical security and lifecycle controls are uneven: production startup can still fallback to a weak secret key, CSRF is not enforced globally, and background resources are not fully registered in a single shutdown lifecycle. These gaps are operationally risky when pool pressure or restart churn occurs.

## Goals / Non-Goals

**Goals:**
- Make production startup fail fast when required security secrets are missing.
- Enforce CSRF validation for all state-changing endpoints without breaking existing frontend flow.
- Make worker/app shutdown deterministic by stopping all background workers and shared clients.
- Keep degraded responses for pool exhaustion and circuit-open states stable and retry-aware.
- Isolate health probe connectivity from main request pool contention.

**Non-Goals:**
- Replacing LDAP provider or redesigning the full authentication architecture.
- Full CSP rollout across all templates in this change.
- Changing URL structure, page IA, or single-port deployment topology.

## Decisions

1. **Production secret-key guard at startup**
   - Decision: enforce `SECRET_KEY` presence/strength in non-development modes and abort startup when invalid.
   - Rationale: prevents silent insecure deployment.

2. **Unified CSRF contract across form + JSON flows**
   - Decision: issue CSRF token from server session, validate hidden form field for HTML forms and `X-CSRF-Token` for JSON POST/PUT/PATCH/DELETE.
   - Rationale: maintains current frontend behavior while covering non-form APIs.

3. **Centralized shutdown registry**
   - Decision: register explicit shutdown hooks that call cache updater stop, realtime sync stop, Redis close, and DB dispose in bounded order.
   - Rationale: avoids thread/client leaks during worker recycle and controlled reload.

4. **Health probe pool isolation**
   - Decision: use a dedicated lightweight DB health engine/pool for `/health` checks.
   - Rationale: prevents health endpoint from being blocked by request-pool exhaustion, improving observability fidelity.

5. **Template-safe JS serialization**
   - Decision: replace HTML-escaped interpolation in JS string contexts with `tojson` serialization.
   - Rationale: avoids context-mismatch injection edge cases.

## Risks / Trade-offs

- **[Risk] CSRF rollout may break undocumented clients** → **Mitigation:** provide opt-in transition flag and explicit error messaging during rollout.
- **[Risk] Strict startup secret validation can block misconfigured environments** → **Mitigation:** provide clear startup diagnostics and `.env.example` updates.
- **[Risk] Additional shutdown hooks can prolong worker exit** → **Mitigation:** bounded timeouts and idempotent stop handlers.
- **[Risk] Dedicated health pool introduces extra DB connections** → **Mitigation:** fixed minimal size and short timeout.
