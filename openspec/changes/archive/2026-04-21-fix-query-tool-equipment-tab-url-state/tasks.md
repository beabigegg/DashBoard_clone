## 1. Diagnose and centralize state hydration

- [x] 1.1 Identify the Query Tool component/composable that owns top-level tab and sub-tab URL-state hydration.
- [x] 1.2 Refactor tab restoration so initial load and route updates flow through one shared URL-to-state helper.

## 2. Restore active tab semantics

- [x] 2.1 Update equipment-tab initialization so `tab=equipment` restores the visible active tab on hard reload.
- [x] 2.2 Bind `aria-current="page"` to reactive active-tab state rather than click-only DOM mutations.
- [x] 2.3 Ensure equipment date filters and any equipment sub-tab state restore from URL in the same hydration flow.

## 3. Re-enable regression coverage

- [x] 3.1 Remove the `test.fixme` guard from `frontend/tests/playwright/query-tool-url-state.spec.js` for the equipment-tab reload case.
- [x] 3.2 Run the focused Query Tool URL-state Playwright coverage and confirm the reload scenario passes without breaking other tab flows.
