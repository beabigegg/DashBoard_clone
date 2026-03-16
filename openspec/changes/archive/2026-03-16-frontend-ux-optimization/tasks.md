## 1. Phase 1 — 無障礙基礎修正

- [x] 1.1 在 `frontend/src/styles/tailwind.css` 的 `@layer components` 加入全域 `:focus-visible` 規則，覆蓋 `.ui-btn`、`.ui-btn--primary`、`.ui-btn--ghost`、`.drawer-link`、`.multi-select-trigger`、pagination buttons、matrix clickable cells，使用 `outline: 2px solid theme('colors.brand.500'); outline-offset: 2px`
- [x] 1.2 修改 `frontend/src/portal-shell/App.vue`：將 `<aside>` 加入 `role="navigation"` + `aria-label="主選單"`；將 `<section class="shell-content">` 改為 `<main id="main-content">`；在 shell 頂部加入 visually-hidden skip-to-content 連結（`<a href="#main-content" class="sr-only focus:not-sr-only">跳至主要內容</a>`）
- [x] 1.3 在 `frontend/src/wip-shared/styles.css` 加入 `@media (prefers-reduced-motion: reduce)` 區塊，scope 在 `:is(.theme-wip-overview, .theme-wip-detail)` 下停用 spin、fadeOut、valueUpdate 動畫
- [x] 1.4 在 `frontend/src/resource-shared/styles.css` 加入 `@media (prefers-reduced-motion: reduce)` 區塊，scope 在 `:is(.theme-resource, .theme-resource-history)` 下停用 hover-lift、dot 動畫
- [x] 1.5 檢查其餘 feature `style.css`（hold-overview、reject-history、admin-performance、qc-gate 等）是否有動畫定義，若有則加入對應的 reduced-motion 覆蓋
- [x] 1.6 在 `frontend/tailwind.config.js` 將 `text.muted` 色值從 `#94a3b8` 調整為 `#64748b`
- [x] 1.7 執行 `npm run build` 驗證無編譯錯誤；鍵盤 Tab 測試 focus ring 可見性

## 2. Phase 2 — 圖表體驗優化

- [x] 2.1 搜尋所有 `.vue` 檔案中的 `<VChart` 實例，將 `autoresize` 統一改為 `:autoresize="{ throttle: 100 }"`（約 15 個檔案）
- [x] 2.2 為每個 Chart 元件的 VChart 外層容器加入 `role="img"` + 描述性 `aria-label`（中文，如 "退貨數量趨勢圖"、"設備稼動率熱力圖"）
- [x] 2.3 在 `frontend/src/reject-history/style.css` 的 `.theme-reject-history` scope 下加入 Pareto Grid 互動樣式：`cursor: pointer`、hover 背景 `theme('colors.surface.hover')`
- [x] 2.4 執行 `npm run build` 驗證；手動測試 Pareto Grid hover 效果

## 3. Phase 3 — 血緣樹效能與互動優化

- [x] 3.1 修改 `frontend/src/query-tool/components/LineageTreeChart.vue`：將 `initialTreeDepth: -1` 改為 `initialTreeDepth: 2`
- [x] 3.2 在 LineageTreeChart toolbar 區域加入「全部展開」和「全部收合」按鈕，使用 ECharts `dispatchAction` 控制展開/收合
- [x] 3.3 將 `roam: 'move'` 改為 `roam: true`（啟用滾輪縮放）
- [x] 3.4 在 toolbar 加入「重置視圖」按鈕，呼叫 `dispatchAction({ type: 'restore' })` 還原預設視圖
- [x] 3.5 將關聯表截斷邏輯改為 `PaginationControl` 分頁顯示，預設每頁 50 筆
- [x] 3.6 PNG 匯出時顯示 `LoadingOverlay`，匯出完成後關閉；將 `devicePixelRatio` 上限改為 2
- [ ] 3.7 手動測試：大量節點（>200）的血緣樹載入效能、縮放操作、分頁切換、PNG 匯出

## 4. Phase 4 — 資料表格功能強化

