## ADDED Requirements

### Requirement: WIP Overview Dashboard 頁面

系統 SHALL 提供 `/wip-overview` 路由，顯示高階主管用的 WIP 總覽 Dashboard。

#### Scenario: 載入 Overview 頁面
- **WHEN** 使用者訪問 `/wip-overview`
- **THEN** 系統顯示 WIP Overview Dashboard，包含 KPI 摘要、工站×產品線矩陣、Hold 摘要

### Requirement: KPI 摘要卡片

系統 SHALL 在頁面頂部顯示 4 個 KPI 摘要卡片：總 Lots、總 QTY、Hold Lots、Hold QTY。

#### Scenario: 顯示 KPI 摘要
- **WHEN** Overview 頁面載入完成
- **THEN** 系統顯示：
  - 總 Lots 數量
  - 總 QTY 數量（使用千分位格式）
  - Hold Lots 數量（紅色標示）
  - Hold QTY 數量（紅色標示）

### Requirement: 工站×產品線矩陣

系統 SHALL 顯示 WORKCENTER_GROUP × PRODUCTLINENAME 的 QTY 矩陣表格。

#### Scenario: 顯示矩陣表格
- **WHEN** Overview 頁面載入資料
- **THEN** 系統顯示矩陣表格：
  - 縱軸：WORKCENTER_GROUP（依 WORKCENTERSEQUENCE_GROUP 排序）
  - 橫軸：PRODUCTLINENAME（依數量排序，取前 N 個主要 Package）
  - 格內：顯示 QTY（千分位格式）
  - 最右欄：該工站的 Total QTY
  - 最下列：該 Package 的 Total QTY

#### Scenario: 點擊工站跳轉
- **WHEN** 使用者點擊矩陣中的某個 WORKCENTER_GROUP 列
- **THEN** 系統跳轉至 `/wip-detail?workcenter={WORKCENTER_GROUP}`

### Requirement: Hold 摘要表

系統 SHALL 顯示 Hold 原因分布表格。

#### Scenario: 顯示 Hold 摘要
- **WHEN** Overview 頁面載入資料
- **THEN** 系統顯示 Hold 摘要表格：
  - 欄位：HOLDREASONNAME、Lots 數量、QTY 數量
  - 依 Lots 數量降序排序
  - 只顯示有 Hold 的資料

### Requirement: 資料更新時間顯示

系統 SHALL 顯示資料的最後更新時間（來自 SYS_DATE 欄位）。

#### Scenario: 顯示更新時間
- **WHEN** 資料載入完成
- **THEN** 系統在頁面右上角顯示「最後更新: YYYY-MM-DD HH:MM:SS」
