---
contract: css-inventory
schema-version: 1.2.10
summary: Governed inventory of authored CSS source files under frontend/src/.
owner: application-team
surface: ui
last-changed: 2026-07-08
---

# CSS Inventory (Governed Source List)

> 來源：遷移自 `contract/css_inventory.md`（2026-03-26 → 2026-05-05）  
> Governance status (2026-03-12): `css-governance-check` = 0 errors, 0 warnings。

- **Included：** 人工撰寫的 CSS source files，位於 `frontend/src/**/*.css`
- **Excluded：** build outputs，位於 `src/mes_dashboard/static/dist/`

---

## Core / Global Layers

| File | Scope | Notes |
|---|---|---|
| `frontend/src/styles/tailwind.css` | Global base + components + utilities | 唯一允許寫 `@layer base` 的位置。含 motion design tokens、`ui-btn` BEM 按鈕系統、`.ui-table-wrap` 搜尋觸發動畫 |
| `frontend/src/portal-shell/style.css` | Portal shell frame | Shell layout chrome 和 shell-wide UI |
| `frontend/src/portal-shell/ai-chat.css` | Portal shell AI chat | AI chat panel 動畫、typing indicator；scoped under `.theme-portal-shell` |
| `frontend/src/portal/portal.css` | Legacy portal entry | Legacy portal host layout |

## Shared Feature Layers

| File | Scope | Notes |
|---|---|---|
| `frontend/src/wip-shared/styles.css` | `theme-wip-*`, hold/reject/query/material/yield shared blocks | 已清理：移除 `.btn*`（替換為 `ui-btn` 系統）；summary/section classes 待元件遷移 |
| `frontend/src/wip-shared/pareto-styles.css` | Pareto chart/table shared blocks | 共用 pareto 呈現 |
| `frontend/src/resource-shared/styles.css` | `theme-resource*` | 已清理：移除 `.btn*`（替換為 `ui-btn`）、`.error-banner`（替換為 `ErrorBanner.vue`） |

## Shared UI Component Styles（scoped）

| File | Scope | Notes |
|---|---|---|
| `frontend/src/shared-ui/components/BlockLoadingState.vue` | `<style scoped>` | Block-level loading placeholder |
| `frontend/src/shared-ui/components/LoadingSpinner.vue` | `<style scoped>` | Inline spinner；sizes sm/md/lg；reduced-motion fallback |
| `frontend/src/shared-ui/components/LoadingOverlay.vue` | `<style scoped>` | Section/page tier overlay |
| `frontend/src/shared-ui/components/SkeletonLoader.vue` | `<style scoped>` | Skeleton variants（text/card/table）；reduced-motion fallback |
| `frontend/src/shared-ui/components/EmptyState.vue` | `<style scoped>` | 型別化 empty state messages |
| `frontend/src/shared-ui/components/ErrorBanner.vue` | `<style scoped>` | 可關閉的 error banner；`message` prop + `action` slot + `dismiss` event |
| `frontend/src/shared-ui/components/SummaryCard.vue` | `<style scoped>` | Summary card；`accent` prop |
| `frontend/src/shared-ui/components/SummaryCardGroup.vue` | `<style scoped>` | Responsive grid container；`columns` prop |
| `frontend/src/shared-ui/components/SectionCard.vue` | `<style scoped>` | Section wrapper；`variant` prop |
| `frontend/src/shared-ui/components/DataTable.vue` | `<style scoped>` | Data table；`data-table-*` scoped classes |
| `frontend/src/shared-ui/components/Chip.vue` | `<style scoped>` | Inline chip/tag；`tone` prop |
| `frontend/src/shared-ui/components/AsyncQueryProgress.vue` | `<style scoped>` | Async job progress bar；`pct` (0–100), `stage` label, `status` prop；reduced-motion fallback required |

## Route-Local Feature Layers

