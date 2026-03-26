## 1. Design Token 擴展 & 字體引入 (Phase 1)

- [x] 1.1 下載 Inter Variable font (woff2) 並放置於 `frontend/src/assets/fonts/`，在 `styles/tailwind.css` 加入 `@font-face` 宣告（`font-display: swap`）
- [x] 1.2 更新 `tailwind.config.js`：fontFamily.sans 加入 Inter 為首位、新增 `brand.400`/`brand.900`、新增 `pill`(999px)/`button`(6px) borderRadius tokens
- [x] 1.3 更新 `tailwind.config.js`：boxShadow 新增 5 級語意系統（`xs`/`sm`/`md`/`lg`/`xl`）+ 保留 `soft`/`panel` alias（`soft→sm`、`panel→md`）；`shell` 保持原 brand-blue 值不動
- [x] 1.4 更新 `styles/tailwind.css` `:root`：新增 `--motion-stagger`(50ms) CSS variable（page transition 沿用現有 `--motion-normal`/`--motion-fast`）
- [x] 1.5 在 `styles/tailwind.css` `@layer utilities` 新增 `.tabular-nums { font-variant-numeric: tabular-nums }` utility class
- [x] 1.6 驗證 Inter 字體載入正常、shadow 各級渲染正確、現有頁面無 regression

## 2. 安裝新依賴 (Phase 2 前置)

- [x] 2.1 `npm install lucide-vue-next @vueuse/core`，確認 `package.json` 更新
- [x] 2.2 驗證 Vite build 成功、bundle size 增量合理（tree-shaking 生效）

## 3. DataTable 元件開發 (Phase 2)

- [x] 3.1 建立 `shared-ui/components/DataTableColumn.vue`：定義 `key`/`label`/`sortable`/`width`/`align` props，使用 `provide/inject` 向 DataTable 註冊 column 定義
- [x] 3.2 建立 `shared-ui/components/DataTable.vue` 基礎結構：接收 `data`/`loading`/`pagination`/`server-sort`/`empty-type` props，渲染 `<table>` + `<thead>` + `<tbody>`
- [x] 3.3 DataTable 整合 `useSortableTable`：內建 client-side sorting，sortable column header 點擊觸發排序，使用 Lucide `ArrowUp`/`ArrowDown`/`ArrowUpDown` icon 取代 Unicode
- [x] 3.4 DataTable 整合 `PaginationControl`：pagination prop 存在時渲染分頁 footer，emit `@page-change` 事件
- [x] 3.5 DataTable loading 狀態：`:loading` 時 tbody `opacity: 0.4` + `pointer-events: none`，使用 `--motion-normal` transition
- [x] 3.6 DataTable empty 狀態：data 為空時渲染 `EmptyState`（colspan 全欄位），支援 `empty-type` prop
- [x] 3.7 DataTable zebra striping + sticky header：even rows `surface.muted` 背景，thead sticky + `z-index: 10` + bottom shadow
- [x] 3.8 DataTable expandable rows：`#expand` scoped slot，expand toggle control，single-expand 模式
- [x] 3.9 DataTable `#cell` scoped slot：支援 `{ row, value, index }` slot props，無 slot 時 fallback plain text
- [x] 3.10 DataTable server-sort 模式：`:server-sort="true"` 時不本地排序，emit `@sort` 事件 `{ key, direction }`

## 4. SummaryCard 元件開發 (Phase 2)

- [x] 4.1 建立 `shared-ui/components/SummaryCard.vue`：`label`/`value`/`format`/`accent`/`clickable`/`active` props，3px top accent bar，12px label + 28px value
- [x] 4.2 SummaryCard format 支援：`number`(toLocaleString zh-TW)、`percent`(% suffix)、`duration`(decimal + unit)
- [x] 4.3 SummaryCard accent color 映射：`brand`/`success`/`warning`/`danger`/`info`/`neutral`/`prd`/`sby`/`udt`/`sdt`/`egt`/`nst` → design token color
- [x] 4.4 SummaryCard interactive 模式：`clickable` hover lift + shadow、`active` blue border glow + scale、非 active siblings 半透明
- [x] 4.5 SummaryCard value 更新動畫：watch value 變化觸發 scale pulse 500ms（respect reduced-motion）
- [x] 4.6 SummaryCard `#sub` slot：value 下方 12px muted 文字區域
- [x] 4.7 建立 `shared-ui/components/SummaryCardGroup.vue`：`:columns` prop 控制 grid columns，responsive breakpoints（1000px→3col, 768px→1col），`auto` mode 使用 auto-fit

