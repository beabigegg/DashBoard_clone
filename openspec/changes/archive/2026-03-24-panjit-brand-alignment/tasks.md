# Tasks: panjit-brand-alignment

## Phase 1: 品牌基礎對齊（高優先級）

- [x] 1.1 修改 `frontend/tailwind.config.js` 品牌色彩
  - `brand.50`: `#eef2ff` → `#e6f4fb`
  - `brand.100`: `#e0e7ff` → `#b3dbf2`
  - `brand.500`: `#667eea` → `#0080C8`
  - `brand.600`: `#5a67d8` → `#006BA8`
  - `brand.700`: `#4c51bf` → `#005A8F`
  - `brand.800`: `#4338ca` → `#004A76`
  - `accent.500`: `#764ba2` → `#00A3E0`
  - `surface.active`: `#eef2ff` → `#e6f4fb`
  - `boxShadow.shell`: `rgba(102, 126, 234, 0.3)` → `rgba(0, 128, 200, 0.25)`
  - 移除 `token.h667eea` 和 `token.h764ba2`（已被 brand/accent 取代）

- [x] 1.2 修改 `frontend/tailwind.config.js` 排版層級
  - 擴展 `fontSize` 定義：`xs`(12px), `sm`(13px), `base`(14px), `lg`(16px), `xl`(20px), `2xl`(24px)

- [x] 1.3 更新 `frontend/src/styles/tailwind.css` 的 `:root` CSS 變數
  - `--portal-brand-start`: 改為 `theme('colors.brand.500')`
  - `--portal-brand-end`: 改為 `theme('colors.accent.500')`

- [x] 1.4 更新 `frontend/src/styles/tailwind.css` 的 `.ui-page-header`
  - 漸層改為 `linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%)`
  - box-shadow 自動跟隨 `boxShadow.shell` 更新

- [x] 1.5 更新 `frontend/src/styles/tailwind.css` 的 `.ui-btn--primary`
  - 改為純色 `background: theme('colors.brand.500')`
  - hover 改為 `background: theme('colors.brand.600')` + `box-shadow: 0 4px 12px rgba(0, 128, 200, 0.35)`

- [x] 1.6 更新 `frontend/src/portal-shell/style.css` 的 `.shell-header`
  - 漸層改為 `linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%)`
  - 字體順序改為 `"Noto Sans TC", "Microsoft JhengHei"` 與 tailwind.config.js 一致

- [x] 1.7 更新 `frontend/src/portal-shell/views/LoginPage.vue` 品牌色
  - 光球漸層：brand/accent 引用已自動變，需視覺驗證
  - 登入按鈕漸層改為單色系或深藍→品牌藍

- [x] 1.8 更新其他引用 `brand.500 → accent.500` 漸層的 feature CSS
  - `wip-shared/styles.css:42` — header-gradient
  - `wip-detail/style.css:300` — header gradient
  - `material-trace/style.css:2` — header gradient
  - `mid-section-defect/style.css:28` — header gradient
  - `tables/style.css:29` — header gradient
  - `resource-shared/styles.css:51` — header-gradient（覆蓋 7 個 theme 作用域）
  - `resource-history/style.css:2` — history-header
  - `hold-history/style.css:2` — hold-history-header
  - `yield-alert-center/style.css:34` — ya-header
  - `reject-history/style.css:2` — reject-history-header
  - 全部改為 `brand.800 → brand.500` 單色系漸層
  - 註：`excel-query`、`job-query`、`qc-gate` 使用 CSS var 回退機制，透過 Task 1.3 的 `:root` 更新自動生效

- [x] 1.9 更新 `shared-ui/components/AiChartRenderer.vue` CHART_PALETTE
  - `bar: '#5a67d8'` → `'#0080C8'`（brand.500）
  - `barSecondary: '#667eea'` → `'#00A3E0'`（accent.500）
  - `line: '#4c51bf'` → `'#006BA8'`（brand.600）
  - `lineSecondary: '#8b83f8'` → `'#00A3E0'`（accent.500）
  - `heatmapMin: '#eef2ff'` → `'#e6f4fb'`（brand.50）
  - `heatmapMax: '#4c51bf'` → `'#004A76'`（brand.800）
  - （圖表例外：CSS 契約 6.3 允許在圖表設定中保留 HEX）

- [x] 1.10 修正硬編碼 `rgba(102, 126, 234, ...)` 為 `rgba(0, 128, 200, ...)`
  - `wip-shared/styles.css:18,250` — shadow-strong + keyframe background
  - `wip-detail/style.css:277` — active background
  - `query-tool/style.css:221,245,267` — focus ring box-shadow
  - `hold-overview/style.css:176` — focus ring box-shadow
  - `qc-gate/style.css:18` — shadow-strong
  - `yield-alert-center/style.css:13,154` — shadow-strong + focus ring

