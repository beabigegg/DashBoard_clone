# Root Cutover Inventory

## Scope
- Workspace root: `/Users/egg/Projects/DashBoard_vite`
- Legacy subtree `DashBoard/`: removed on 2026-02-08
- Objective: ensure runtime/test/deploy flows depend only on root architecture.

## 1. Runtime / Test / Deploy Path Audit

### Legacy path references
- Historical mentions may exist in archived OpenSpec artifacts for traceability.
- Active runtime/test/deploy code MUST NOT reference removed legacy subtree paths.

### Result
- Legacy code directory is removed.
- No active runtime code in `src/`, `scripts/`, or `tests/` requires legacy subtree paths.
- Remaining mentions are documentation-only migration history.

## 2. Root-only Execution Hardening

### Updated
- `scripts/start_server.sh`
  - Frontend build readiness now checks all required root dist entries:
    - `portal.js`
    - `resource-status.js`
    - `resource-history.js`
    - `job-query.js`
    - `excel-query.js`
    - `tables.js`

### Verified behavior target
- Startup/build logic remains anchored to root paths:
  - `frontend/`
  - `src/mes_dashboard/static/dist/`
  - `src/`

## 3. Root-only Smoke Checks (single-port)

### Build smoke
- `npm --prefix frontend run build`

### App import smoke
- `PYTHONPATH=src python -c "from mes_dashboard.app import create_app; app=create_app('testing'); print(app.url_map)"`
- Verified route initialization count (`routes 83`) in root-only execution context.

### HTTP smoke (Flask test client)
- Verify page renders and module asset tags resolve/fallback:
  - `/`
  - `/resource`
  - `/resource-history`
  - `/job-query`
  - `/excel-query`
  - `/tables`

### Test smoke
- `python -m pytest -q tests/test_app_factory.py tests/test_template_integration.py tests/test_cache.py`
