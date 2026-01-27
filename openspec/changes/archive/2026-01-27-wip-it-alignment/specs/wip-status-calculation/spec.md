## ADDED Requirements

### Requirement: WIP Status 三態計算

系統 SHALL 根據 IT Power BI 標準定義計算 WIP Status，將每個 Lot 分類為 RUN、HOLD 或 QUEUE 三種狀態之一。

#### Scenario: 判斷 RUN 狀態
- **GIVEN** 一筆 WIP 資料
- **WHEN** `EQUIPMENTCOUNT > 0`
- **THEN** WIP Status = "RUN"，WIP Status Sequence = 1

#### Scenario: 判斷 HOLD 狀態
- **GIVEN** 一筆 WIP 資料
- **WHEN** `EQUIPMENTCOUNT = 0` AND `CURRENTHOLDCOUNT > 0`
- **THEN** WIP Status = "HOLD"，WIP Status Sequence = 3

#### Scenario: 判斷 QUEUE 狀態
- **GIVEN** 一筆 WIP 資料
- **WHEN** `EQUIPMENTCOUNT = 0` AND `CURRENTHOLDCOUNT = 0`
- **THEN** WIP Status = "QUEUE"，WIP Status Sequence = 2

### Requirement: WIP Status 分組統計

系統 SHALL 在 Summary API 提供按 WIP Status 分組的統計數據。

#### Scenario: 回傳 WIP Status 分組統計
- **WHEN** 呼叫 Summary API
- **THEN** 回傳資料包含 `byWipStatus` 物件：
  ```json
  {
    "byWipStatus": {
      "run": { "lots": 500, "qtyPcs": 30000 },
      "queue": { "lots": 634, "qtyPcs": 21789 },
      "hold": { "lots": 100, "qtyPcs": 5000 }
    }
  }
  ```

### Requirement: 保留 DUMMY 過濾

系統 SHALL 在所有 WIP Status 計算中保留現有的 DUMMY 過濾條件。

#### Scenario: 排除 DUMMY Lots
- **GIVEN** WIP Status 統計查詢
- **WHEN** 資料中有 LOTID 包含 "DUMMY" 的記錄
- **THEN** 該記錄不納入任何 WIP Status 統計
