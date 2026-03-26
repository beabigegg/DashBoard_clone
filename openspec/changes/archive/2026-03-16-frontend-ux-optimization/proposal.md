## Why

前端架構全面審查發現多項影響操作效率與可及性的 UX 問題：互動元素缺少鍵盤焦點環、無 `<main>` landmark 與 skip link、動畫缺少 reduced-motion 支援、圖表 resize 未統一節流、血緣樹大量節點時效能不佳（全展開 + 無縮放）、資料表格無欄位排序與分頁強化、篩選器在行動裝置上溢出。這些問題直接影響工廠操作人員的日常使用體驗，需系統性改善。

## What Changes

### Phase 1 — 無障礙基礎
- 全域 `:focus-visible` 焦點環（`ui-btn`、`drawer-link`、`multi-select-trigger`、pagination、matrix cell）
- Portal shell 加入 `<main>` landmark、`role="navigation"`、skip-to-content 連結
- 所有 feature CSS 加入 `@media (prefers-reduced-motion: reduce)` 覆蓋
- `text.muted` 色彩對比度修正（#94a3b8 → #64748b，達 WCAG AA 4.5:1）

### Phase 2 — 圖表體驗
- 所有 VChart 統一 `autoresize: { throttle: 100 }`
- 圖表外層加入 `role="img"` + `aria-label`
- Pareto Grid 互動強化（cursor:pointer、hover 高亮、tooltip 提示）

### Phase 3 — 血緣樹效能與互動
- `initialTreeDepth` 從 -1 改為 2，加入「全部展開」按鈕
- 啟用滾輪縮放（`roam: true`），加入「重置視圖」按鈕
- 關聯表從截斷 200 筆改為 PaginationControl 分頁
- PNG 匯出加入 LoadingOverlay 提示

### Phase 4 — 資料表格功能
- 新增 `useSortableTable` composable（支援 string/number/date 排序）
- 分頁元件強化：頁碼跳轉、page-size 選擇器、中文化
- 表格斑馬紋（`ui-table-wrap` 全域規則）
- WIP matrix overflow-x 修正

### Phase 5 — 篩選器與表單
- Hold overview 篩選面板 RWD 斷點（700px 以下單欄）
- MultiSelect loading spinner + SVG chevron 動畫
- 新增 ErrorBanner 元件（dismiss + retry slot）

### Phase 6 — 元件一致性整理（長期）
- Card / Loading / Error Banner CSS 統一至 shared-ui
- MultiSelect 樣式內聚至 `<style scoped>`
- `token.hXXXXXX` 逐步遷移至語義化 token

## Capabilities

### New Capabilities
- `accessibility-foundation`: 全域焦點環、landmark 語義、skip link、reduced-motion、色彩對比度 — 跨所有頁面的無障礙基礎設施
- `chart-interaction-hardening`: 圖表 autoresize 節流、ARIA 標籤、Pareto Grid 互動強化
- `lineage-tree-ux`: 血緣樹展開深度控制、縮放功能、關聯表分頁、匯出 loading 提示
- `table-sort-and-pagination`: 通用排序 composable、分頁元件強化（頁碼/page-size/中文化）、斑馬紋、overflow 修正
- `filter-form-polish`: 篩選面板 RWD、MultiSelect loading/chevron 動畫、ErrorBanner 元件
- `component-style-unification`: Card/Loading/ErrorBanner/MultiSelect 樣式統一、token 遷移

### Modified Capabilities
- `tailwind-design-system`: `text.muted` 色值調整、`ui-table-wrap` 斑馬紋規則、全域 focus-visible 規則
- `spa-shell-navigation`: portal-shell `<main>` landmark + skip link
- `unified-multiselect`: loading spinner、SVG chevron 動畫、樣式內聚至 scoped

## Impact

**前端檔案（主要）：**
- `frontend/src/styles/tailwind.css` — focus ring、斑馬紋（全域 @layer components）
- `frontend/tailwind.config.js` — `text.muted` 色值
- `frontend/src/portal-shell/App.vue` — landmark/skip link
- `frontend/src/query-tool/components/LineageTreeChart.vue` — 展開/縮放/分頁/匯出
- `frontend/src/shared-ui/components/` — PaginationControl、MultiSelect、ErrorBanner（新增）
- `frontend/src/shared-composables/useSortableTable.js`（新增）
- 所有 feature `style.css` — reduced-motion 覆蓋
- `frontend/src/wip-overview/style.css` — overflow 修正
- `frontend/src/hold-overview/style.css` — 篩選面板 RWD
- `frontend/src/reject-history/` — Pareto 互動強化
- 約 15 個 Chart 元件 — autoresize throttle + ARIA

**契約檔案：**
- `contract/css_inventory.md` — ErrorBanner.vue scoped style 登錄

**無後端 API 變更。無 breaking change。**
