## CHANGED Requirements

### Requirement: KPI 摘要卡片（修改）

原有 4 個 KPI 卡片（總 Lots、總 QTY、Hold Lots、Hold QTY）修改為 2 個 KPI 卡片。

#### Scenario: 顯示 KPI 摘要
- **WHEN** Overview 頁面載入完成
- **THEN** 系統顯示 2 個 KPI 卡片：
  - 總 Lots 數量（Total Lots）
  - 總 QTY 數量（Total QTY，使用千分位格式）
- **AND** 移除獨立的 Hold Lots、Hold QTY 卡片（已整合至 WIP Status 卡片）

## ADDED Requirements

### Requirement: WIP Status 狀態卡片

系統 SHALL 在 KPI 摘要卡片下方顯示 3 個 WIP Status 狀態卡片（RUN、QUEUE、HOLD）。

#### Scenario: 顯示 WIP Status 卡片
- **WHEN** Overview 頁面載入完成
- **THEN** 系統顯示 3 個狀態卡片，依序為：
  1. **RUN 卡片**（綠色邊框，淺綠背景）
     - 顯示 RUN 狀態的 Lots 數量
     - 顯示 RUN 狀態的 QTY 數量（pcs）
  2. **QUEUE 卡片**（黃色邊框，淺黃背景）
     - 顯示 QUEUE 狀態的 Lots 數量
     - 顯示 QUEUE 狀態的 QTY 數量（pcs）
  3. **HOLD 卡片**（紅色邊框，淺紅背景）
     - 顯示 HOLD 狀態的 Lots 數量
     - 顯示 HOLD 狀態的 QTY 數量（pcs）

#### Scenario: WIP Status 卡片數字呈現
- **GIVEN** WIP Status 卡片
- **THEN** Lots 數量與 QTY 數量使用相同字體大小顯示
- **AND** 兩個數字並排呈現，讓主管可同時清楚看到

### Requirement: WIP Status 卡片顏色定義

系統 SHALL 使用以下顏色定義 WIP Status 卡片：

| 狀態 | 邊框顏色 | 背景顏色 | 標籤文字顏色 |
|------|----------|----------|--------------|
| RUN | #22C55E | #F0FDF4 | #166534 |
| QUEUE | #F59E0B | #FFFBEB | #92400E |
| HOLD | #EF4444 | #FEF2F2 | #991B1B |

### Requirement: Summary API 回應格式

系統 SHALL 修改 Summary API 回傳格式以支援 WIP Status 顯示。

#### Scenario: API 回傳 WIP Status 統計
- **WHEN** 前端呼叫 `/api/wip/overview/summary`
- **THEN** API 回傳包含：
  ```json
  {
    "success": true,
    "data": {
      "totalLots": 1234,
      "totalQtyPcs": 56789,
      "byWipStatus": {
        "run": { "lots": 500, "qtyPcs": 30000 },
        "queue": { "lots": 634, "qtyPcs": 21789 },
        "hold": { "lots": 100, "qtyPcs": 5000 }
      },
      "dataUpdateDate": "2026-01-27 14:30:00"
    }
  }
  ```
