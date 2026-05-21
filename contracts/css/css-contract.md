---
contract: css
summary: UI token policy, component styling rules, and visual review constraints.
owner: application-team
surface: ui
schema-version: 1.4.0
last-changed: 2026-05-21
breaking-change-policy: deprecate-2-minors
---

# CSS / UI Contract — MES Dashboard

> 來源：遷移自 `contract/css_development_contract.md` v1.1（2026-05-05）

## Token Source of Truth

**`frontend/tailwind.config.js` 是唯一真實來源。**

| 契約 | 規則 |
|---|---|
| 2.1 | 禁止在任何 `.css` 的 `:root` 中手動定義設計規範（顏色、間距、字體等） |
| 2.2 | 所有新設計規範必須加入 `tailwind.config.js` 的 `theme.extend` |
| 2.3 | CSS 檔案中引用設計規範必須透過 Tailwind `theme()` 函式 |
| 2.4 | **例外**：第三方圖表函式庫（ECharts）因 API 限制無法用 `theme()`，允許在 JS/Vue 圖表設定物件中使用色碼，但須遵守圖表例外治理（見下§6） |

## 樣式決策框架

| 契約 | 規則 |
|---|---|
| 3.1 | 優先使用 Tailwind 功能類別（utility-first）；例：`flex items-center rounded-lg` |
| 3.2 | 一組功能類別組合在專案中重複出現 **3 次以上**時，抽象化為語意化元件類別 |
| 3.2.1 | 元件類別使用 `@apply` 組合 Tailwind 功能類別 |
| 3.2.2 | **全域複用**元件（按鈕、輸入框、徽章）必須定義在 `frontend/src/styles/tailwind.css` 的 `@layer components` 中，以 `ui-` 前綴 |
| 3.2.3 | 僅當樣式無法透過 Tailwind 實現（偽元素、複雜 `calc()`）才在元件類別撰寫原生 CSS，仍需用 `theme()` |
| 3.3 | **嚴格禁止**在 Vue `<template>` 中使用 `style="..."` 定義靜態樣式（僅限動態綁定） |

## 樣式作用域與隔離

| 契約 | 規則 |
|---|---|
| 4.1 | 功能區塊的樣式檔（如 `resource-shared/styles.css`）**嚴禁**包含 `html`, `body`, `*` 等全域標籤的樣式 |
| 4.2 | 每個主要功能區塊必須定義唯一「主題根類別」（如 `.theme-resource`, `.theme-wip`），應用於最外層容器 |
| 4.3 | 功能區塊所有樣式規則必須以主題根類別為父選擇器，防止洩漏 |

## 基礎樣式

| 契約 | 規則 |
|---|---|
| 5.1 | 所有全域基礎樣式和 CSS 重置必須統一在 `frontend/src/styles/tailwind.css` 的 `@layer base` 定義（`preflight` 已被禁用） |
| 5.2 | 任何其他 CSS 檔案禁止包含自己的基礎樣式重置 |

## 圖表與函式庫例外治理

| 契約 | 規則 |
|---|---|
| 6.1 | 例外只適用於第三方圖表函式庫設定（ECharts `option`, `itemStyle`, `visualMap`, `lineStyle`）；不適用於一般 CSS 或 Vue template style |
| 6.2 | 圖表顏色優先由集中 palette/token 映射取得，不得在多處散落重複硬編碼 |
| 6.3 | 必須保留 HEX 的條件：色碼位於圖表設定上下文；具備明確語意（`danger`, `warning`, `seriesA`）；同一檔案重複色碼需抽為常數或 palette |
| 6.4 | 圖表例外需透過 `frontend/scripts/css-governance-check.js` 盤點（warning/allow-candidate）；非圖表上下文的 HEX 視為違規（error） |

## Component Rules

