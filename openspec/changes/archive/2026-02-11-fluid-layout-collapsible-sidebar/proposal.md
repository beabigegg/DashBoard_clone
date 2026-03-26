## Why

The portal shell just completed an iframe-to-Vue migration but still uses a block/card-based layout with `max-width: 1600px` centered shell, fixed `220px` sidebar, and rounded-corner card containers. This creates a segmented "boxed" appearance with wasted screen real estate and occasional card overflow issues. Converting to a full-screen fluid layout with a collapsible sidebar drawer maximizes usable space and provides a modern dashboard experience.

> **Scope**: This change is **Portal Shell Modernize Phase 1** — it targets the shell layout layer only (header, sidebar, content wrapper). Page-level component redesign (cards, tables, charts within individual pages) is out of scope and should be addressed in a separate Phase 2 change.

## What Changes

- **BREAKING**: Remove `max-width` constraints from the portal shell (`.shell` 1600px) and all page-level wrappers (`.dashboard` 1800px, `.qc-gate-page` 1900px, `.job-query-page` 1680px, etc.) — content fills available viewport width
- Remove border-radius and border from the shell header, sidebar, and content area — edge-to-edge fluid appearance
- Convert `.shell-main` from CSS Grid (`220px | 1fr`) to Flexbox with animated sidebar width transitions
- Add collapsible sidebar: desktop push-mode (width animates from 240px to 0), mobile overlay-mode (slide-in drawer with backdrop)
- Add hamburger toggle button in the shell header
- Add sidebar state persistence via `sessionStorage`
- Add mobile overlay backdrop with fade transition
- Add keyboard accessibility (Escape to close mobile drawer)
- Maintain existing gradient color scheme, navigation hierarchy, card-level styling within pages

## Capabilities

### New Capabilities
- `collapsible-sidebar-drawer`: Sidebar collapse/expand behavior, toggle button, mobile overlay, state persistence, keyboard accessibility, smooth transitions

### Modified Capabilities
- `spa-shell-navigation`: Shell layout changes from block-centered grid to full-screen fluid flexbox; sidebar becomes collapsible; content area becomes scrollable flex child
- `tailwind-design-system`: CSS variables updated (`--portal-shell-max-width` removed), `.u-content-shell` utility changed from max-width to full-width

## Impact

- **Portal shell** (`frontend/src/portal-shell/App.vue`, `frontend/src/portal-shell/style.css`): Major layout restructure — template adds toggle button, overlay, class bindings; CSS rewrites `.shell`, `.shell-main`, `.sidebar`; `.content` renamed to `.shell-content` to avoid class collision with page-level `.content` (e.g. in tables module)
- **Global styles** (`frontend/src/styles/tailwind.css`): CSS variable updates, utility class changes
- **Shell-registered page modules only**: Page-level max-width and padding overridden when embedded in shell via `.shell-content .xxx-page` selectors (standalone rendering unaffected). Verification scope limited to pages registered in shell route contracts — unregistered routes (e.g. missing contract warnings) are excluded
- **Health popup**: z-index adjustment needed to stay above new sidebar overlay layer
- **No new dependencies**: Pure Vue + Tailwind + CSS, no additional libraries
- **New test file**: `frontend/tests/portal-shell-sidebar.test.js` — automated tests (Node `node:test` harness) for sidebar collapse/expand, mobile overlay, and sessionStorage persistence