| File | Primary Theme Root | Route / Feature |
|---|---|---|
| `frontend/src/admin-dashboard/style.css` | `theme-admin-dashboard` | admin-dashboard | move-target-permissions-panel: gained `.pa-perm-*` rules for the relocated target-edit permission whitelist tab; panel-exclusive names used (not the pre-existing generic `.status-badge`/bare `table` rules already used by `RecentSessionsTable.vue`) to avoid a same-name collision |
| `frontend/src/admin-pages/style.css` | `theme-admin-pages` | admin-pages | move-target-permissions-panel: lost the two `.pa-perm-add-row`/`.pa-perm-add-input` rules (panel relocated to admin-dashboard); shared `.table-container`/`.status-badge`/etc. rules kept — still used by `PagesManagementPanel` |
| `frontend/src/anomaly-overview/style.css` | `theme-anomaly-overview` | anomaly-overview |
| `frontend/src/eap-alarm/style.css` | `theme-eap-alarm` | eap-alarm |
| `frontend/src/db-scheduling/style.css` | `theme-db-scheduling` | db-scheduling |
| `frontend/src/downtime-analysis/style.css` | `theme-downtime-analysis` | downtime-analysis |
| `frontend/src/hold-detail/style.css` | `theme-hold-detail` | hold-detail |
| `frontend/src/hold-history/style.css` | `theme-hold-history` | hold-history |
| `frontend/src/hold-overview/style.css` | `theme-hold-overview` | hold-overview |
| `frontend/src/job-query/style.css` | `theme-job-query` | job-query |
| `frontend/src/material-consumption/style.css` | `theme-material-consumption` | material-consumption |
| `frontend/src/material-trace/style.css` | `theme-material-trace` | material-trace |
| `frontend/src/mid-section-defect/style.css` | `theme-mid-section-defect` | mid-section-defect | Sankey/Heatmap chart styles for forward cause-effect analysis; all rules scoped under `.theme-mid-section-defect` (css-contract Rule 4.2/4.3) |
| `frontend/src/qc-gate/style.css` | `theme-qc-gate` | qc-gate |
| `frontend/src/query-tool/style.css` | `theme-query-tool` | query-tool |
| `frontend/src/reject-history/style.css` | `theme-reject-history` | reject-history — `.supplementary-panel/.supplementary-header/.supplementary-row/.supplementary-toolbar` removed (rh-remove-supplementary-filter); `.primary-prefilter-row` grid is `repeat(4, minmax(0, 1fr))` |
| `frontend/src/resource-history/style.css` | `theme-resource-history` | resource-history |
| `frontend/src/resource-status/style.css` | `theme-resource` | resource-status |
| `frontend/src/wip-detail/style.css` | `theme-wip-detail` | wip-detail |
| `frontend/src/wip-overview/style.css` | `theme-wip-overview` | wip-overview |
| `frontend/src/yield-alert-center/style.css` | `theme-yield-alert-center` | yield-alert-center |
| `frontend/src/production-history/style.css` | `theme-production-history` | production-history |
| `frontend/src/production-achievement/style.css` | `theme-production-achievement` | production-achievement |

---

## Synchronization Rule

任何新增/刪除/重新命名/搬移 `frontend/src/**/*.css` 的 PR 必須在同一變更同步更新此清單。

## CHANGELOG

## [css-inventory 1.2.10] — 2026-07-08
### Changed
- move-target-permissions-panel: `admin-dashboard/style.css` row note updated (gained `.pa-perm-*` rules for the relocated target-edit permission whitelist tab); `admin-pages/style.css` row note updated (lost the two panel-exclusive `.pa-perm-add-row`/`.pa-perm-add-input` rules; shared table/badge rules kept for `PagesManagementPanel`). No file added/removed from the Route-Local Feature Layers table.

## [css-inventory 1.2.9] — 2026-07-02
### Added
- production-achievement-kanban: `frontend/src/production-achievement/style.css` registered with `theme-production-achievement` root. Route-Local Feature Layers table.

## [css-inventory 1.2.8] — 2026-06-30
### Changed
- msd-forward-cause-effect: Updated `frontend/src/mid-section-defect/style.css` row note to document Sankey/Heatmap chart styles for forward cause-effect analysis; all rules must remain scoped under `.theme-mid-section-defect` (css-contract Rule 4.2/4.3).

## [css-inventory 1.2.7] — 2026-06-26
### Added
- add-db-scheduling-page: `frontend/src/db-scheduling/style.css` registered with `theme-db-scheduling` root. Route-Local Feature Layers table.