| component | variants | states | allowed overrides |
|---|---|---|---|
| `DataTable.vue` | — | loading（`:loading` prop）、empty | 只能透過 props/slots；禁止外部定義 `data-table-*` CSS |
| `SummaryCard` | `accent` prop | — | 不得保留舊的 `.summary-card` / `.summary-grid` CSS |
| `Chip` | `tone` prop | — | 禁止自訂 pill/tag CSS 取代 tone 系統 |
| `SectionCard` | — | — | 禁止在 feature CSS 新增 `.section-card` |
| `ErrorBanner` | — | — | 禁止在 feature CSS 新增 `.error-banner` |
| `LoadingOverlay` | `tier="page"` | — | 禁止自訂 full-page spinner |

## Loading 三層治理

| 場景 | 必須使用 | 禁止 |
|---|---|---|
| Page-level（初始化全局等待） | `<LoadingOverlay tier="page" />` | 自訂 `@keyframes` + fixed/absolute 全屏遮罩 |
| Component-level（按鈕 busy） | `is-loading` class + `<LoadingSpinner size="sm" />` + `disabled` + loading 文案 | 保留自定義 `.btn-spinner` |
| Block-level（DataTable） | `DataTable :loading` prop | 同一區塊並存 `ui-table-wrap.is-loading` 與 `:loading` |
| Block-level（非 DataTable） | `<BlockLoadingState />` 或 `<EmptyState type="loading" />` | — |

所有 loading 動畫必須尊重 `prefers-reduced-motion`。

## CSS Inventory Governance

| 契約 | 規則 |
|---|---|
| 7.1 | `contracts/css/css-inventory.md`（若存在）或 `contract/css_inventory.md` 為 `frontend/src/**/*.css` 的治理索引 |
| 7.2 | 新增/刪除/重新命名/搬移任何 CSS 檔案，必須在同一變更更新清單 |
| 7.3 | CSS 規則大幅搬移時，必須更新清單的 scope/notes 欄位 |
| 7.4 | `src/mes_dashboard/static/dist/*` 產物不屬清單治理範圍 |

## Detail Table Layout Rule

明細表（detail table）必須渲染為單一平面表格，不得嵌套在額外的卡片或包裝容器內。

| 頁面 | 明細表元件 / 區塊 | 規則 |
|---|---|---|
| `hold-history` | `DetailTable.vue`（Hold / Release 明細） | 必須直接使用 `DataTable` + `DataTableColumn` 渲染為單一平面表格，不得在 `<section class="card">` 之外再套額外 wrapper 卡片 |
| `hold-overview` | `App.vue` 內的 "Hold Lot Details" 區塊 | 同上，`DataTable` 直接置於 `.card-body` 內，不允許嵌套額外容器卡片 |
| `reject-history` | `components/DetailTable.vue`（明細列表） | `.card-body` 必須套用 `padding: 0` scoped override，DataTable 緊貼卡片邊緣，不得保留 `style.css` 的 `.card-body` 全域 padding |
| `material-trace` | `App.vue` 內的 "查詢結果" 區塊（Result Card `.card-body`） | 同上，`.card-body` 必須套用 `padding: 0` scoped override，DataTable 緊貼卡片邊緣 |

**參考實作**（正確模式）：`hold-detail/components/DistributionTable.vue`、`wip-detail/components/LotTable.vue`。

- 明細表的外層容器只允許一層 `<section class="card ui-card">`，其 `.card-body` 直接包含 `DataTable`（或原生 `<table>`），不得再嵌套一層 `<section class="card">` 或其他 wrapper 卡片元件。
- 表格的 column resize handle（`.col-resize-handle`）、tooltip teleport 等輔助元素不屬於「額外卡片包裝」，允許保留。
- 違反此規則的佈局稱為「表中表（table-within-table）」，屬 Forbidden Practice。

**material-consumption（2026-05-20）**: `frontend/src/material-consumption/style.css` 的全部 CSS 規則必須以 `.theme-material-consumption` 為父選擇器作用域；zero unscoped top-level rules permitted。由 `npm run css:check` Rule 6 強制執行；CI fails on any violation。

