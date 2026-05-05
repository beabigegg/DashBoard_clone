---
contract: css-inventory
summary: Governed inventory of authored CSS source files under frontend/src/.
owner: application-team
surface: ui
last-changed: 2026-05-05
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

## Route-Local Feature Layers

| File | Primary Theme Root | Route / Feature |
|---|---|---|
| `frontend/src/admin-dashboard/style.css` | `theme-admin-dashboard` | admin-dashboard |
| `frontend/src/admin-performance/style.css` | `theme-admin-performance` | admin-performance |
| `frontend/src/admin-user-usage-kpi/style.css` | `theme-admin-user-usage-kpi` | admin-user-usage-kpi |
| `frontend/src/anomaly-overview/style.css` | `theme-anomaly-overview` | anomaly-overview |
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

---

## Synchronization Rule

任何新增/刪除/重新命名/搬移 `frontend/src/**/*.css` 的 PR 必須在同一變更同步更新此清單。
