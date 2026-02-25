## Why

「製程不良追溯分析」頁面（mid-section-defect）目前的反向追溯只歸因到**上游機台**這單一維度。品質工程師在實務上需要同時比對多個因子（機台、原物料批號、源頭晶片）才能定位根因。現有的 EventFetcher 和 LineageEngine 已具備查詢原物料與血緣的能力，但分析頁面尚未整合這些資料來源。此外，頁面缺乏對歸因邏輯的透明度說明，使用者不了解數字是如何計算出來的。

## What Changes

### 新增多因子歸因維度
- 新增「依原物料歸因」柏拉圖：以 `material_part_name + material_lot` 為 key，計算歸因不良率（與機台歸因相同邏輯）
- 新增「依源頭晶片歸因」柏拉圖：以 LineageEngine split chain 的 root ancestor (`CONTAINERNAME`) 為 key，計算歸因不良率
- 移除原有的「依封裝 (PACKAGE)」與「依 TYPE」柏拉圖，改為上述兩張
- 「依製程 (WORKFLOW)」柏拉圖移除（產品分布相關分析由「報廢歷史查詢」頁面負責）

### 柏拉圖改善
- 新增排序 toggle：可切換「依不良數」/「依不良率」排序
- 新增 80% 累計標記線（ECharts markLine）
- Tooltip 增加顯示「關聯 LOT 數」

### 分析摘要面板
- 在 KPI 卡片上方新增可收合的「分析摘要」區塊
- 顯示：查詢條件、資料範圍統計（LOT 總數/投入/報廢 LOT 數/報廢總數/血緣追溯涵蓋數）、歸因邏輯文字說明

### 明細表嫌疑因子命中
- 後端 `_build_detail_table` 改回傳結構化的上游機台資料（list of `{station, machine}` objects），取代扁平化逗號字串
- 前端根據當前柏拉圖 Top N 嫌疑因子，在明細表顯示命中狀況（如 `WIRE-03, DIE-01 (2/3)`）
- 嫌疑名單跟隨柏拉圖 inline filter 連動

### 嫌疑機台上下文面板
- 點擊柏拉圖的機台 bar 時，顯示該機台的上下文面板
- 面板內容：歸因數據摘要、所屬站點/機型、近期維修紀錄（透過 query-tool 的 `get_lot_jobs` API 取得）

### 後端：多因子歸因引擎
- 在 `mid_section_defect_service.py` 新增 `_attribute_materials()` 函數（歸因邏輯與 `_attribute_defects` 相同 pattern）
- 在 `mid_section_defect_service.py` 新增 `_attribute_wafer_roots()` 函數（以 root ancestor 為 key）
- Staged trace API events stage 新增請求 `materials` domain 的支援（已在 EventFetcher 中支援，只需在 mid_section_defect profile 的 domain 列表中加入）
- `_build_all_charts` 改為使用新的 DIMENSION_MAP（移除 by_package / by_pj_type / by_workflow，新增 by_material / by_wafer_root）

### 報廢歷史查詢頁面增強
- 將「依 PACKAGE / TYPE / WORKFLOW」的產品分布分析遷移到報廢歷史查詢頁面
- 在報廢歷史查詢頁面新增 Pareto 維度選擇器，支援多維度切換（原因、PACKAGE、TYPE、WORKFLOW、站點、機台）

## Capabilities

### New Capabilities
- `msd-multifactor-attribution`: 製程不良追溯分析的多因子歸因引擎（原物料、源頭晶片）及對應的柏拉圖呈現
- `msd-analysis-transparency`: 分析摘要面板，顯示查詢條件、資料範圍、歸因邏輯說明
- `msd-suspect-context`: 嫌疑機台上下文面板及明細表嫌疑因子命中呈現

### Modified Capabilities
- `reject-history-page`: 新增產品分布 Pareto 維度（PACKAGE / TYPE / WORKFLOW），接收從製程不良追溯頁面遷出的分析責任
- `trace-staged-api`: mid_section_defect profile 的 events stage 新增 `materials` domain 請求，aggregation 邏輯新增原物料與晶片歸因

## Impact

### Backend
- `src/mes_dashboard/services/mid_section_defect_service.py` — 核心改動：新增歸因函數、修改 chart builder、修改 detail table 結構
- `src/mes_dashboard/routes/trace_routes.py` — events stage 的 mid_section_defect profile domain 列表擴充
- `src/mes_dashboard/routes/mid_section_defect_routes.py` — export 可能需要對應新欄位
- `src/mes_dashboard/services/reject_history_service.py` — 新增 Pareto 維度支援
- `src/mes_dashboard/routes/reject_history_routes.py` — 新增維度參數

### Frontend
- `frontend/src/mid-section-defect/App.vue` — 主要改動：新增分析摘要、重排柏拉圖、嫌疑命中邏輯
- `frontend/src/mid-section-defect/components/ParetoChart.vue` — 新增排序 toggle、80% markLine、tooltip lot_count
- `frontend/src/mid-section-defect/components/DetailTable.vue` — 嫌疑命中欄位改版
- `frontend/src/mid-section-defect/components/KpiCards.vue` — 可能微調
- 新增 `frontend/src/mid-section-defect/components/AnalysisSummary.vue`
- 新增 `frontend/src/mid-section-defect/components/SuspectContextPanel.vue`
- `frontend/src/reject-history/components/ParetoSection.vue` — 新增維度選擇器
- `frontend/src/reject-history/App.vue` — 支援多維度 Pareto

### SQL
- 可能新增 `src/mes_dashboard/sql/mid_section_defect/upstream_materials.sql`（或直接複用 EventFetcher materials domain 的 `query_tool/lot_materials.sql`）

### Tests
- `tests/test_mid_section_defect.py` — 新增原物料/晶片歸因的單元測試
- `tests/test_reject_history_routes.py` — 新增維度 Pareto 測試
