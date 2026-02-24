## Why

`/mid-section-defect` 目前僅支援 TMTT 測試站的反向不良追溯，偵測站硬編碼在 SQL 中。實務上需要從任意站點偵測不良並雙向追溯：後段不良回推上游集中機台（反向），前段報廢後倖存批次的下游表現（正向）。將此頁面升級為全線雙向追溯中心，覆蓋 12 個 workcenter group × 2 方向的分析需求。同時移除功能被完全取代的 `/tmtt-defect`（TMTT印字腳型不良分析）頁面。

## What Changes

- **偵測站泛化**：將硬編碼的 TMTT 站點篩選改為參數化，使用者可從 12 個 workcenter group 中選擇任意偵測站
- **反向追溯泛化**：現有 TMTT → 上游機台歸因邏輯保留，但偵測站改為可選（預設仍為「測試」）
- **新增正向追溯**：偵測站報廢批次 → 追蹤倖存批次往下游走 → 各下游站的額外報廢率（判斷部分報廢後剩餘品是否仍有問題）
- **UI 改版**：FilterBar 新增偵測站下拉 + 方向切換；KPI/圖表/明細表依方向動態切換
- **重新命名**：頁面標題從「中段製程不良追溯」改為「製程不良追溯分析」，內部 TMTT_ 前綴統一改為 DETECTION_
- **移除 TMTT 印字腳型不良分析**：`/tmtt-defect` 頁面功能已被泛化後的追溯中心完全覆蓋（選偵測站=測試 + 篩選不良原因=276_腳型不良/277_印字不良），移除前後端代碼與路由註冊

## Capabilities

### New Capabilities
- `defect-trace-station-detection`: 參數化偵測站 SQL 與篩選邏輯，支援任意 workcenter group 作為偵測起點
- `defect-trace-forward-pipeline`: 正向追溯 pipeline — 偵測站報廢批次 → forward lineage → 下游 WIP + 下游報廢記錄 → 正向歸因引擎
- `defect-trace-bidirectional-ui`: 雙向追溯前端 — 偵測站選擇器、方向切換、方向感知的 KPI/圖表/明細表/CSV 匯出

### Modified Capabilities
- `progressive-trace-ux`: 需擴展支援 direction 參數，lineage stage 依方向選擇 ancestor 或 forward tree
- `event-fetcher-unified`: 新增 `downstream_rejects` event domain

## Impact

- **Backend**: `mid_section_defect_service.py`（主要重構）、`mid_section_defect_routes.py`、`trace_routes.py`、`event_fetcher.py`
- **SQL**: 新增 `station_detection.sql`、`downstream_rejects.sql`；修改 `upstream_history.sql`（加 TRACKINQTY）
- **Frontend**: `FilterBar.vue`、`App.vue`、`KpiCards.vue`、`DetailTable.vue`、`useTraceProgress.js`、`style.css`
- **Config**: `page_status.json`（頁面名稱更新 + 移除 tmtt-defect 條目）
- **API**: 所有 `/api/mid-section-defect/*` 端點新增 `station` + `direction` 參數；新增 `/station-options` 端點
- **移除**: `frontend/src/tmtt-defect/`（整個目錄）、`src/mes_dashboard/routes/tmtt_defect_routes.py`、`src/mes_dashboard/services/tmtt_defect_service.py`、`src/mes_dashboard/sql/tmtt_defect/`、相關測試檔案、`nativeModuleRegistry.js` 中的 tmtt-defect 註冊
