## 1. resource-shared 共用模組

- [x] 1.1 建立 `frontend/src/resource-shared/styles.css` — 從兩頁 Jinja2 模板抽取共用 CSS：`:root` 變數、status 顏色類別（`.col-prd`/`.col-sby`/...）、tree table 樣式（`.row-level-0`/`.row-level-1`/`.row-level-2`、`.indent-1`/`.indent-2`、`.expand-btn`）、KPI 卡片樣式、OU badge 色碼（`.ou-badge.high/medium/low`）、loading overlay、filter indicator
- [x] 1.2 建立 `frontend/src/resource-shared/constants.js` — STATUS_DISPLAY_MAP（PRD→生產中 等 6+值）、STATUS_AGGREGATION（PM/BKD→UDT、ENG→EGT、OFF→NST）、STATUS_COLORS（PRD=#22c55e 等 6 色）、OU_BADGE_THRESHOLDS（high≥80、medium≥50、low<50）、MATRIX_STATUS_COLUMNS 順序定義
- [x] 1.3 建立 `frontend/src/resource-shared/components/HierarchyTable.vue` — 三層展開/收合樹表元件，props: `hierarchy`（三層資料）、`columns`（欄位定義陣列）、`expandedState`（reactive 物件）；events: `@cell-click`、`@toggle-row`、`@toggle-all`；支援 Level 0/1/2 行樣式和縮排

## 2. resource-status Vue 3 遷移

- [x] 2.1 建立 `frontend/src/resource-status/index.html` — HTML entry point，引用 main.js，設定 `<title>設備即時概況</title>`
- [x] 2.2 建立 `frontend/src/resource-status/App.vue` — 頂層元件，整合所有子元件，管理全域狀態（allEquipment、matrixFilter、hierarchyState），呼叫 loadData/loadOptions/loadSummary
- [x] 2.3 建立 `frontend/src/resource-status/components/StatusHeader.vue` — cache 狀態指示（green/yellow/red dot）、最後更新時間、手動刷新按鈕
- [x] 2.4 建立 `frontend/src/resource-status/components/FilterBar.vue` — workcenter group 下拉（GET /api/resource/status/options）+ 3 個 checkbox（生產設備/重點設備/監控設備）
- [x] 2.5 建立 `frontend/src/resource-status/components/SummaryCards.vue` — 10 張 KPI 卡片（Total/PRD/SBY/UDT/SDT/EGT/NST/OTHER/OU%/AVAIL%），含 click 篩選、active 狀態、百分比顯示
- [x] 2.6 建立 `frontend/src/resource-status/components/MatrixSection.vue` — 使用 resource-shared/HierarchyTable，buildMatrixHierarchy 邏輯（3 層聚合 + 狀態歸類），toolbar（expand/collapse all），cell click 篩選設備
- [x] 2.7 建立 `frontend/src/resource-status/components/EquipmentGrid.vue` + `EquipmentCard.vue` — 設備卡片格（auto-fill grid, min 280px），每卡顯示 resource name/status badge/workcenter/group/family/location/LOT count/JOB indicator，狀態色邊框，篩選指示器
- [x] 2.8 建立 `frontend/src/resource-status/components/FloatingTooltip.vue` — `<Teleport to="body">` + `v-if`，LOT 詳情（LOTID/QTY/track-in time/employee）和 JOB 詳情（order/status/model/technician/codes），viewport clamp 定位邏輯
- [x] 2.9 整合 useAutoRefresh — import `wip-shared/composables/useAutoRefresh.js`，intervalMs 設為 5 分鐘（5 * 60 * 1000），接入 loadData 作為 onRefresh

## 3. resource-history Vue 3 遷移

- [x] 3.1 建立 `frontend/src/resource-history/index.html` — HTML entry point，設定 `<title>設備歷史績效</title>`
- [x] 3.2 建立 `frontend/src/resource-history/App.vue` — 頂層元件，管理 summaryData/detailData/hierarchyState/filters 狀態，executeQuery 整合 parallel API calls
- [x] 3.3 建立 `frontend/src/resource-history/components/FilterBar.vue` — 日期區間（預設 last 7 days）+ 粒度按鈕（日/週/月/年）+ 查詢按鈕
- [x] 3.4 建立 `frontend/src/resource-history/components/MultiSelect.vue` — 多選下拉元件（checkbox list + click-outside-close + select all/clear），v-model 綁定 selectedItems 陣列，供 workcenter groups 和 families 使用
- [x] 3.5 建立 `frontend/src/resource-history/components/KpiCards.vue` — 9 張 KPI 卡片（OU%/AVAIL%/PRD/SBY/UDT/SDT/EGT/NST/Machine Count），使用 buildResourceKpiFromHours() 計算，大數值用 K 格式
- [x] 3.6 建立 `frontend/src/resource-history/components/TrendChart.vue` — vue-echarts 折線圖（OU%+AVAIL% 雙線，smooth area fill 0.2 opacity），`<VChart :option="chartOption" autoresize />`
- [x] 3.7 建立 `frontend/src/resource-history/components/StackedChart.vue` — vue-echarts 堆疊柱狀圖（6 狀態 hours per period），使用 resource-shared STATUS_COLORS
- [x] 3.8 建立 `frontend/src/resource-history/components/ComparisonChart.vue` — vue-echarts 橫向柱狀圖（top 15 workcenters by OU%），色碼 green/yellow/red（同 OU badge 閾值）
- [x] 3.9 建立 `frontend/src/resource-history/components/HeatmapChart.vue` — vue-echarts 2D 熱圖（workcenters × dates），visualMap red→yellow→green，workcenter_seq 排序
- [x] 3.10 建立 `frontend/src/resource-history/components/DetailSection.vue` — 使用 resource-shared/HierarchyTable，buildHierarchy 邏輯（3 層聚合 + hours 計算），toolbar（expand/collapse all + CSV export 按鈕）
- [x] 3.11 實作 CSV 匯出 — 點擊按鈕建立臨時 `<a>` 導向 `/api/resource/history/export?...` 下載

## 4. Vite 建置與 Flask 路由

- [x] 4.1 更新 `frontend/vite.config.js` — resource-status 和 resource-history entry 從 `main.js` 改為 `index.html`
- [x] 4.2 更新 `frontend/package.json` build script — 新增 resource-status.html 和 resource-history.html 的 copy 指令
- [x] 4.3 更新 `src/mes_dashboard/app.py` — `/resource` route 改為 `send_from_directory(dist_dir, 'resource-status.html')`，`/resource-history` route 改為 `send_from_directory(dist_dir, 'resource-history.html')`

## 5. 清理與驗證

- [x] 5.1 刪除 Jinja2 模板 `templates/resource_status.html` 和 `templates/resource_history.html`
- [x] 5.2 刪除 resource-status/main.js 和 resource-history/main.js 中的舊 vanilla JS 程式碼（替換為 Vue 3 的 createApp 入口）
- [x] 5.3 執行 `npm run build` 確認建置成功，確認 `static/dist/` 產出 resource-status.html/js/css 和 resource-history.html/js/css
- [x] 5.4 驗證兩頁在 portal iframe 中正常載入，CSP frame-ancestors 'self' 允許嵌入
