## Context

All pages that serialize filter arrays into URL query strings (via `replaceRuntimeHistory` or `navigateToRuntimeRoute`) are vulnerable to Gunicorn's `limit_request_line = 4094`. The problem manifests in three scenarios:

1. **Page refresh** — `replaceRuntimeHistory` writes a long URL to `history.replaceState`; on F5 the browser sends a GET to the server.
2. **Cross-page navigation** — wip-overview's `navigateToDetail` and wip-detail's `<a :href="backUrl">` build URLs with all filter arrays; when not intercepted by the SPA router bridge (or on `<a>` click), the full URL hits the server.
3. **Export download** — reject-history, resource-history, and production-history build GET URLs with array params for CSV export.

10 pages are affected (see proposal for full audit). The previous fix (commit 64d8bc1) only addressed API query endpoints, not page-level URLs.

## Goals / Non-Goals

**Goals:**
- Eliminate all `Request Line is too large` errors across the entire frontend
- Provide a transparent, shared mechanism so every page benefits without per-page rewrites for `updateUrlState`
- Preserve short-URL bookmarkability — only trigger the guard when the URL would exceed the threshold
- Ensure browser back/forward, page refresh, and multi-tab all work correctly
- Add E2E test coverage for the multi-select → navigate → back → refresh round-trip

**Non-Goals:**
- Migrating all API query endpoints from GET to POST (already done in previous work)
- Changing Gunicorn's `limit_request_line` (server config is not ours to change in production)
- Implementing URL compression or hash-based state (over-engineering for this use case)
- Changing how filters are rendered in the UI or how filter panels work

## Decisions

### D1: Length-guarded `replaceRuntimeHistory` with sessionStorage spill

**Choice:** Modify `replaceRuntimeHistory` in `shell-navigation.js` to measure the resulting URL. If it exceeds `URL_SAFE_LENGTH = 2000`, serialize the full query string into `sessionStorage` under a stable key derived from the pathname, and replace the URL's query with `?_s=1` (a marker). On page load, a `restoreUrlState()` function checks for `?_s=1`, reads sessionStorage, and restores the query params for the page to consume via `URLSearchParams`.

**Why this over alternatives:**
- *Per-page sessionStorage* — Requires changing every page's `updateUrlState`. The shared guard covers all 10 pages automatically.
- *URL hash encoding* — Hashes still go to the server on some browsers/proxies, and break anchor navigation.
- *Increase Gunicorn limit* — Not feasible; we don't control the production config.

**Key detail:** The sessionStorage key is `url-state:<pathname>` (e.g., `url-state:/wip-overview`). This means each page has exactly one stored state, and navigating between pages doesn't cause cross-contamination. The `_s=1` marker is stripped from the URL after restoration to keep the address bar clean.

### D2: Dedicated cross-page state for wip-overview ↔ wip-detail

**Choice:** Create `core/wip-navigation-state.js` with `storeWipNavigationState(filters, status)` and `loadWipNavigationState()`. When navigating from overview to detail, store filters in sessionStorage and navigate with only `?workcenter=X&status=Y`. When going back, store filters and navigate with only the overview base URL. The page on the receiving end reads from sessionStorage first, then falls back to URL params.

**Why not rely solely on D1:** The D1 guard handles the `replaceRuntimeHistory` case (refresh). But the cross-page navigation problem is different: the *destination* URL is new (not a replace), and the receiving page needs the filter context. D2 provides explicit intent-based state transfer. D1 + D2 together cover all three scenarios.

### D3: Fix `<a :href="backUrl">` to use SPA navigation

**Choice:** Replace `<a :href="backUrl">` in wip-detail with `<button @click="navigateBack">` using `navigateToRuntimeRoute`. This ensures the back action goes through the SPA router bridge when available, and stores filters via D2 before navigating.

**Why not `<router-link>`:** The wip-detail component is a native module loaded inside NativeRouteView, not directly aware of the Vue Router instance. `navigateToRuntimeRoute` is the established pattern for cross-module navigation.

### D4: POST-based export for reject-history, resource-history, production-history

**Choice:** Add `POST` method support to the three export endpoints (keeping GET for backward compat). Create a shared `core/post-export.js` utility that sends a POST with JSON body, receives the blob, and triggers download.

**Why POST:** Export params can be arbitrarily large (same multi-select arrays). GET URLs hit the same Gunicorn limit. POST body has no practical limit. The pattern already exists: `material-trace/export` and `job-query/export` are already POST-based.

### D5: E2E test coverage

**Choice:** Add Playwright tests that:
1. Navigate wip-overview → select many filters → drilldown to wip-detail → click back → verify no 400 error and filters preserved
2. Same for hold-overview with many filters → page refresh → verify no 400 error
3. Export CSV from reject-history with many filters → verify download succeeds (no 400)

Tests will use the real dev server (consistent with existing E2E test patterns in this project).

## Risks / Trade-offs

- **sessionStorage size limit (~5MB)** → Mitigation: URL query strings are at most ~100KB even in extreme cases. No risk of hitting the limit.
- **sessionStorage not shared across tabs** → Mitigation: This is actually desired. Each tab has its own filter state. Bookmarking a long-filter URL won't work (you get `?_s=1`), but this is acceptable since the alternative is a 400 error.
- **Race between replaceState and sessionStorage** → Mitigation: `restoreUrlState()` runs synchronously before any page component mounts, so the URL params are available by the time `initializePage()` reads them.
- **Stale sessionStorage on back/forward cache (bfcache)** → Mitigation: The `_s=1` marker in URL is the trigger; if sessionStorage was cleared, the page loads with empty filters (same as a fresh visit). The state in sessionStorage is keyed by pathname, so it's always the latest state for that page.
