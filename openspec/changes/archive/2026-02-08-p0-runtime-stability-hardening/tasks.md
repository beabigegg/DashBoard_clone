## 1. Runtime Stability Hardening

- [x] 1.1 Add startup validation for `SECRET_KEY` and environment-aware secure defaults.
- [x] 1.2 Register centralized shutdown hooks to stop cache updater, realtime sync worker, Redis client, and DB engine.
- [x] 1.3 Isolate database health probing from request pool and keep degraded signal contract stable.
- [x] 1.4 Normalize pool-exhausted response metadata and retry headers across API error paths.

## 2. Security Baseline Enforcement

- [x] 2.1 Add CSRF token issuance/validation for form posts and JSON mutation endpoints.
- [x] 2.2 Update login flow to rotate session identity on successful authentication.
- [x] 2.3 Replace JS-context template interpolation in `hold_detail.html` with JSON-safe serialization.

## 3. Verification and Documentation

- [x] 3.1 Add tests for startup secret guard, CSRF rejection, and session-rotation behavior.
- [x] 3.2 Add lifecycle tests/validation for shutdown cleanup and health endpoint behavior under pool saturation.
- [x] 3.3 Update README/README.mdj runtime hardening sections and operator rollout notes.
