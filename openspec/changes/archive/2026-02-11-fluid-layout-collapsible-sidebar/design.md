## Context

The portal shell (`frontend/src/portal-shell/App.vue` + `frontend/src/portal-shell/style.css`) currently uses a block-centered layout: `.shell` has `max-width: 1600px; margin: 0 auto; padding: 20px`, `.shell-main` uses `display: grid; grid-template-columns: 220px minmax(0,1fr)`, and both `.sidebar` and `.content` are styled as bordered, rounded white cards. Page modules add their own `max-width` (1680-1900px) and `padding`.

The result is a segmented, boxed appearance that wastes screen real estate. The migration to full-screen fluid layout with a collapsible drawer addresses this.

**Constraints:**
- No new dependencies (pure Vue 3 + Tailwind CSS 3 + vanilla CSS)
- Sidebar navigation items are text-only (no icons) — icon-only collapsed mode is not viable
- Pages must still render correctly standalone (outside the portal shell) for development
- Existing color scheme and navigation hierarchy must be preserved

## Goals / Non-Goals

**Goals:**
- Full-viewport fluid layout with no max-width constraints at shell or page level
- Collapsible sidebar: push-mode on desktop (content resizes), overlay-mode on mobile
- Smooth 300ms transitions for sidebar open/close
- Sidebar state persistence within browser session
- Keyboard accessibility (Escape closes mobile drawer)
- Maintain all existing navigation, routing, and page functionality

**Non-Goals:**
- Icon-only collapsed sidebar mode (nav items have no icons; complete hide is chosen)
- Redesigning individual page components or card layouts within pages (deferred to Phase 2)
- Adding new dependencies (headlessui, shadcn, etc.)
- Server-side changes or API modifications
- Full ARIA focus-trap for mobile overlay (simple Escape + backdrop click suffices)
- Verifying pages not registered in shell route contracts (e.g. routes with missing contract warnings)

## Decisions

### D1: Flexbox over CSS Grid for `.shell-main`

**Choice**: Replace `display: grid; grid-template-columns: 220px minmax(0,1fr)` with `display: flex`.

**Rationale**: CSS Grid `grid-template-columns` cannot be smoothly animated with CSS transitions. Flexbox with `width` + `min-width` transitions on the sidebar provides smooth animated collapse/expand. The layout is a simple two-column split, which flexbox handles naturally.

### D2: Sidebar collapses to 0 width (complete hide)

**Choice**: Desktop collapsed state sets sidebar `width: 0; min-width: 0; overflow: hidden`.

**Rationale**: The current navigation items are text-only with no icons. An icon-only strip would require adding icons to every nav item — a separate design effort. Complete hide is the simplest approach that provides maximum content space.

### D3: Mobile overlay vs desktop push

**Choice**: Desktop uses push mode (content resizes via flex). Mobile (<=900px) uses fixed-position overlay with backdrop.

**Rationale**: On desktop, push mode provides a stable layout without content obscuring. On mobile, the viewport is too narrow for push mode — overlay maximizes both sidebar and content usability. The 900px breakpoint matches the existing responsive threshold.

### D4: JavaScript viewport detection instead of pure CSS media queries

**Choice**: Use a `resize` event listener to set `isMobile` ref, then apply CSS classes based on state.

**Rationale**: The sidebar has three distinct behaviors: desktop-expanded, desktop-collapsed, and mobile-overlay. Pure CSS media queries cannot differentiate between "desktop-collapsed" and "mobile-hidden" since both have zero sidebar width. JavaScript state allows clean separation of desktop collapse (user choice) and mobile overlay (viewport-driven).

### D5: `sessionStorage` for sidebar preference

**Choice**: Persist collapsed/expanded state in `sessionStorage` (not `localStorage`).

**Rationale**: Session-scoped persistence means the user's choice persists across page navigations and refreshes within the same tab, but new tabs start with sidebar expanded. This matches the ephemeral nature of a UI layout preference. The codebase already uses `sessionStorage` for recovery keys in `NativeRouteView.vue`.

### D6: Page-level max-width override via scoped selectors

**Choice**: Add `.shell-content .xxx-page { max-width: none; }` rules in `frontend/src/portal-shell/style.css` rather than modifying each page's CSS. Include `.shell-content .tables-page .container` for the tables module where `max-width` is on the inner `.container` element, not the page wrapper.

**Rationale**: This keeps all shell-level layout overrides in one file, preserves standalone page rendering (pages still have their own max-width when accessed directly), and avoids touching 10+ page CSS files.

### D7: Content area background color

**Choice**: Change `.shell-content` background from `#ffffff` to `#f5f7fa` (app background color).

**Rationale**: With borders and border-radius removed, the content area merges visually with the page background. Using the app bg color instead of white allows individual page cards (`.section-card`, `.header-gradient`) to stand out on their own. This maintains the card-on-background visual hierarchy.

### D8: Rename `.content` to `.shell-content` to prevent CSS collision

**Choice**: Rename the shell's main content area class from `.content` to `.shell-content` in both the template and CSS.

**Rationale**: The tables module (`tables/App.vue:81`) and potentially other page modules also use a `.content` class. If the shell rewrites `.content` with `flex: 1; overflow-y: auto`, it will leak into page-level `.content` elements and cause layout breakage. Using `.shell-content` scopes the styles unambiguously to the shell layer. This is a low-cost rename (one template attribute + CSS find-and-replace in a single file) with high defensive value.

## Risks / Trade-offs

- **[Text wrapping during animation]** → Sidebar text may wrap awkwardly during 300ms width transition. Mitigate with `white-space: nowrap; overflow: hidden` on the sidebar.
- **[Double scrollbar]** → Content area gets `overflow-y: auto`, but some pages have `min-height: 100vh`. Mitigate with `.shell-content .resource-page { min-height: auto }` overrides.
- **[Residual gutter after collapse]** → If legacy `.shell-main` `gap: 12px` is left in place during flex migration, collapsed sidebar still leaves visible empty space. Mitigate by removing `gap` from `.shell-main`.
- **[Health popup z-index clash]** → `.health-popup` uses `z-index: 30` which is below mobile sidebar overlay `z-index: 40`. Mitigate by bumping health popup to `z-index: 50`.
- **[Wide content readability]** → Removing all max-width means tables and cards stretch on ultra-wide monitors. Accepted trade-off per user preference. Individual page teams can re-add max-width later if needed.
- **[sessionStorage loss]** → If user clears session data, sidebar preference resets. Acceptable — sidebar defaults to expanded which is a safe fallback.
- **[CSS class collision]** → Shell `.content` class collides with page-level `.content` (e.g. tables module). Mitigate by renaming to `.shell-content` (Decision D8).