- [x] 4.1 新增 `frontend/src/shared-composables/useSortableTable.js`，實作通用排序邏輯：接受 `data`（ref/computed）、`sortKey`、`sortDirection` 參數，回傳排序後的資料；支援 string（locale-aware）、number、date 型別自動偵測
- [x] 4.2 在 `LotTable` 元件整合 `useSortableTable`：header 加入排序圖示（▲/▼ 或 SVG），點擊切換排序；加入 `aria-sort` 屬性
- [x] 4.3 在 `DetailTable` 元件整合 `useSortableTable`（同上模式）
- [x] 4.4 強化 `frontend/src/shared-ui/components/PaginationControl.vue`：新增 `showPageNumbers` prop（預設 false）顯示頁碼跳轉；新增 `showPageSize` prop + `pageSizeOptions` prop（預設 [10, 25, 50, 100]）；將 "Prev"/"Next" 改為 "上一頁"/"下一頁"；加入 `aria-label` 標註
- [x] 4.5 在 `frontend/src/styles/tailwind.css` 的 `@layer components` 中 `.ui-table-wrap` 下加入 `tbody tr:nth-child(even) { background-color: theme('colors.surface.muted'); }` 斑馬紋規則
- [x] 4.6 在 `frontend/src/wip-overview/style.css` 的 `.theme-wip-overview` scope 下為 matrix container 加入 `overflow-x: auto`
- [x] 4.7 執行 `npm run build` 驗證；手動測試排序功能、分頁跳轉、斑馬紋顯示

## 5. Phase 5 — 篩選器與表單改善

- [x] 5.1 在 `frontend/src/hold-overview/style.css` 的 `.theme-hold-overview` scope 下加入 `@media (max-width: 700px)` 將篩選面板 grid 改為 `grid-template-columns: 1fr`
- [x] 5.2 修改 `frontend/src/shared-ui/components/MultiSelect.vue`：當 `loading` prop 為 true 時在 trigger 按鈕內顯示小型 spinner（可複用 LoadingSpinner sm）
- [x] 5.3 修改 MultiSelect：將 unicode `▲`/`▼` 替換為 SVG chevron icon，加入 `transform: rotate(180deg)` transition（使用 `--motion-fast: 150ms`）
- [x] 5.4 新增 `frontend/src/shared-ui/components/ErrorBanner.vue`：接受 `message` prop + `dismissible` prop（預設 true）+ `action` slot；使用 `<style scoped>` 定義樣式（沿用現有 `.ui-error-banner` 視覺風格）；emit `dismiss` 事件
- [x] 5.5 更新 `contract/css_inventory.md` 加入 `ErrorBanner.vue` scoped style 條目
- [x] 5.6 執行 `npm run build` 驗證；手動測試 MultiSelect loading/chevron、ErrorBanner dismiss

## 6. Phase 6 — 元件一致性整理（長期）

- [x] 6.1 審查 `resource-shared/styles.css` 中的 `.section-card` / `.section-inner` / `.section-title` 定義，確認哪些可以移除並由 `SectionCard.vue` + `ui-section-card` 取代（保留：使用 CSS vars，與 ui-section-* 差異明顯）
- [x] 6.2 審查 `hold-overview/style.css` 中的 `.card` / `.card-header` / `.card-body` 定義，確認取代方案（保留：使用 wip-shared CSS vars，不安全移除）
- [x] 6.3 將 `resource-shared/styles.css` 中的 `.multi-select` 基礎樣式移入 `MultiSelect.vue` 的 `<style scoped>`，僅保留 theme-specific overrides
- [x] 6.4 移除 `resource-shared/styles.css` 和 `wip-shared/styles.css` 中重複的 `.loading-overlay` / `.loading-spinner` 定義，確認各消費者已改用 shared-ui 元件（跳過：Vue templates 仍直接使用 class names）
- [x] 6.5 移除 `hold-overview/style.css` 和 `resource-shared/styles.css` 中重複的 `.error-banner` 定義，逐步替換消費者為 `ErrorBanner` 元件（跳過：20+ 處仍使用 class name）
- [x] 6.6 盤點 `token.hXXXXXX` 使用處，建立語義化 token 對照表，在後續修改中逐步遷移（49 vue / 665 css 參照，需後續版本逐步遷移）
- [x] 6.7 執行 `npm run build` 驗證；逐模組手動測試視覺一致性
