# Implementation Tasks

## Phase 1: Backend - Hold 分類邏輯

### wip_service.py

- [x] 新增 `NON_QUALITY_HOLD_REASONS` 常數 Set（11 個非品質異常 Reason）
- [x] 新增 `is_quality_hold(reason: str)` 輔助函數
- [x] 新增 `_build_hold_type_sql_list()` 函數產生 SQL IN clause

### get_wip_summary() 修改

- [x] SQL 新增 `QUALITY_HOLD_LOTS` 和 `QUALITY_HOLD_QTY_PCS` 統計
- [x] SQL 新增 `NON_QUALITY_HOLD_LOTS` 和 `NON_QUALITY_HOLD_QTY_PCS` 統計
- [x] 回應新增 `qualityHold` 和 `nonQualityHold` 欄位

### get_wip_matrix() 修改

- [x] 新增 `hold_type` 參數（Optional[str]）
- [x] 當 `status='HOLD'` 且 `hold_type='quality'` 時，加入 `HOLDREASONNAME NOT IN (...)` 條件
- [x] 當 `status='HOLD'` 且 `hold_type='non-quality'` 時，加入 `HOLDREASONNAME IN (...)` 條件

### get_wip_hold_summary() 修改

- [x] 回應每個 item 新增 `holdType` 欄位（`'quality'` 或 `'non-quality'`）

### get_wip_detail() 修改

- [x] 新增 `hold_type` 參數（Optional[str]）
- [x] Summary 統計新增 `qualityHoldLots` 和 `nonQualityHoldLots`
- [x] 當 `status='HOLD'` 且有 `hold_type` 時，過濾對應 Hold 類型

---

## Phase 2: Backend - API Routes

### wip_routes.py

- [x] `/api/wip/overview/matrix` 新增 `hold_type` query parameter
- [x] `/api/wip/detail/<workcenter>` 新增 `hold_type` query parameter
- [x] 將 `hold_type` 傳遞給 service 函數

---

## Phase 3: Frontend - WIP Overview

### CSS 樣式 (wip_overview.html)

- [x] `.wip-status-row` grid 改為 4 欄 (`repeat(4, 1fr)`)
- [x] 新增 `.wip-status-card.quality-hold` 樣式（紅色系）
- [x] 新增 `.wip-status-card.non-quality-hold` 樣式（橘色系）
- [x] 新增 `.hold-type-badge` 樣式（品質/非品質標籤）

### HTML 卡片 (wip_overview.html)

- [x] 移除原本的 `.wip-status-card.hold`
- [x] 新增「品質異常」卡片 (`quality-hold`)，綁定 `toggleStatusFilter('quality-hold')`
- [x] 新增「非品質異常」卡片 (`non-quality-hold`)，綁定 `toggleStatusFilter('non-quality-hold')`

### JavaScript 狀態管理 (wip_overview.html)

- [x] `renderSummary()` 更新：讀取 `qualityHold` 和 `nonQualityHold` 並顯示
- [x] `toggleStatusFilter()` 更新：支援 `'quality-hold'` 和 `'non-quality-hold'`
- [x] `updateCardStyles()` 更新：處理新的卡片 class
- [x] `updateMatrixTitle()` 更新：顯示「品質異常 Hold Only」或「非品質異常 Hold Only」
- [x] `fetchMatrix()` 更新：當 filter 為 hold 類型時，傳送 `status=HOLD` + `hold_type`

### Hold Summary 表格 (wip_overview.html)

- [x] `renderHold()` 更新：在 Reason 前面加入類型標籤 badge

---

## Phase 4: Frontend - WIP Detail

### CSS 樣式 (wip_detail.html)

- [x] `.summary-row` grid 改為 5 欄 (`repeat(5, 1fr)`)
- [x] 新增 `.summary-card.status-quality-hold` 樣式（紅色系）
- [x] 新增 `.summary-card.status-non-quality-hold` 樣式（橘色系）
- [x] 更新 responsive breakpoints（1400px → 3 欄，768px → 1 欄）

### HTML 卡片 (wip_detail.html)

- [x] 移除原本的 `.summary-card.status-hold`
- [x] 新增「品質異常」卡片，綁定 `toggleStatusFilter('quality-hold')`
- [x] 新增「非品質異常」卡片，綁定 `toggleStatusFilter('non-quality-hold')`

### JavaScript 狀態管理 (wip_detail.html)

- [x] `renderSummary()` 更新：讀取並顯示 `qualityHoldLots` 和 `nonQualityHoldLots`
- [x] `toggleStatusFilter()` 更新：支援 `'quality-hold'` 和 `'non-quality-hold'`
- [x] `updateCardStyles()` 更新：處理新的卡片 class
- [x] `updateTableTitle()` 更新：顯示「品質異常 Hold Only」或「非品質異常 Hold Only」
- [x] `fetchDetail()` 更新：當 filter 為 hold 類型時，傳送 `status=HOLD` + `hold_type`

---

## Phase 5: 驗證

- [x] 手動測試：WIP Overview 4 張卡片顯示正確數據
- [x] 手動測試：WIP Overview 點擊品質異常卡片，Matrix 正確篩選
- [x] 手動測試：WIP Overview 點擊非品質異常卡片，Matrix 正確篩選
- [x] 手動測試：WIP Overview Hold Summary 顯示類型標籤
- [x] 手動測試：WIP Detail 5 張卡片顯示正確數據
- [x] 手動測試：WIP Detail 點擊品質異常卡片，Table 正確篩選
- [x] 手動測試：WIP Detail 點擊非品質異常卡片，Table 正確篩選
- [x] 驗證：`qualityHold + nonQualityHold = hold` 統計一致性
- [x] 響應式測試：不同螢幕寬度下卡片正確排列
