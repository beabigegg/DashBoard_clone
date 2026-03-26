## 1. Hold Detail Vite Modularization

- [x] 1.1 Add `hold-detail` entry to Vite build configuration.
- [x] 1.2 Create `frontend/src/hold-detail/main.js` by migrating existing page script while preserving behavior.
- [x] 1.3 Update `hold_detail.html` to prefer `frontend_asset('hold-detail.js')` with inline fallback retention.

## 2. Security and Parity Hardening

- [x] 2.1 Sanitize dynamic HTML/attribute interpolation in hold-detail module rendering paths.
- [x] 2.2 Apply equivalent sanitization in inline fallback logic to avoid security bypass.
- [x] 2.3 Preserve legacy global handler compatibility for existing inline event hooks.

## 3. Validation

- [x] 3.1 Build frontend and verify `hold-detail.js` output in static dist.
- [x] 3.2 Extend template integration tests for hold-detail module/fallback rendering.
- [x] 3.3 Run focused pytest suite for template/frontend regressions.
