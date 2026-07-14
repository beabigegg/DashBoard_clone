# Visual Review Report

## Affected Screens
- 生產達成率 report (`/production-achievement`) — full App.vue rewrite: 4-button mode switch (當日/前日/當月/自訂區間), DailyView/CumulativeView table+KPI cards, new PlanAchievementStackedChart, unchanged TargetEditPanel, 設定 button.
- NEW 生產達成率設定 mini-app (`/production-achievement-settings`, standalone route, no drawer entry) — header card + OD-5 save-note banner + 3 panels: PackageLfMappingPanel, WorkcenterMergeMappingPanel, DailyPlanPanel.

## Viewports Checked
Desktop/tablet/mobile: static source review only (flex-wrap + min/max-width reasoning from Vue templates + CSS). No live-rendered screenshots — Playwright unusable in this sandbox (Chromium v1228 cached vs v1208 pinned; installing a new version is against CI-runner-only policy), same limitation every other test agent hit this session.

## States Checked
default, loading, empty, error, disabled — all present and consistently wired (LoadingOverlay/BlockLoadingState/AsyncQueryProgress/DataTable-loading; ErrorBanner + per-panel editError; editForbidden/editSaving gating). hover/focus — ui-btn shared hover established elsewhere; explicit :focus only on `.pa-app__input` (settings inputs fall back to native focus, matching pre-existing `.pa-target-panel__*` precedent — advisory only). long-text — not empirically tested; relies on shared DataTable's established wrapping (out of this change's scope, unmodified).

## Evidence
- screenshots: none (Playwright unavailable in sandbox)
- videos: none
- diff reports: none (pixel-level visual assertions explicitly out of scope per test-plan.md § Out of Scope)
- build: fresh `npm run build` → exit 0, 2895 modules; compiled CSS shows `--pa-shift-d:#2563eb`, `--pa-shift-n:#7c3aed`, `--pa-plan-line:#ef4444`, `--pa-cumulative-rate:#16a34a`, `.pa-settings__save-note{background:#ecfdf5;border:1px solid #6ee7b7;color:#065f46}`; zero unresolved `theme(` strings anywhere in built dist tree
- lint: fresh `npm run css:check` → 0 errors, 308 warnings (0 attributable to the 2 changed files)
- unit tests: fresh `npx vitest run .../PlanAchievementStackedChart.test.ts` → 7/7 passed (empty-state, real-stack, uncapped >100%, null→0, y=100 markLine, resolveCssVar-only colors, dual x-axis shape reuse)

## CSS Contract Findings
- Rule 2.1–2.4 (token source of truth + chart exception): compliant — 4 new tokens (`h065f46`, `h6ee7b7`, `h7c3aed`, `hecfdf5`) now correctly registered in `tailwind.config.js` (fixed by main Claude after e2e-resilience-engineer found the build-breaking gap; independently re-verified by visual-reviewer via static cross-reference, fresh build, and compiled-CSS-output inspection); chart colors indirected via CSS custom properties + `resolveCssVar()`, mirroring `resource-history/components/StackedChart.vue` (verified identical `resolveCssVar()` implementation).
- Rule 4.1–4.3 (scoping): compliant, 0 unscoped rules in either file (css:check Rule 6 clean).
- Rule 4.4/4.5: N/A (no Teleport; no `:is()` shared-file reuse) — matches css-contract.md CHANGELOG note.
- Rule 5.1/5.2: compliant, no base resets.
- Governance sync: `contracts/css/css-contract.md` (1.16.0) and `contracts/css/css-inventory.md` (1.2.12) both updated same-PR, dated 2026-07-14.
- Advisory (non-blocking): `pa-app__empty-state` class/text mismatch (cosmetic, "正在載入..." loading copy on a class named `empty-state`); `.pa-settings-panel__input`/`__select` lack a custom `:focus` style (faithful parity with pre-existing `.pa-target-panel__*` classes, not a new regression — optional future polish).

## Decision
approved
