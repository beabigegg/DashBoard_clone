## 1. Root Migration Baseline

- [x] 1.1 Build root project baseline in `DashBoard_vite` by referencing `DashBoard/` structure while preserving `DashBoard/` as comparison source.
- [x] 1.2 Ensure root-level Python entry/config/scripts can run without depending on nested `DashBoard/` paths.
- [x] 1.3 Update root README and environment setup notes to make root-first workflow explicit.

## 2. Vite + Single-Port Integration

- [x] 2.1 Add root frontend Vite project and configure build output to backend static assets.
- [x] 2.2 Integrate frontend build into deploy/start scripts with fallback behavior when npm build is unavailable.
- [x] 2.3 Verify root app serves Vite-built assets through Flask on the same external port.

## 3. Portal Navigation Refactor

- [x] 3.1 Refactor root portal navigation to drawer groups (reports/queries/dev-tools) while keeping existing route targets.
- [x] 3.2 Keep lazy-load frame behavior and health popup behavior compatible after navigation refactor.

## 4. Cache and Field Contract Updates

- [x] 4.1 Replace default NoOp route cache in root app with layered cache backend (L1 memory + optional Redis).
- [x] 4.2 Align known field-name inconsistencies between UI and export (job query and resource history first batch).

## 5. Validation and Documentation

- [x] 5.1 Run focused root tests for app factory/cache/query modules and record results.
- [x] 5.2 Document residual environment-dependent test gaps (Oracle/Redis dependent cases) and next actions.