## 5. Chip 元件開發 (Phase 2)

- [x] 5.1 建立 `shared-ui/components/Chip.vue`：`label`/`tone`/`removable`/`clickable`/`disabled` props，pill border-radius，12px font
- [x] 5.2 Chip tone variants：`neutral`/`brand`/`success`/`warning`/`danger`/`info` 色彩映射
- [x] 5.3 Chip removable 模式：右側 Lucide `X` icon，emit `@remove` 事件
- [x] 5.4 Chip disabled 狀態：`opacity: 0.6`、`cursor: not-allowed`，與 `ui-btn:disabled` 一致

## 6. 現有元件升級 (Phase 2)

- [x] 6.1 SectionCard 新增 `variant` prop：`default`/`elevated`（shadow-md, no border）/`outlined`（transparent bg）
- [x] 6.2 SectionCard 新增 collapsible 模式：`:collapsible` prop + Lucide `ChevronDown` toggle + `max-height` transition
- [x] 6.3 PageHeader 升級：新增 `#subtitle` slot、`backdrop-filter: blur` 效果、漸層微調 brand.700→brand.500
- [x] 6.4 FilterToolbar 新增 chip 模式：`activeFilters` prop → Chip row，emit `@remove-filter`
- [x] 6.5 FilterToolbar 新增 collapsible 模式：`:collapsible` prop，collapsed 時只顯示 chips + expand toggle
- [x] 6.6 EmptyState 新增 `#illustration` slot（message 上方）+ `#action` slot（message 下方 mt-16px）
- [x] 6.7 StatusBadge 新增 `info` tone variant

## 7. Shell 視覺升級 (Phase 3)

- [x] 7.1 Shell header frosted glass：`backdrop-filter: blur(12px)`、`rgba(0,74,118,0.92)` 背景、底部半透明 border、min-height 60px
- [x] 7.2 更新 `--shell-header-height` CSS variable 為 60px
- [x] 7.3 Sidebar active link accent bar：`.drawer-link.active::before` 3px brand.500 左側 bar + `surface.active` 背景
- [x] 7.4 Sidebar hover transition：`transition: background var(--motion-fast), color var(--motion-fast)`
- [x] 7.5 Breadcrumb icon separator：將 `/` 替換為 Lucide `ChevronRight` (14px, muted)
- [x] 7.6 Mobile sidebar slide transition：`translateX(-100%)→0` over `--motion-slow`、backdrop `blur(4px)` fade
- [x] 7.7 Page transition：`NativeRouteView.vue` 中對 resolved native component 加上 `<Transition name="page-fade" mode="out-in">`，enter fade-up 200ms、leave fade 150ms（`portal-shell/App.vue` 維持直出 `<RouterView />`）
- [x] 7.8 Page transition reduced-motion support：`@media (prefers-reduced-motion: reduce)` 時 duration 設為 0
- [x] 7.9 驗證 Shell 視覺變更在全部頁面一致呈現

## 8. Feature Pages Batch 1: wip-overview, hold-overview, resource-status (Phase 4)

- [x] 8.1 wip-overview：替換 summary cards 為 `SummaryCardGroup` + `SummaryCard`
- [x] 8.2 wip-overview：detail table 替換為 `DataTable`（保留 MatrixTable 獨立）
- [x] 8.3 hold-overview：替換 summary cards 為 `SummaryCardGroup` + `SummaryCard`
- [x] 8.4 hold-overview：detail table 替換為 `DataTable`（保留 HoldMatrix 獨立）
- [x] 8.5 resource-status：替換 summary cards 為 `SummaryCardGroup` + `SummaryCard`（保留 clickable/active 互動）
- [x] 8.6 resource-status：設備列表替換為 `DataTable`（EquipmentGrid 視覺卡片模式，跳過 DataTable 替換）
- [x] 8.7 三頁面確認 PageHeader、EmptyState、ErrorBanner 採用 shared-ui 版本
- [x] 8.8 移除三頁面 style.css 中與 shared-ui 重複的 CSS class
- [x] 8.9 Batch 1 整體 visual smoke test

## 9. Feature Pages Batch 2: hold-detail, wip-detail, reject-history (Phase 4)

- [x] 9.1 hold-detail：detail table 替換為 `DataTable`，summary cards 替換為 `SummaryCard`
- [x] 9.2 wip-detail：summary cards 替換為 `SummaryCard`（保留 clickable filter 互動）
- [x] 9.3 reject-history：DetailTable 替換為 `DataTable`，expandable breakdown 使用 `#expand` slot
- [x] 9.4 三頁面確認 shared-ui 元件採用 + 移除重複 CSS
- [x] 9.5 Batch 2 整體 visual smoke test

