## Why

MES Dashboard 已完成 SPA shell 遷移與核心元件庫建立，但前端仍存在顯著的視覺不一致：多個 feature 各自實作 table、filter、card、summary 等 UI 模式，導致相同語意的 UI 在不同頁面呈現不同的字級、間距、陰影與互動回饋。shared-ui 元件採用率仍不足（多數 feature 仍用自建 markup），且缺乏統一的 DataTable、SummaryCard、Icon 系統。現在是統一的最佳時機——所有 in-scope native route（共 19 條）已遷入 shell，Tailwind design token 已建立，可在不破壞主色系（brand blue `#0080C8` gradient + surface/state tokens）的前提下進行系統性的 UI 現代化。

## What Changes

### Design Token 層
- 擴展 `tailwind.config.js`：新增 `brand.400`/`brand.900`、半透明色彩變體、5 級 shadow 系統（`xs`→`xl`）、`pill`/`button` border-radius tokens
- 引入 `Inter` 作為 Latin/數字字體，與 Noto Sans TC 配對，提升數據閱讀體驗
- 新增 page transition motion tokens（`--motion-page-enter`, `--motion-stagger`）

### 核心元件新增
- **DataTable** — 統一 sortable headers、pagination、loading overlay、empty state、zebra striping、sticky header；取代各 feature 自建 table markup
- **SummaryCard** — 統一 KPI 卡片：label/value/trend indicator/colored top-border/hover lift；取代各 feature 自建 summary cards
- **Chip** — 統一 filter chips 與 status tags
- **PageTransition** — 在 `NativeRouteView` 對已解析頁面元件加入 fade-up transition wrapper（保留 shell host `App.vue` 的直出 `<RouterView />`）

### 現有元件升級
- **SectionCard** — 新增 `variant` prop（`default`/`elevated`/`outlined`）、可折疊功能
- **PageHeader** — 新增 subtitle slot、backdrop-blur 效果、漸層微調
- **FilterToolbar** — 支援 chip 模式顯示已選 filter、collapsible 展開
- **EmptyState** — 新增 illustration slot、action button slot
- **StatusBadge** — 新增 `info` tone variant

### Shell 視覺升級
- Header 加入 `backdrop-filter: blur`、底部半透明邊框
- Sidebar active link 左側 accent bar（3px brand.500）、drawer 展開動畫
- Content area page enter transition（fade-up 200ms）
- Breadcrumb 升級為可點擊麵包屑 + chevron separator

### Feature Pages 統一（6 批次漸進）
- Batch 1: wip-overview, hold-overview, resource-status — 替換為 DataTable + SummaryCard + FilterToolbar
- Batch 2: hold-detail, wip-detail, reject-history — 統一 detail table 與 filter
- Batch 3: resource-history, hold-history, qc-gate — 統一 timeline/history 呈現
- Batch 4: query-tool, material-trace, yield-alert-center — 複雜互動頁面微調
- Batch 5: job-query, tables, excel-query, mid-section-defect — 補齊現行 in-scope route 的統一改造
- Batch 6: admin-dashboard, anomaly-overview, production-history — 管理/分析頁面統一（`/admin/performance` 已 deprecated，不列入改造）

### In-scope 路由覆蓋矩陣（apply baseline）
- Batch 1: `/wip-overview`, `/hold-overview`, `/resource`
- Batch 2: `/hold-detail`, `/wip-detail`, `/reject-history`
- Batch 3: `/resource-history`, `/hold-history`, `/qc-gate`
- Batch 4: `/query-tool`, `/material-trace`, `/yield-alert-center`
- Batch 5: `/job-query`, `/tables`, `/excel-query`, `/mid-section-defect`
- Batch 6: `/admin/dashboard`, `/anomaly-overview`, `/production-history`
- External governed target（不改造 UI）: `/admin/pages`
- Deprecated direct-entry（僅驗證 redirect）: `/admin/performance`, `/admin/user-usage-kpi`

