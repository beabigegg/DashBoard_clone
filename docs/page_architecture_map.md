# Page Architecture Map

## Portal Navigation Model

Portal (`/`) uses drawer-based navigation and keeps existing operational flow:

- 報表類
  - `/wip-overview`
  - `/resource`
  - `/resource-history`
- 查詢類
  - `/tables`
  - `/excel-query`
  - `/job-query`
- 開發工具
  - `/admin/pages`
  - `/admin/performance`

## Independent Pages

These pages are independent views (iframe tabs in portal) and can be loaded directly:
- `/wip-overview`
- `/resource`
- `/resource-history`
- `/tables`
- `/excel-query`
- `/job-query`

## Drill-down Pages

These pages are drill-down/detail pages, linked from parent views:
- `/wip-detail` (from WIP flows)
- `/hold-detail` (from hold-related flows)

## Vite Entry Mapping

- `portal` -> `frontend/src/portal/main.js`
- `resource-status` -> `frontend/src/resource-status/main.js`
- `resource-history` -> `frontend/src/resource-history/main.js`
- `job-query` -> `frontend/src/job-query/main.js`
- `excel-query` -> `frontend/src/excel-query/main.js`
- `tables` -> `frontend/src/tables/main.js`

All pages keep inline fallback scripts in templates when module assets are unavailable.