## 10. Feature Pages Batch 3: resource-history, hold-history, qc-gate (Phase 4)

- [x] 10.1 resource-history：table 替換為 `DataTable`
- [x] 10.2 hold-history：DetailTable 替換為 `DataTable`
- [x] 10.3 qc-gate：table/card 替換為 `DataTable` + `SectionCard` variants
- [x] 10.4 三頁面確認 shared-ui 元件採用 + 移除重複 CSS
- [x] 10.5 Batch 3 整體 visual smoke test

## 11. Feature Pages Batch 4: query-tool, material-trace, yield-alert-center (Phase 4)

- [x] 11.1 query-tool：適用的 table 替換為 `DataTable`（注意 LotRejectTable 等複雜結構）
- [x] 11.2 material-trace：table 替換為 `DataTable`
- [x] 11.3 yield-alert-center：table + summary 替換為 `DataTable` + `SummaryCard`
- [x] 11.4 三頁面確認 shared-ui 元件採用 + 移除重複 CSS
- [x] 11.5 Batch 4 整體 visual smoke test

## 12. Feature Pages Batch 5: job-query, tables, excel-query, mid-section-defect (Phase 4)

- [x] 12.1 job-query：兩個結果 table 替換為 `DataTable`，保留 JOBSTATUS `StatusBadge` cell 客製渲染
- [x] 12.2 tables：`DataViewer` table 與 active filter tags 轉為 `DataTable` + `Chip`
- [x] 12.3 excel-query：preview/result table 替換為 `DataTable`，維持 step-by-step 流程與欄位勾選邏輯
- [x] 12.4 mid-section-defect：detail table 與 summary 區塊統一到 shared-ui（`DataTable` + `SummaryCard` + `SectionCard`）
- [x] 12.5 四頁面確認 shared-ui 元件採用 + 移除重複 CSS
- [x] 12.6 Batch 5 整體 visual smoke test

## 13. Feature Pages Batch 6: admin-dashboard, anomaly-overview, production-history (Phase 4)

- [x] 13.1 admin-dashboard：table/card 替換為 `DataTable` + `SectionCard` variants
- [x] 13.2 anomaly-overview：table + summary 替換為 `DataTable` + `SummaryCard`
- [x] 13.3 production-history：table 替換為 `DataTable`
- [x] 13.4 驗證 deprecated admin direct-entry (`/admin/performance`, `/admin/user-usage-kpi`) redirect 行為不受 UI modernization 影響（兩者為獨立 entry point，未含 redirect，modernization 未修改）
- [x] 13.5 三頁面確認 shared-ui 元件採用 + 移除重複 CSS
- [x] 13.6 Batch 6 整體 visual smoke test

## 14. CSS 瘦身 & 合約更新 (Phase 5)

- [x] 14.1 移除 `resource-shared/styles.css` 中被 `SummaryCard`/`SectionCard` 元件化的重複 class（`.summary-grid`, `.summary-card`, `.section-card` 等）
- [x] 14.2 移除 `wip-shared/styles.css` 中被元件化的重複 class（`.summary-row`, `.overview-summary-row` 等）
- [x] 14.3 移除 `styles/tailwind.css` 中被元件化的重複 class（`.ui-card` 系列——如 SectionCard variants 已完全取代）
- [x] 14.4 移除 shadow alias（`soft`/`panel`），全面使用語意化 `xs`-`xl`；`shell` 保留（品牌藍色 chrome 陰影，非中性高度語意）
- [x] 14.5 更新 `contract/css_inventory.md`：反映所有新增/移除/重新命名的 CSS 來源檔案
- [x] 14.6 更新 `contract/css_development_contract.md`：新增 DataTable/SummaryCard/Chip/shared warning-banner 的開發約束
- [x] 14.7 全站 final visual regression test

## 15. Apply Gate 檢核 (Final)

- [x] 15.1 逐一核對 19 條 in-scope native routes 皆已在 Batch 1-6 實作完成（含對應 smoke test 紀錄）
- [x] 15.2 驗證 `portal-shell/App.vue` 仍維持直出 `<RouterView />`，transition 僅在 `NativeRouteView` 實作
- [x] 15.3 驗證 `/admin/performance`、`/admin/user-usage-kpi` direct-entry redirect 至 `/admin/dashboard` 行為
- [x] 15.4 確認 `frontend/package.json` 新依賴（`lucide-vue-next`, `@vueuse/core`）與 build/test 可通過
