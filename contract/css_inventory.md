# CSS Inventory (Governed Source List)

Updated: 2026-03-26

This file is the governed inventory for authored CSS source files in `frontend/src/**/*.css`.

Governance status (2026-03-12): `css-governance-check` = 0 errors, 0 warnings.

- Included: human-authored source CSS files under `frontend/src/`
- Excluded: build outputs under `src/mes_dashboard/static/dist/`

## Core / Global Layers

| File | Scope | Notes |
| :--- | :--- | :--- |
| `frontend/src/styles/tailwind.css` | Global base + components + utilities | The only allowed global `@layer base` location. Added: motion design tokens in `:root`, unified `ui-btn` BEM button system, `.ui-table-wrap` search trigger animation classes |
| `frontend/src/portal-shell/style.css` | Portal shell frame | Shell layout chrome and shell-wide UI |
| `frontend/src/portal-shell/ai-chat.css` | Portal shell AI chat | AI chat panel animations, typing indicator, step-text, and conversation divider; scoped under `.theme-portal-shell` |
| `frontend/src/portal/portal.css` | Legacy portal entry | Legacy portal host layout |

## Shared Feature Layers

| File | Scope | Notes |
| :--- | :--- | :--- |
| `frontend/src/wip-shared/styles.css` | `theme-wip-*`, hold/reject/query/material/yield shared blocks | Shared WIP domain primitives. **Cleaned**: removed `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-light`, `.btn-back` definitions (replaced by global `ui-btn` system). Summary/section classes retained pending component migration. |
| `frontend/src/wip-shared/pareto-styles.css` | Pareto chart/table shared blocks | Shared pareto presentation |
| `frontend/src/resource-shared/styles.css` | `theme-resource*` and related shared blocks | Shared resource domain primitives. **Cleaned**: removed `.btn`, `.btn-sm`, `.btn-primary` (replaced by `ui-btn`); removed `.error-banner` (replaced by shared-ui `ErrorBanner.vue`). Summary-grid/card/section-card classes retained pending component migration. |

## Shared UI Component Styles (scoped — new in frontend-unified-ux)

| File | Scope | Notes |
| :--- | :--- | :--- |
| `frontend/src/shared-ui/components/BlockLoadingState.vue` | `<style scoped>` | Block-level loading placeholder; `text` + `minHeight` props; replaces ad-hoc `loading-text` divs |
| `frontend/src/shared-ui/components/LoadingSpinner.vue` | `<style scoped>` | Inline spinner; sizes sm/md/lg; reduced-motion fallback added |
| `frontend/src/shared-ui/components/LoadingOverlay.vue` | `<style scoped>` | Section/page tier overlay |
| `frontend/src/shared-ui/components/SkeletonLoader.vue` | `<style scoped>` | Shared skeleton variants for text/card/table loading states with reduced-motion fallback |
| `frontend/src/shared-ui/components/EmptyState.vue` | `<style scoped>` | Typed empty state messages |
| `frontend/src/shared-ui/components/ErrorBanner.vue` | `<style scoped>` | Dismissible error banner; `message` prop + `action` slot + `dismiss` event |
| `frontend/src/shared-ui/components/SummaryCard.vue` | `<style scoped>` | Summary card with accent bar, label, value, sub slot; `accent` prop for color theming |
| `frontend/src/shared-ui/components/SummaryCardGroup.vue` | `<style scoped>` | Responsive grid container for SummaryCard; `columns` prop |
| `frontend/src/shared-ui/components/SectionCard.vue` | `<style scoped>` | Section wrapper with optional header, collapsible body, footer; `variant` prop for visual style |
| `frontend/src/shared-ui/components/DataTable.vue` | `<style scoped>` | Shared data table with sorting, pagination, slot columns; `data-table-*` scoped classes |
| `frontend/src/shared-ui/components/Chip.vue` | `<style scoped>` | Inline label chip/tag; `tone` prop for semantic coloring |

## Route-Local Feature Layers

| File | Primary Theme Root | Route / Feature |
| :--- | :--- | :--- |
| `frontend/src/admin-dashboard/style.css` | `theme-admin-dashboard` | admin-dashboard |
| `frontend/src/admin-performance/style.css` | `theme-admin-performance` | admin-performance |
| `frontend/src/admin-user-usage-kpi/style.css` | `theme-admin-user-usage-kpi` | admin-user-usage-kpi |
| `frontend/src/anomaly-overview/style.css` | `theme-anomaly-overview` | anomaly-overview |
| `frontend/src/excel-query/style.css` | `theme-excel-query` | excel-query |
| `frontend/src/hold-detail/style.css` | `theme-hold-detail` | hold-detail |
| `frontend/src/hold-history/style.css` | `theme-hold-history` | hold-history |
| `frontend/src/hold-overview/style.css` | `theme-hold-overview` | hold-overview |
| `frontend/src/job-query/style.css` | `theme-job-query` | job-query |
| `frontend/src/material-trace/style.css` | `theme-material-trace` | material-trace |
| `frontend/src/mid-section-defect/style.css` | `theme-mid-section-defect` | mid-section-defect |
| `frontend/src/qc-gate/style.css` | `theme-qc-gate` | qc-gate |
| `frontend/src/query-tool/style.css` | `theme-query-tool` | query-tool |
| `frontend/src/reject-history/style.css` | `theme-reject-history` | reject-history |
| `frontend/src/resource-history/style.css` | `theme-resource-history` | resource-history |
| `frontend/src/resource-status/style.css` | `theme-resource` | resource-status |
| `frontend/src/tables/style.css` | `theme-tables` | tables |
| `frontend/src/wip-detail/style.css` | `theme-wip-detail` | wip-detail |
| `frontend/src/wip-overview/style.css` | `theme-wip-overview` | wip-overview |
| `frontend/src/yield-alert-center/style.css` | `theme-yield-alert-center` | yield-alert-center |
| `frontend/src/production-history/style.css` | `theme-production-history` | production-history |

## Synchronization Rule

Any PR that adds/removes/renames/moves a CSS source file in `frontend/src/**/*.css` MUST update this inventory in the same change.
