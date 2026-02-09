## Context

設備即時概況與設備歷史績效是專案中最後一組使用三層階層樹表的 Jinja2 頁面。兩頁合計 1,697 行 vanilla JS + 3,200 行 Jinja2 模板（含 820 行重複 inline fallback script）。已有 5 頁（QC-GATE、Tables、WIP 三頁）成功遷移至 Vue 3 + Vite 純前端，模式穩定。

兩頁共享：
- 三層階層樹表（workcenter group → family → resource）
- E10 狀態碼集（PRD/SBY/UDT/SDT/EGT/NST + 聚合規則 PM→UDT、ENG→EGT、OFF→NST）
- OU%/Availability% KPI 計算（`core/compute.js`）
- 樹狀展開/收合（`core/table-tree.js`）
- 篩選模式（workcenter groups、is_production/is_key/is_monitor）
- CSS 變數系統（`:root` 色碼、卡片、表格樣式）

## Goals / Non-Goals

**Goals:**
- 兩頁完全脫離 Jinja2 + `_base.html`，改用 `send_from_directory` 靜態服務
- 抽取 `resource-shared/` 共用模組，消除兩頁間的重複邏輯
- History 頁 ECharts 改用 vue-echarts，與 QC-GATE/WIP Overview 一致
- Status 頁複用 `useAutoRefresh` composable
- 移除 Jinja2 模板及 inline fallback script

**Non-Goals:**
- 不修改後端 API 端點或回傳結構
- 不新增 npm 依賴（vue-echarts、echarts 已安裝）
- 不重構後端 cache 架構
- 不增加功能（如 History 頁新增自動刷新）

## Decisions

### D1: 抽取 `resource-shared/` 共用模組

**選擇**：建立 `frontend/src/resource-shared/` 放置兩頁共用的 CSS、常數、元件。
**替代方案**：(a) 各頁獨立 — 大量重複；(b) 放入 `core/` — 太專屬設備頁面，不適合通用模組。
**理由**：與 `wip-shared/` 模式一致，語義清晰。

共用模組內容：
- `styles.css`：`:root` 變數、status 顏色、tree table 樣式、KPI 卡片樣式、loading overlay
- `constants.js`：`STATUS_DISPLAY_MAP`（6 值中英對照）、`STATUS_AGGREGATION`（PM→UDT 等聚合規則）、`STATUS_COLORS`（6 色碼）、`OU_BADGE_THRESHOLDS`（high≥80/medium≥50/low<50）
- `components/HierarchyTable.vue`：三層展開/收合樹表元件，接收 `hierarchy` prop 和 `columns` 定義，兩頁共用

### D2: HierarchyTable.vue 設計

**選擇**：單一 `<HierarchyTable>` 元件，透過 `columns` prop 定義欄位、`hierarchy` prop 傳入資料、`@cell-click` 事件處理互動。
**替代方案**：(a) 遞迴 TreeNode 元件 — 過度設計，三層固定深度不需遞迴；(b) 各頁獨立表格 — 重複。
**理由**：三層結構固定（group → family → resource），用 `v-for` 嵌套即可，不需泛用遞迴。

### D3: vue-echarts 統一 ECharts 使用方式

**選擇**：History 頁的 4 個 ECharts 圖表全部改用 `<VChart :option="..." autoresize />`。
**替代方案**：直接使用 ECharts API + `onMounted` 手動 init/dispose。
**理由**：vue-echarts 已用於 QC-GATE 和 WIP Overview，`autoresize` 解決 iframe 隱藏時 width=0 問題。4 個圖表各自封裝為獨立元件。

### D4: Status 頁 tooltip 實作

**選擇**：自訂 `<FloatingTooltip>` 元件 + CSS fixed 定位（移植現有邏輯）。
**替代方案**：(a) Floating UI 庫 — 新增依賴；(b) 原生 `title` — 太簡陋。
**理由**：現有 tooltip 邏輯已穩定（viewport clamp + 點擊觸發），Vue 化後更乾淨（`<Teleport to="body">` + `v-if`），無需新增依賴。

### D5: Status 頁自動刷新複用

**選擇**：直接 import `wip-shared/composables/useAutoRefresh.js`（跨 shared 目錄引用）。
**替代方案**：(a) 複製到 resource-shared/ — 重複；(b) 移至 core/ — 改動範圍大。
**理由**：composable 無 WIP 特定邏輯，路徑引用 `../../wip-shared/composables/useAutoRefresh.js` 可行。intervalMs 設為 5 分鐘（Status 頁用 5 分鐘而非 WIP 的 10 分鐘）。

### D6: 多選下拉元件（History 頁）

**選擇**：自訂 `<MultiSelect>` 元件（移植現有邏輯）。
**替代方案**：Element Plus Select — 引入大型 UI 庫。
**理由**：現有多選邏輯簡單（checkbox list + click-outside-close + select all/clear），Vue 化後用 `v-model` 綁定即可，無需外部庫。

### D7: 元件拆分策略

**resource-status 元件結構**：
```
App.vue
├── StatusHeader.vue        (cache 狀態、最後更新時間)
├── FilterBar.vue           (群組下拉 + 3 checkbox)
├── SummaryCards.vue         (10 張 KPI 卡片)
├── MatrixSection.vue        (expand/collapse toolbar + HierarchyTable)
├── EquipmentGrid.vue        (設備卡片格 + 篩選指示器)
│   └── EquipmentCard.vue    (單張設備卡片)
└── FloatingTooltip.vue      (LOT/JOB 詳情 tooltip)
```

**resource-history 元件結構**：
```
App.vue
├── FilterBar.vue           (日期 + 粒度 + 多選 + checkbox)
│   └── MultiSelect.vue     (多選下拉元件)
├── KpiCards.vue            (9 張 KPI 卡片)
├── ChartSection.vue        (2×2 圖表格)
│   ├── TrendChart.vue      (OU%/AVAIL% 趨勢折線)
│   ├── StackedChart.vue    (E10 狀態堆疊柱狀)
│   ├── ComparisonChart.vue (workcenter OU% 橫條)
│   └── HeatmapChart.vue   (workcenter × 日期 熱圖)
├── DetailSection.vue       (expand/collapse toolbar + HierarchyTable + CSV 匯出)
```

## Risks / Trade-offs

- **[R1] 跨 shared 目錄引用 useAutoRefresh** → 路徑較長但可行，未來若需可移至 `core/`。不在此變更範圍內重構。
- **[R2] HierarchyTable 通用性** → 目前設計為兩頁共用，欄位/格式差異透過 props 和 slots 處理。若未來新頁面需要完全不同的樹表，可獨立元件。
- **[R3] vue-echarts 4 圖同頁效能** → History 頁同時渲染 4 個圖表，資料量大時可能卡頓。vue-echarts `autoresize` + `computed` option 已足夠，不需 lazy loading。
- **[R4] Status 頁 250+ 設備卡片** → 現有實作無虛擬滾動，Vue 化後 `v-for` 渲染相同數量。短期不加虛擬滾動（非 Non-Goal 但不在此範圍），數量級可接受。
