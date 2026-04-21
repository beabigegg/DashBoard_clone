# Fix: Query Tool Equipment Tab URL State Not Restored After Reload

## Why

Query Tool already writes equipment-tab state into the URL, but a hard reload does
not fully restore the UI state from those params. In the current behavior, the
address bar still contains the correct `tab=equipment` and date params, yet the
equipment tab button (`設備生產批次追蹤`) is not marked active and its
`aria-current="page"` state is missing.

This creates two concrete problems:

- The page violates the URL-state contract: a bookmark or reload does not restore
  the same visible state the URL claims.
- Accessibility state is wrong: screen readers and keyboard users get incorrect
  active-tab semantics.

The issue is currently pinned by
`frontend/tests/playwright/query-tool-url-state.spec.js:45`, which is marked
`test.fixme` until the bug is fixed.

## Repro

1. Navigate to Query Tool.
2. Click `設備生產批次追蹤`.
3. Fill a date range, for example `2026-03-01` to `2026-03-07`.
4. Confirm the URL contains the equipment-tab state.
5. Hard reload the page.
6. Observe that the URL still contains the tab/date params, but the tab button is
   not highlighted and does not have `aria-current="page"`.

## Expected vs Actual

| | Behaviour |
|---|---|
| **Expected** | On reload, the page reads URL params, restores the active tab to `equipment`, restores visible inputs, and renders `aria-current="page"` on the active tab button. |
| **Actual** | The URL params survive, but the UI falls back to the wrong tab state or an incomplete restored state; `aria-current` is absent or attached to the wrong button. |

## What Changes

- Restore Query Tool tab state from URL during initial page mount / hydration.
- Ensure tab selection is driven by a single reactive source of truth rather than
  click-only state.
- Ensure `aria-current="page"` is derived from that same active-tab state.
- Re-enable the existing Playwright regression test once the reload flow is fixed.

## Suggested Fix Direction

1. In the Query Tool page/component that owns tab state, read the `tab` URL param
   during initial mount and route updates, then call the same state transition used
   by an actual tab click.
2. If sub-tab state exists (`equipment_sub_tab`, lot-equipment sub-tab, etc.),
   restore those from URL in the same initialization path rather than in separate
   ad hoc handlers.
3. Bind `aria-current` directly to the reactive active-tab value so reload, back,
   forward, and direct links all render the same semantics.
4. Remove the `test.fixme` guard after the fix is verified.

## Acceptance

- Reloading Query Tool with `tab=equipment` restores the equipment tab visibly.
- The active equipment tab button renders `aria-current="page"` after reload.
- Date inputs and relevant sub-tab state are restored from the URL.
- `frontend/tests/playwright/query-tool-url-state.spec.js` no longer needs
  `test.fixme` for the equipment-tab reload scenario.
- Existing Query Tool URL-state tests for other tabs and flows stay green.

## Impact

- Affects Query Tool frontend tab-state initialization and URL-state sync logic.
- No backend/API contract changes.
- Low blast radius if implemented in the page-level tab-state wiring rather than
  scattered button handlers.

## Discovered By

Triage during `harden-production-test-coverage` change (T009), then linked from
the `Discovered Regressions` section of that change's proposal.