### CSS 瘦身
- 合併重複 card styles（`.ui-card` + `.section-card` → `SectionCard` variants）
- 合併重複 banner styles → `ErrorBanner.vue` + shared warning-banner 樣式規範
- Feature CSS 中與 shared-ui 重複的樣式逐步移除
- 同步 `contract/css_inventory.md`

## Capabilities

### New Capabilities
- `data-table-component`: 統一可排序、可分頁、含 loading/empty state 的 DataTable 元件
- `summary-card-component`: 統一 KPI 摘要卡片元件（label/value/trend/colored border）
- `chip-component`: 統一 filter chip 與 status tag 元件
- `page-transition-system`: NativeRouteView 元件層頁面切換 transition + content fade-in
- `shell-visual-refresh`: Portal shell header/sidebar/breadcrumb 視覺現代化
- `design-token-expansion`: Tailwind token 擴展（shadow 5 級、border-radius、Latin 字體、半透明色彩）
- `feature-page-unification`: 6 批次漸進式 feature page UI 統一改造（覆蓋 19 條 in-scope native route）

### Modified Capabilities
- `component-style-unification`: SectionCard 新增 variant/collapse 功能，擴大 card 合併範圍
- `tailwind-design-system`: 擴展 shadow/radius/font/color tokens
- `unified-button-system`: 與新 Chip 元件整合，確保按鈕/chip 視覺一致
- `empty-state`: 新增 illustration slot 與 action button slot
- `frontend-motion-system`: 新增 page transition 與 stagger animation tokens
- `filter-form-polish`: FilterToolbar chip 模式與 collapsible 升級
- `loading-system`: DataTable 內建 loading overlay 整合
- `table-sort-and-pagination`: DataTable 元件封裝 useSortableTable + PaginationControl
- `search-trigger-animation`: DataTable 原生支援 fetch loading dimming

## Impact

### Frontend Code
- `frontend/tailwind.config.js` — token 擴展
- `frontend/src/styles/tailwind.css` — 新增 CSS variables 與 component classes
- `frontend/src/shared-ui/components/` — 新增 4 元件 + 升級 5 元件
- `frontend/src/portal-shell/App.vue`, `style.css` — shell 視覺升級
- `frontend/src/portal-shell/views/NativeRouteView.vue` — page transition 包裹
- 19 條 in-scope native route 對應 feature 目錄的 `App.vue` + `style.css` — 漸進式元件替換
- `frontend/src/resource-shared/styles.css` — 被元件化後的樣式清理
- `frontend/src/wip-shared/styles.css` — 同上

### Contracts
- `contract/css_inventory.md` — 新增/移除 CSS 來源
- `contract/css_development_contract.md` — 新增 DataTable/SummaryCard/Chip 與 shared warning-banner 的 styling 指引

### Dependencies
- **Lucide Vue Next** (`lucide-vue-next`) — 輕量 tree-shakeable icon library，取代散落的 inline SVG
- **@vueuse/core** — 常用 composables（`useResizeObserver`, `useIntersectionObserver`, `onClickOutside` 等），減少自建 utility
- **Inter font** — 透過 local woff2 引入，作為 Latin/數字字體

### Risk
- Feature page 批次改造需逐頁驗證功能不 regression
- DataTable 需覆蓋現有所有 table 的 sorting/pagination 行為
- Shell 視覺變更影響全部頁面，需整體驗收

## Apply Readiness (Definition of Done)

- `shared-ui/components` 新增 `DataTable`, `DataTableColumn`, `SummaryCard`, `SummaryCardGroup`, `Chip` 並完成既有元件升級
- `tailwind.config.js` 與 `styles/tailwind.css` 完成 token/motion/font 擴展，且新樣式只透過 token 消費
- 19 條 in-scope native routes 均完成 batch 指派並完成對應替換，無遺漏頁面
- `portal-shell` page transition 僅在 `NativeRouteView` 元件層實作，`App.vue` 維持直出 `<RouterView />`
- `admin/performance`、`admin/user-usage-kpi` direct-entry redirect 行為驗證通過
- `contract/css_inventory.md` 與 `contract/css_development_contract.md` 完成同步更新
- Visual smoke test（6 個 batches + shell 全域）完成，無阻斷性 regression
