# Fix: Query Tool Equipment Tab URL State Not Restored After Reload

## Problem

After a hard page reload, the Query Tool equipment tab (`設備生產批次追蹤`) does not restore its `aria-current="page"` state. The URL params (`?tab=equipment&start=...&end=...`) are present in the address bar but the tab button is not highlighted as active.

**Repro steps:**
1. Navigate to Query Tool → click `設備生產批次追蹤` tab
2. Set date range (e.g. 2026-03-01 to 2026-03-07)
3. Hard reload (`Ctrl+R`)
4. Observe: URL contains tab/date params, but the tab button does not have `aria-current="page"`

**Affected:** `frontend/tests/playwright/query-tool-url-state.spec.js:45` (test marked `test.fixme` until fixed)

## Expected vs Actual

| | Behaviour |
|---|---|
| **Expected** | After reload, the router reads URL params and sets active tab to `equipment`; tab button gets `aria-current="page"` |
| **Actual** | Tab button is not activated on reload; `aria-current` is absent or on the wrong tab |

## Suggested Fix Direction

1. In `QueryToolPage.vue` (or whichever component owns tab state), read the `tab` URL param in `onMounted` and call the tab activation handler.
2. Ensure `aria-current="page"` is set reactively from the active tab state (not just from click events).
3. Re-enable the `test.fixme` test in `query-tool-url-state.spec.js` after fix is verified.

## Discovered By

Triage during `harden-production-test-coverage` change (T009).
