### Requirement: Hold Summary 柏拉圖視覺化

系統 SHALL 在 WIP Overview 頁面以兩張柏拉圖呈現 Hold 資料分佈，分別為品質異常 Hold 與非品質異常 Hold。

#### Scenario: 顯示品質異常柏拉圖
- **WHEN** 頁面載入 Hold 資料且存在品質異常 Hold
- **THEN** 系統顯示品質異常柏拉圖，X 軸為 Hold Reason，Y 軸（左）為 QTY 柱狀圖，Y 軸（右）為累計百分比折線圖

#### Scenario: 顯示非品質異常柏拉圖
- **WHEN** 頁面載入 Hold 資料且存在非品質異常 Hold
- **THEN** 系統顯示非品質異常柏拉圖，X 軸為 Hold Reason，Y 軸（左）為 QTY 柱狀圖，Y 軸（右）為累計百分比折線圖

#### Scenario: 無資料時顯示提示
- **WHEN** 某分類（品質或非品質）無 Hold 資料
- **THEN** 該分類圖表區域顯示「目前無資料」提示訊息

### Requirement: 柏拉圖排序與累計計算

系統 SHALL 按 QTY 降序排列 Hold Reason，並以 QTY 計算累計百分比。

#### Scenario: QTY 降序排列
- **WHEN** 渲染柏拉圖
- **THEN** Hold Reason 按 QTY 由高至低排列於 X 軸

#### Scenario: 累計百分比計算
- **WHEN** 渲染柏拉圖累計線
- **THEN** 累計百分比以各 Reason 的 QTY 佔該分類總 QTY 比例累加計算

### Requirement: 柏拉圖摘要表格

系統 SHALL 在每張柏拉圖下方顯示摘要表格，包含 Hold Reason、Lots、QTY、累計%。

#### Scenario: 摘要表格欄位
- **WHEN** 渲染摘要表格
- **THEN** 表格包含欄位：Hold Reason（可點擊）、Lots 數量、QTY 數量、累計百分比

#### Scenario: 摘要表格排序
- **WHEN** 渲染摘要表格
- **THEN** 表格資料順序與柏拉圖一致（QTY 降序）

### Requirement: Hold Reason Drill-down

系統 SHALL 支援點擊柏拉圖柱狀或摘要表格連結跳轉至 Hold Detail 頁面。

#### Scenario: 點擊柏拉圖柱狀
- **WHEN** 使用者點擊柏拉圖中的某一柱狀
- **THEN** 導向 `/hold-detail?reason={encoded_reason}` 頁面

#### Scenario: 點擊摘要表格連結
- **WHEN** 使用者點擊摘要表格中的 Hold Reason 連結
- **THEN** 導向 `/hold-detail?reason={encoded_reason}` 頁面

### Requirement: 響應式版面配置

系統 SHALL 支援響應式設計，大螢幕兩欄並排，小螢幕垂直堆疊。

#### Scenario: 大螢幕並排顯示
- **WHEN** 螢幕寬度 >= 1200px
- **THEN** 品質異常與非品質異常柏拉圖並排顯示

#### Scenario: 小螢幕堆疊顯示
- **WHEN** 螢幕寬度 < 1200px
- **THEN** 品質異常與非品質異常柏拉圖垂直堆疊顯示
