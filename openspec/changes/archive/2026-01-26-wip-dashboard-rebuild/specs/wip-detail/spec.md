## ADDED Requirements

### Requirement: WIP Detail Dashboard 頁面

系統 SHALL 提供 `/wip-detail` 路由，顯示產線用的單一工站 WIP 細部 Dashboard。

#### Scenario: 載入 Detail 頁面
- **WHEN** 使用者訪問 `/wip-detail?workcenter=焊接_DB`
- **THEN** 系統顯示該 WORKCENTER_GROUP 的 WIP 細部資訊

#### Scenario: 無參數訪問
- **WHEN** 使用者訪問 `/wip-detail` 不帶 workcenter 參數
- **THEN** 系統顯示第一個 WORKCENTER_GROUP（依 WORKCENTERSEQUENCE_GROUP 排序）的資料

### Requirement: 篩選器

系統 SHALL 提供篩選功能，包含：Package 下拉選單、Status 下拉選單。（Workcenter 不需要篩選，因為每個 WORKCENTER_GROUP 有獨立的 Detail 頁面）

#### Scenario: Package 篩選
- **WHEN** 使用者選擇特定 Package
- **THEN** 系統只顯示該 PRODUCTLINENAME 的 Lots

#### Scenario: Status 篩選
- **WHEN** 使用者選擇 Status（全部/Active/Hold）
- **THEN** 系統依 STATUS 欄位篩選顯示

### Requirement: 工站摘要卡片

系統 SHALL 在篩選器下方顯示 4 個摘要卡片：總 Lots、在機 Lots、待料 Lots、Hold Lots。

#### Scenario: 顯示工站摘要
- **WHEN** Detail 頁面載入完成
- **THEN** 系統顯示：
  - 總 Lots：該工站的 Lot 總數
  - 在機 Lots：EQUIPMENTNAME IS NOT NULL 的數量
  - 待料 Lots：EQUIPMENTNAME IS NULL 的數量
  - Hold Lots：STATUS = 'HOLD' 的數量

### Requirement: Lot 明細表格

系統 SHALL 顯示該工站的 Lot 明細表格，橫向展開 SPECNAME，並在對應 Spec 欄位顯示數量。

#### Scenario: 顯示 Lot 明細
- **WHEN** Detail 頁面載入資料
- **THEN** 系統顯示表格：
  - 固定欄位：LOTID、EQUIPMENTNAME（NULL 顯示「待料」）、STATUS（HOLD 顯示紅色 + HOLDREASONNAME）、PRODUCTLINENAME
  - 動態欄位：該工站的所有 SPECNAME（依 SPECSEQUENCE 排序）
  - Spec 欄位顯示該 Lot 的 QTY（千分位格式），非當前 Spec 的欄位留空

#### Scenario: Hold 狀態顯示
- **WHEN** Lot 的 STATUS = 'HOLD'
- **THEN** 系統以紅色顯示 Status 欄位
- **AND** 顯示括號內的 HOLDREASONNAME（如「Hold (YieldLimit)」）

#### Scenario: 表格分頁
- **WHEN** Lot 數量超過 100 筆
- **THEN** 系統顯示分頁控制項
- **AND** 每頁顯示 100 筆

### Requirement: 資料更新時間顯示

系統 SHALL 顯示資料的最後更新時間（來自 SYS_DATE 欄位）。

#### Scenario: 顯示更新時間
- **WHEN** 資料載入完成
- **THEN** 系統在頁面右上角顯示「最後更新: YYYY-MM-DD HH:MM:SS」
