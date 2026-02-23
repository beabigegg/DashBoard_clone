## 1. Config and Core Safety Baseline

- [x] 1.1 Add centralized hardening config keys (`TRUST_PROXY_HEADERS`, trusted proxy source config, JSON/body/input limits) with production-safe defaults.
- [x] 1.2 Change page registry fallback behavior so `api_public` defaults to false when config is missing/invalid.
- [x] 1.3 Implement secret redaction utility for connection-string logging and apply it to Redis URL logs.
- [x] 1.4 Enforce startup validation for required production security variables (including `SECRET_KEY`) with actionable diagnostics.
- [x] 1.5 Update environment documentation (`.env.example`/README/deploy docs) to match new hardening settings.

## 2. Released API Input Validation and Budget Guards

- [x] 2.1 Introduce a shared JSON request parsing/validation helper and adopt it in released JSON-only endpoints (`query-tool`, `job-query`, `resource` related routes).
- [x] 2.2 Ensure invalid/malformed/non-JSON payloads return deterministic 400/415 and do not fall through to generic 500 handlers.
- [x] 2.3 Add configurable hard caps for query-tool batch inputs (including `container_ids`) and reject overflow requests before service execution.
- [x] 2.4 Add configurable `limit` bounds for `/api/resource/detail` and normalize/reject invalid pagination limits consistently.
- [x] 2.5 Fix released route numeric query parsing edge cases to avoid `TypeError`/500 regressions.

## 3. Rate-Limit Trust Boundary Hardening

- [x] 3.1 Refactor rate-limit client identity resolution to ignore `X-Forwarded-For` by default and use `remote_addr` in direct-exposure deployments.
- [x] 3.2 Add trusted-proxy mode behavior so forwarded IP is used only when explicit trust configuration is enabled.
- [x] 3.3 Add tests for spoofed header attempts, direct mode behavior, and trusted-proxy behavior.

## 4. Frontend Injection-Surface Reduction

- [x] 4.1 Refactor `job-query` action rendering to remove raw inline `onclick` interpolation and use safe event binding/data attributes.
- [x] 4.2 Review and tighten applicable CSP/script-safety configuration for released routes without breaking current module/fallback loading.
- [x] 4.3 Add frontend/template tests to lock down safe rendering behavior for quoted/special-character data.

## 5. Regression Gates and Verification

- [x] 5.1 Add negative-path tests for invalid JSON, oversized batch input, bounded `limit`, and no-service-call-on-reject behavior.
- [x] 5.2 Add config hardening tests for `api_public` fail-safe fallback, production env validation, and Redis URL redaction.
- [x] 5.3 Run released-route focused pytest suite and update/repair affected contract tests to reflect explicit new 4xx/429 boundaries only.
- [x] 5.4 Ensure CI requires the new hardening test set to pass before merge.
