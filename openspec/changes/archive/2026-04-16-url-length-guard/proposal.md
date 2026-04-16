## Why

Users selecting multiple items (lotids, workorders, packages, etc.) in filter panels causes URL query strings to exceed Gunicorn's `limit_request_line` (4094 bytes), resulting in `400 Bad Request — Request Line is too large (8192 > 4094)`. This affects page navigation (browser back, `<a href>` links), `replaceRuntimeHistory` (page refresh), and CSV export GET URLs. A previous fix (commit 64d8bc1) only addressed API endpoint POST migration for hold-overview/reject-history, but left all page-level URL serialization untouched — the same error surfaces on browser back, manual refresh, and export download.

## What Changes

- Introduce a shared URL length guard in `replaceRuntimeHistory` that automatically spills oversized query params to `sessionStorage`, keeping the URL under a safe threshold (~2000 chars). Page load restores state transparently.
- Fix the wip-detail `<a :href="backUrl">` back link to use SPA navigation (`navigateToRuntimeRoute`) instead of full-page GET.
- Add cross-page navigation state transfer via `sessionStorage` for the wip-overview ↔ wip-detail drilldown/back flow, so only `workcenter` + `status` appear in the URL.
- Convert CSV export functions that build GET URLs with unbounded array params to POST-based blob downloads (reject-history, resource-history, production-history).
- All existing URL-serializing pages benefit from the shared guard without per-page rewrites for `updateUrlState`/`syncUrlState`.

## Capabilities

### New Capabilities
- `url-length-guard`: Shared infrastructure that prevents URL query strings from exceeding server limits. Covers `replaceRuntimeHistory` automatic spill-to-sessionStorage, cross-page navigation state transfer, and POST-based export download utility.

### Modified Capabilities
- `wip-detail-page`: Back link changes from `<a :href>` to SPA navigation; filter state received via sessionStorage instead of URL params.
- `wip-overview-page`: `navigateToDetail` stores filters in sessionStorage; URL kept minimal.
- `reject-history-page`: `exportCsv` migrated from GET query string to POST blob download.
- `resource-history-page`: `exportCsv` migrated from GET query string to POST blob download.

## Impact

- **Frontend core**: `shell-navigation.js` gains length-guarded `replaceRuntimeHistory`; new `wip-navigation-state.js` utility.
- **Frontend pages affected by guard** (no code change needed — automatic): hold-overview, yield-alert-center, job-query, query-tool, hold-history.
- **Frontend pages with explicit changes**: wip-overview, wip-detail, reject-history, resource-history, production-history.
- **Backend**: New POST export endpoints for reject-history and resource-history (existing GET endpoints remain for short URLs / backward compat).
- **E2E tests**: New Playwright specs covering multi-select → navigate → back → refresh round-trip for wip-overview↔wip-detail and hold-overview, plus export download with large filter sets.
- **No breaking changes**: All existing bookmarked short URLs continue to work. sessionStorage is a transparent fallback only triggered when URL would exceed the threshold.
