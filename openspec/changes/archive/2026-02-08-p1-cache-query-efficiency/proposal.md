## Why

Current reporting workloads still spend unnecessary CPU and memory on repeated full-data merges, broad DataFrame copies, and duplicated cache representations. We need a focused efficiency phase that preserves the intentional full-table cache strategy for `resource` and `wip`, while reducing cost for other query paths and increasing frontend compute reuse.

## What Changes

- Introduce indexed/incremental cache synchronization for heavy report datasets that do not require full-table snapshots.
- Keep `resource` and `wip` as full-table cache by design, but reduce redundant in-process representations and copy overhead.
- Move additional derived calculations (chart/table/KPI/filter shaping) to reusable browser modules in Vite frontend.
- Add cache/query efficiency telemetry and repeatable benchmark gates to validate gains.

## Capabilities

### New Capabilities
- `cache-indexed-query-acceleration`: Define incremental refresh and indexed query contracts for non-full-snapshot datasets.

### Modified Capabilities
- `cache-observability-hardening`: Add memory-efficiency and cache-structure telemetry expectations.
- `frontend-compute-shift`: Expand browser-side reusable compute coverage for report interactions.

## Impact

- Affected code:
  - `src/mes_dashboard/core/cache.py`
  - `src/mes_dashboard/services/resource_cache.py`
  - `src/mes_dashboard/services/realtime_equipment_cache.py`
  - `src/mes_dashboard/services/wip_service.py`
  - `src/mes_dashboard/routes/health_routes.py`
  - `frontend/src/core/`
  - `frontend/src/**/main.js`
  - `tests/`
- APIs:
  - read-heavy `/api/wip/*` and `/api/resource/*` endpoints (response contract unchanged)
- Operational behavior:
  - Preserve current `resource` and `wip` full-table caching strategy.
  - Reduce server-side compute load through selective frontend compute offload.