## Resource-Status UI Surface Rules

Added by `resource-status-package-group`.

| surface | component | rule |
|---|---|---|
| FilterBar | Package Group MultiSelect | Must be scoped under `.theme-resource`; uses shared `MultiSelect.vue`; prop/emit surface must be additive (do not change existing emit signatures). If the MultiSelect is inside a `.ui-card`, add a scoped modifier class and `overflow: visible` per Known Global Rule Interactions pattern. |
| EquipmentCard | PACKAGEGROUPNAME text row | Render only when `PACKAGEGROUPNAME !== null`. Must be scoped under `.theme-resource`. Use existing text-row pattern alongside WORKCENTERNAME / RESOURCEFAMILYNAME rows; no new CSS class required. |
| MatrixSection | Package expandable dimension | Must be scoped under `.theme-resource`. New dimension column follows the same CSS class pattern as existing expandable dimensions; no new authored class names required unless existing ones cannot cover the Package column. |

All new CSS rules (if any) added to `frontend/src/resource-status/style.css` must be scoped under `.theme-resource` and must pass `npm run css:check` Rule 6. No new `.css` source file is created by this change; `css-inventory.md` does not require an update.

## Known Global Rule Interactions

- **`.ui-card { overflow: hidden }` (defined in `frontend/src/styles/tailwind.css`) clips any `position: absolute` dropdown (MultiSelect, custom select) nested inside it.** When a card must contain such a dropdown, add a scoped modifier class to the card (e.g., `filter-query-card`, `type-filter-card`) and override `overflow: visible` in the feature's scoped `style.css` — never change the global rule. The pattern has been applied in 7+ feature CSS files and is established as the correct override contract. Evidence: `material-part-consumption` — filter panel MultiSelect clipped by `.ui-card { overflow: hidden }` until scoped override was added.

## Forbidden Practices

- 表中表（detail table 嵌套在額外卡片 wrapper 內）
- 硬編碼 token 值（顏色、間距）繞過 `tailwind.config.js`
- 功能區塊樣式洩漏至全域（缺少主題根類別作用域）
- 從外部 CSS 覆寫共用元件內部樣式（DataTable、SummaryCard、Chip、SectionCard、ErrorBanner）
- 未審查的 z-index 添加
- 多種 loading 表現並存於同一區塊
- **直接修改全域 `.ui-card` 的 overflow 屬性**：若需卡片內的彈出下拉，使用 scoped 修飾類別加上 `overflow: visible` override（見 Known Global Rule Interactions）

## Visual Review Policy

所有 UI 變更必須提供視覺佐證（截圖或 Playwright visual diff）。CSS contract drift 由 `spec-drift-auditor` 在每次 release 前檢查。

## CHANGELOG

## [css 1.4.0]
- resource-status-package-group (2026-05-21): Added "Resource-Status UI Surface Rules" section documenting FilterBar Package Group MultiSelect, EquipmentCard PACKAGEGROUPNAME text row (hide when null), and MatrixSection Package dimension scoping requirements. All rules enforce existing `.theme-resource` scope contract; no new CSS source file; css-inventory.md unchanged.

## [css 1.3.0]
- material-part-consumption (2026-05-20): Added "Known Global Rule Interactions" section documenting `.ui-card { overflow: hidden }` clipping behaviour and the scoped modifier class override pattern. Added corresponding Forbidden Practice entry prohibiting direct modification of the global `overflow` property. Evidence: filter panel MultiSelect dropdown was clipped until `.filter-query-card` scoped override was introduced.

## [css 1.2.1]
- material-part-consumption (2026-05-20): Added `.theme-material-consumption` scoping rule for `frontend/src/material-consumption/style.css`. Enforced by `npm run css:check` Rule 6; zero unscoped top-level rules permitted.
