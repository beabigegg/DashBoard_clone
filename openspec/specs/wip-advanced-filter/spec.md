## ADDED Requirements

### Requirement: DUMMY Lot 預設排除

系統 SHALL 預設排除 LOTID 包含 "DUMMY" 字串的資料，適用於所有 WIP 查詢端點。

#### Scenario: 預設查詢排除 DUMMY
- **WHEN** 使用者載入 WIP Overview 或 Detail 頁面，未指定 include_dummy 參數
- **THEN** 系統回傳的資料不包含任何 LOTID 含 "DUMMY" 的記錄

#### Scenario: 明確包含 DUMMY
- **WHEN** API 請求包含參數 `include_dummy=true`
- **THEN** 系統回傳的資料包含所有記錄（含 DUMMY lots）

---

### Requirement: WORKORDER 模糊搜尋

系統 SHALL 提供 WORKORDER 模糊搜尋功能，允許使用者透過部分字串找出匹配的 Work Order。

#### Scenario: 搜尋 WORKORDER
- **WHEN** 使用者在 WORKORDER 搜尋框輸入 "GA26" 並觸發搜尋
- **THEN** 系統回傳 WORKORDER 欄位包含 "GA26" 的前 20 筆不重複結果

#### Scenario: 最少輸入字元限制
- **WHEN** 使用者輸入少於 2 個字元
- **THEN** 系統不觸發搜尋，下拉選單維持空白

#### Scenario: 套用 WORKORDER 篩選
- **WHEN** 使用者選擇特定 WORKORDER 並套用篩選
- **THEN** 頁面僅顯示該 WORKORDER 的相關 lot 資料

---

### Requirement: LOT ID 模糊搜尋

系統 SHALL 提供 LOT ID 模糊搜尋功能，允許使用者透過部分字串找出匹配的 Lot。

#### Scenario: 搜尋 LOT ID
- **WHEN** 使用者在 LOT ID 搜尋框輸入 "GA26011" 並觸發搜尋
- **THEN** 系統回傳 LOTID 欄位包含 "GA26011" 的前 20 筆結果

#### Scenario: 套用 LOT ID 篩選
- **WHEN** 使用者選擇特定 LOT ID 並套用篩選
- **THEN** 頁面僅顯示該 LOT 的詳細資料

---

### Requirement: Autocomplete 下拉選單

系統 SHALL 提供 autocomplete 下拉選單，顯示搜尋結果供使用者選擇。

#### Scenario: 顯示搜尋結果
- **WHEN** 搜尋 API 回傳結果
- **THEN** 下拉選單顯示匹配的選項，最多 20 筆

#### Scenario: 選擇選項
- **WHEN** 使用者點擊下拉選單中的選項
- **THEN** 該值填入搜尋框，並可用於後續篩選

#### Scenario: 輸入防抖
- **WHEN** 使用者快速連續輸入字元
- **THEN** 系統等待 300ms 無新輸入後才觸發搜尋 API

---

### Requirement: 搜尋 API 端點

系統 SHALL 提供統一的搜尋 API 端點供前端查詢 WORKORDER 與 LOT ID。

#### Scenario: 查詢 WORKORDER 清單
- **WHEN** 前端請求 `GET /api/wip/meta/search?type=workorder&q=GA26&limit=20`
- **THEN** 系統回傳 JSON 格式的 WORKORDER 清單，欄位包含 `items` 陣列

#### Scenario: 查詢 LOT ID 清單
- **WHEN** 前端請求 `GET /api/wip/meta/search?type=lotid&q=GA26011&limit=20`
- **THEN** 系統回傳 JSON 格式的 LOT ID 清單，欄位包含 `items` 陣列

#### Scenario: 空查詢字串
- **WHEN** 前端請求搜尋 API 但 `q` 參數為空或少於 2 字元
- **THEN** 系統回傳空的 `items` 陣列

---

### Requirement: WIP Overview 篩選器整合

WIP Overview 頁面 SHALL 整合 WORKORDER 與 LOT ID 篩選功能。

#### Scenario: 篩選器顯示於頁面
- **WHEN** 使用者載入 WIP Overview 頁面
- **THEN** 頁面顯示 WORKORDER 與 LOT ID 搜尋框

#### Scenario: 篩選影響所有區塊
- **WHEN** 使用者套用 WORKORDER 或 LOT ID 篩選
- **THEN** KPI 摘要、矩陣表格、Hold 摘要皆依篩選條件更新

---

### Requirement: WIP Detail 篩選器整合

WIP Detail 頁面 SHALL 整合 WORKORDER 與 LOT ID 篩選功能。

#### Scenario: 篩選器顯示於頁面
- **WHEN** 使用者載入 WIP Detail 頁面
- **THEN** 頁面顯示 WORKORDER 與 LOT ID 搜尋框，與現有 Package/Status 篩選器並列

#### Scenario: 多重篩選條件
- **WHEN** 使用者同時設定 Package、Status、WORKORDER 篩選
- **THEN** 系統以 AND 邏輯組合所有條件，回傳符合全部條件的資料
