## 1. Sidebar State Management (App.vue script)

- [x] 1.1 Add `sidebarCollapsed`, `sidebarMobileOpen`, `isMobile` refs to `App.vue` `<script setup>`
- [x] 1.2 Implement `toggleSidebar()`, `closeMobileSidebar()`, `checkViewport()` functions
- [x] 1.3 Add `sessionStorage` load/save for sidebar collapsed preference (`portal-shell:sidebar-collapsed`)
- [x] 1.4 Register `resize` listener in `onMounted`, clean up in `onUnmounted`
- [x] 1.5 Add Escape key handler to close mobile sidebar overlay
- [x] 1.6 Add `closeMobileSidebar()` call to existing route watcher for auto-close on navigation

## 2. Template Restructure (App.vue template)

- [x] 2.1 Add `.shell-header-left` wrapper with hamburger toggle `<button>` (inline SVG, `aria-label`, `aria-expanded`)
- [x] 2.2 Add `:class` binding on `.shell` root: `{ 'sidebar-collapsed': sidebarCollapsed && !isMobile }`
- [x] 2.3 Add `:class` bindings on `<aside class="sidebar">`: `sidebar--collapsed`, `sidebar--mobile-open`, `sidebar--mobile-closed`
- [x] 2.4 Add `<Transition name="overlay-fade">` wrapped `<div class="sidebar-overlay">` before `<main>`, shown when `isMobile && sidebarMobileOpen`
- [x] 2.5 Rename `<section class="content">` to `<section class="shell-content">` in the template

## 3. Shell CSS Rewrite (`frontend/src/portal-shell/style.css`)

- [x] 3.1 Rename all `.content` selectors to `.shell-content` throughout `style.css` (`.content`, `.content .xxx-page`, etc.)
- [x] 3.2 `.shell`: remove `max-width: 1600px`, `padding: 20px`, `margin: 0 auto`; add `display: flex; flex-direction: column`
- [x] 3.3 `.shell-header`: remove `border-radius: 12px`; adjust `padding` to `12px 20px`; add `flex-shrink: 0`
- [x] 3.4 Add `.shell-header-left` styles (flex, align-items center, gap 12px)
- [x] 3.5 Add `.sidebar-toggle` button styles (36x36, border/bg rgba white, hover, focus-visible outline)
- [x] 3.6 `.shell-main`: replace `display: grid; grid-template-columns` with `display: flex; flex: 1; overflow: hidden`; remove legacy `gap: 12px` to prevent residual gutter when sidebar collapses
- [x] 3.7 `.sidebar`: rewrite to `width: 240px; min-width: 240px; border-right; overflow-y: auto; flex-shrink: 0; transition: width/min-width/padding 0.3s; white-space: nowrap` — remove border-radius, border, sticky, height: fit-content
- [x] 3.8 Add `.sidebar--collapsed` styles: `width: 0; min-width: 0; padding: 0; border-right: none; overflow: hidden`
- [x] 3.9 Add `.sidebar--mobile-closed` styles: fixed position, `transform: translateX(-100%)`, 280px width, z-index 40
- [x] 3.10 Add `.sidebar--mobile-open` styles: fixed position, `transform: translateX(0)`, box-shadow, z-index 40
- [x] 3.11 Add `.sidebar-overlay` styles: fixed inset 0, z-index 35, `background: rgba(0,0,0,0.4)`
- [x] 3.12 Add `overlay-fade` transition classes (enter/leave opacity 0.3s)
- [x] 3.13 `.shell-content`: remove `border`, `border-radius: 10px`, `min-height: 70vh`; add `flex: 1; min-width: 0; overflow-y: auto`; change background to `#f5f7fa`
- [x] 3.14 Bump `.health-popup` z-index from `30` to `50`

## 4. Page-Level Overrides (`frontend/src/portal-shell/style.css`)

- [x] 4.1 Add `.shell-content .resource-page, .shell-content .dashboard, .shell-content .qc-gate-page, .shell-content .job-query-page, .shell-content .excel-query-page, .shell-content .query-tool-page, .shell-content .tmtt-page, .shell-content .tables-page` override: `max-width: none; min-height: auto`
- [x] 4.2 Add `.shell-content .tables-page .container` override: `max-width: none` (tables module has max-width on inner `.container`, not on page wrapper)
- [x] 4.3 Add `.shell-content .resource-page` override: `padding: 0` (remove duplicate padding)

## 5. Responsive and Accessibility (`frontend/src/portal-shell/style.css`)

- [x] 5.1 Simplify `@media (max-width: 900px)` block — remove grid/sidebar rules (now JS-driven); keep header/content padding adjustments only
- [x] 5.2 Extend `@media (prefers-reduced-motion: reduce)` to include `.sidebar`, `.sidebar--mobile-*`, `.sidebar-overlay`, `.overlay-fade-*`, `.sidebar-toggle`

## 6. CSS Variables Update (`frontend/src/styles/tailwind.css`)

- [x] 6.1 Change `--portal-shell-max-width` from `1600px` to `none`
- [x] 6.2 Add `--portal-sidebar-width: 240px` and `--shell-header-height: 56px`
- [x] 6.3 Update `.u-content-shell` utility: replace `max-width` with `width: 100%`

## 7. Automated Tests

- [x] 7.1 Create `frontend/tests/portal-shell-sidebar.test.js` using existing Node `node:test` harness
- [x] 7.2 Test: desktop sidebar collapse — toggle sets `sidebarCollapsed` to true, sidebar gets `sidebar--collapsed` class
- [x] 7.3 Test: mobile overlay close via backdrop — clicking overlay calls `closeMobileSidebar()`, `sidebarMobileOpen` becomes false
- [x] 7.4 Test: mobile overlay close via Escape — pressing Escape when overlay open closes sidebar
- [x] 7.5 Test: sessionStorage persistence — collapsing sidebar writes to sessionStorage; mounting with stored value restores collapsed state

## 8. Manual Verification

- [x] 8.1 Run `npm run build` — confirm no build errors
- [x] 8.2 Test desktop: sidebar expanded → toggle collapse → toggle expand (smooth 300ms animation)
- [x] 8.3 Test mobile (<= 900px): toggle opens overlay drawer with backdrop → tap backdrop closes → Escape closes
- [x] 8.4 Test route navigation auto-closes mobile sidebar
- [x] 8.5 Test health popup z-index: open health popup while mobile sidebar is open → popup stays on top
- [x] 8.6 Test shell-registered page modules render fluid (no max-width centering) within the shell
- [x] 8.7 Test `prefers-reduced-motion`: all transitions disabled
- [x] 8.8 Verify tables module `.content` class is not affected by shell `.shell-content` styles
