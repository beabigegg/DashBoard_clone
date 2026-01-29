## MODIFIED Requirements

### Requirement: Resource History KPI API - Availability%

系統 SHALL 在 KPI API 回應中新增 `availability_pct` 欄位。

#### Scenario: KPI includes availability percentage
- **WHEN** 呼叫 `GET /api/resource/history/summary`
- **THEN** 回應的 `kpi` 物件 SHALL 包含 `availability_pct` 欄位
- **AND** `availability_pct` 計算公式為 `(PRD + SBY + EGT) / (PRD + SBY + EGT + SDT + UDT + NST) * 100`
- **AND** 數值四捨五入至小數點後一位

#### Scenario: Availability percentage handles zero denominator
- **WHEN** 分母 `(PRD + SBY + EGT + SDT + UDT + NST)` 為零
- **THEN** `availability_pct` SHALL 回傳 `0`

---

### Requirement: Resource History Trend API - Availability%

系統 SHALL 在趨勢 API 回應的每個資料點中新增 `availability_pct` 欄位。

#### Scenario: Trend data includes availability percentage
- **WHEN** 呼叫 `GET /api/resource/history/summary`
- **THEN** 回應的 `trend` 陣列中每個物件 SHALL 包含 `availability_pct` 欄位
- **AND** 各資料點的 `availability_pct` 使用該時間區段的 E10 狀態時數計算

#### Scenario: Trend availability calculation formula
- **GIVEN** 單一時間區段的 E10 狀態時數
- **WHEN** 計算該區段的 `availability_pct`
- **THEN** 公式為 `(PRD_HOURS + SBY_HOURS + EGT_HOURS) / (PRD_HOURS + SBY_HOURS + EGT_HOURS + SDT_HOURS + UDT_HOURS + NST_HOURS) * 100`

---

### Requirement: Resource History Detail API - Availability%

系統 SHALL 在明細 API 回應的每筆資料中新增 `availability_pct` 欄位。

#### Scenario: Detail data includes availability percentage
- **WHEN** 呼叫 `GET /api/resource/history/detail`
- **THEN** 回應的 `data` 陣列中每個物件 SHALL 包含 `availability_pct` 欄位

---

### Requirement: CSV Export - Availability%

系統 SHALL 在 CSV 匯出中新增 Availability% 欄位。

#### Scenario: CSV includes availability column
- **WHEN** 匯出 CSV 檔案
- **THEN** CSV 標頭 SHALL 包含 `Availability%` 欄位（位於 `OU%` 之後）
- **AND** 各列的 `Availability%` 使用該機台的 E10 狀態時數計算

---

### Requirement: Frontend Trend Chart - Availability%

系統 SHALL 在趨勢圖中新增 Availability% 趨勢線。

#### Scenario: Chart displays availability trend line
- **WHEN** 顯示設備歷史績效頁面的趨勢圖
- **THEN** 圖表 SHALL 顯示 Availability% 趨勢線
- **AND** Availability% 使用綠色 (`#10B981`) 顯示
- **AND** OU% 保持原有藍色 (`#3B82F6`)

#### Scenario: Chart legend shows both metrics
- **WHEN** 顯示趨勢圖
- **THEN** 圖例 SHALL 包含 "OU%" 與 "Availability%" 兩項

---

### Requirement: Frontend KPI Card - Availability%

系統 SHALL 在 KPI 區新增 Availability% 卡片。

#### Scenario: KPI section displays availability card
- **WHEN** 顯示設備歷史績效頁面
- **THEN** KPI 區 SHALL 顯示 Availability% 卡片
- **AND** 卡片顯示格式為 `XX.X%`
- **AND** 卡片位置在 OU% 卡片之後
