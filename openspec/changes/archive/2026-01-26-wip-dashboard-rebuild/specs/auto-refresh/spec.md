## ADDED Requirements

### Requirement: 自動刷新間隔

系統 SHALL 每 10 分鐘自動刷新 Dashboard 資料。

#### Scenario: 自動刷新觸發
- **WHEN** 頁面載入後經過 10 分鐘
- **THEN** 系統自動呼叫 API 取得最新資料
- **AND** 更新頁面顯示
- **AND** 持續每 10 分鐘重複此行為

### Requirement: 無縫更新

系統 SHALL 在刷新時不重新載入整個頁面，只更新變化的資料區塊。

#### Scenario: 數值更新
- **WHEN** 自動刷新取得新資料
- **AND** 某個 KPI 數值有變化
- **THEN** 系統只更新該數值的 DOM 元素
- **AND** 使用 CSS transition 顯示數值變化效果（0.3s fade）
- **AND** 頁面不閃爍、不跳動

#### Scenario: 表格資料更新
- **WHEN** 自動刷新取得新資料
- **AND** 表格有新增或刪除的列
- **THEN** 系統使用 fade in/out animation 處理列的增刪
- **AND** 已存在的列只更新變化的欄位

### Requirement: 更新時間同步

系統 SHALL 在每次刷新後更新「最後更新」時間顯示。

#### Scenario: 更新時間顯示
- **WHEN** 自動刷新完成
- **THEN** 系統更新右上角的「最後更新」時間為新資料的 sys_date

### Requirement: 刷新狀態指示

系統 SHALL 在刷新過程中顯示subtle loading indicator。

#### Scenario: 刷新中狀態
- **WHEN** 系統開始呼叫 API 取得新資料
- **THEN** 系統在「最後更新」旁顯示小型 spinner 或 loading dot
- **AND** spinner 不應遮蔽內容或干擾使用者操作

#### Scenario: 刷新完成狀態
- **WHEN** API 回應成功
- **THEN** 系統隱藏 loading indicator
- **AND** 可選：顯示短暫的 success feedback（如綠色 checkmark，1秒後消失）

### Requirement: 錯誤處理

系統 SHALL 在刷新失敗時優雅處理，不影響使用者查看現有資料。

#### Scenario: API 錯誤
- **WHEN** 自動刷新 API 呼叫失敗
- **THEN** 系統保留現有資料顯示
- **AND** 在「最後更新」旁顯示 subtle 錯誤提示（如紅色 dot）
- **AND** 下次刷新時間仍按 10 分鐘計算

### Requirement: 手動刷新

系統 SHALL 提供手動刷新按鈕，讓使用者可以立即取得最新資料。

#### Scenario: 手動刷新
- **WHEN** 使用者點擊刷新按鈕
- **THEN** 系統立即呼叫 API 取得最新資料
- **AND** 重置 10 分鐘自動刷新計時器

### Requirement: 頁面可見性處理

系統 SHALL 在頁面不可見時暫停自動刷新，恢復可見時立即刷新。

#### Scenario: 頁面隱藏
- **WHEN** 使用者切換到其他分頁或最小化視窗
- **THEN** 系統暫停自動刷新計時器

#### Scenario: 頁面恢復
- **WHEN** 使用者返回該分頁
- **THEN** 系統立即執行一次刷新
- **AND** 重新啟動 10 分鐘自動刷新計時器