- [x] 1.11 遷移紫色系 hex token 引用至語意 brand token
  - `token.heef2ff` → `brand.50`：portal-shell(217,266), anomaly-overview(230,268), query-tool(139,202), job-query(108)
  - `token.h4338ca` → `brand.800`：portal-shell(218,267,445), anomaly-overview(309), LineageTreeChart.vue(1067)
  - `token.h4c51bf` → `brand.700`：query-tool(140,203)
  - `token.hc7d2fe` → `brand.100`：portal-shell(268), hold-overview(268,273), qc-gate(125), LineageTreeChart.vue(1061)
  - `token.h6366f1` → `brand.500`：job-query(107)
  - `token.h1e3a8a` → `brand.800`：hold-overview(274)
  - `qc-gate/style.css:126` rgba(99,102,241) → rgba(0,128,200)

- [x] 1.12 Vite dev build 驗證 — 確認無編譯錯誤，品牌色全面生效

## Phase 2: 按鈕系統統一（中優先級）

- [x] 2.1 在 `styles/tailwind.css` `@layer components` 新增按鈕變體
  - `ui-btn--secondary`: `brand.50` 底 + `brand.600` 字 + `brand.500` 邊框
  - `ui-btn--danger`: `state.danger` 底 + 白字 + `state.danger` hover 深色

- [x] 2.2 清除 `portal-shell/style.css` 的 `.btn-link`（第 305 行）
  - 註：原提案誤標為 `.btn-primary`，實際為 `.btn-link`；該檔案不存在 `.btn-primary`

- [x] 2.3 清除 `query-tool/style.css` 的 `.btn`, `.btn-primary`, `.btn-export`（第 71-112 行）
  - 同步更新 `query-tool/components/QueryBar.vue`, `ExportButton.vue`, `EquipmentView.vue` 的 class

- [x] 2.4 清除 `admin-dashboard/style.css` 的 `.btn`（第 80-99 行, 第 548 行）
  - 同步更新 `admin-dashboard/App.vue` 及 tabs 元件的 class

- [x] 2.5 清除 `admin-performance/style.css` 的 `.btn`（第 51-70 行, 第 390 行）
  - 同步更新 `admin-performance/App.vue` 的 class

- [x] 2.6 清除 `admin-user-usage-kpi/style.css` 的 `.btn`（第 63-82 行）
  - 同步更新 `admin-user-usage-kpi/App.vue` 的 class

- [x] 2.7 清除 `material-trace/style.css` 的 `.btn-export`（第 289-299 行）
  - 同步更新 `material-trace/App.vue` 的 class

- [x] 2.8 Vite build 驗證 — 確認所有按鈕樣式正常，無 class 遺漏

## Phase 3: 表格現代化（中優先級）

- [x] 3.1 修改 `resource-shared/styles.css` 的 `.matrix-table` 系列
  - 移除全邊框，改為 `td { border-bottom }` 行分隔線
  - 表頭改為 `brand.50` 淺藍底 + `border-bottom: 2px`
  - 加入 `position: sticky; top: 0` 到 `th`
  - 保持 `.theme-resource*` 作用域

- [x] 3.2 修改 `wip-shared/styles.css` 的表格系列
  - 同 3.1 的樣式變更
  - 保持 `:is(.theme-wip-*, ...)` 作用域

- [x] 3.3 檢查其他含 `.matrix-table` 的 route-local CSS（4 個 CSS 檔案 + 3 個 Vue 檔案）
  - 註：原提案誤計為 19 個檔案，實際 matrix-table 定義在 4 個 CSS 檔案
  - `hold-overview/style.css` 和 `wip-overview/style.css` 有 route-local 覆蓋，已同步調整
  - 其餘透過 shared layer 自動繼承

- [ ] 3.4 視覺驗證 — 確認資料密集表格的可讀性

## Phase 4: Skeleton Loading（中優先級）

- [x] 4.1 建立 `frontend/src/shared-ui/components/SkeletonLoader.vue`
  - Props: `type` (`text`|`card`|`table`), `rows` (number)
  - `<style scoped>` 含 shimmer 動畫
  - 尊重 `prefers-reduced-motion`

- [x] 4.2 更新 `contract/css_inventory.md`
  - 在 Shared UI Component Styles 表格新增 `SkeletonLoader.vue` 條目

- [x] 4.3 在 1-2 個頁面整合 SkeletonLoader 作為示範
  - 建議：`hold-overview/App.vue` 或 `resource-status/App.vue`

## Phase 5: 收尾驗證

- [x] 5.1 執行 `frontend/scripts/css-governance-check.js` — 確認 0 errors
- [x] 5.2 完整 Vite production build — 確認無錯誤
- [ ] 5.3 視覺走查 — 逐頁確認品牌色、按鈕、表格、載入狀態
  - 重點頁面：LoginPage, portal-shell header, hold-overview, resource-status, query-tool, wip-overview
