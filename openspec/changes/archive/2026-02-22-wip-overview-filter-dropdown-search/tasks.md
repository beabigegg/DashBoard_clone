## 1. OpenSpec alignment

- [x] 1.1 Confirm modified capability scope and spec deltas for `wip-overview-page`

## 2. Backend: cache-backed filter options + new filter fields

- [x] 2.1 Add WIP service support for `FIRSTNAME` / `WAFERDESC` in cache-derived indexes and snapshot filter path
- [x] 2.2 Add cache-backed `get_wip_filter_options` service API returning workorders/lotids/packages/types/firstnames/waferdescs
- [x] 2.3 Add `GET /api/wip/meta/filter-options` route
- [x] 2.4 Extend overview query routes (`summary`, `matrix`, `hold`) to parse and pass `firstname` and `waferdesc`
- [x] 2.5 Keep backward compatibility for existing params and behavior

## 3. Frontend: WIP overview filter UX replacement

- [x] 3.1 Replace `wip-overview` filter inputs with searchable dropdowns (reuse `resource-shared/components/MultiSelect.vue`)
- [x] 3.2 Add two new filters in UI: `Wafer LOT` (`firstname`) and `Wafer Type` (`waferdesc`)
- [x] 3.3 Load filter options from `/api/wip/meta/filter-options` on initialization and bind to dropdown options
- [x] 3.4 Ensure apply/clear/chip-remove and URL sync all work with old + new filters

## 4. Tests and verification

- [x] 4.1 Update route tests for new endpoint and new query parameters
- [x] 4.2 Update service tests for filter options and new index fields
- [x] 4.3 Update frontend derive tests for URL/query param mapping
- [x] 4.4 Run targeted test commands and fix regressions
