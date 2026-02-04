## ADDED Requirements

### Requirement: Equipment selection from cache
系統 SHALL 從 resource_cache 載入可用設備清單，讓使用者選擇要查詢的設備。

#### Scenario: Load equipment list
- **WHEN** 使用者進入設備維修查詢頁面
- **THEN** 系統顯示從 resource_cache 載入的設備清單，包含 RESOURCENAME 和 WORKCENTERNAME

#### Scenario: Multi-select equipment
- **WHEN** 使用者選擇多台設備
- **THEN** 系統記錄所選設備的 RESOURCEID 列表供後續查詢使用

---

### Requirement: Date range filter
系統 SHALL 提供日期範圍篩選功能，限制查詢的時間區間。

#### Scenario: Set date range
- **WHEN** 使用者指定起始日期和結束日期
- **THEN** 系統驗證日期格式為 YYYY-MM-DD 且結束日期不早於起始日期

#### Scenario: Date range limit
- **WHEN** 使用者選擇的日期範圍超過 365 天
- **THEN** 系統顯示錯誤訊息「日期範圍不可超過 365 天」

#### Scenario: Quick date preset
- **WHEN** 使用者點擊「最近 90 天」按鈕
- **THEN** 系統自動填入過去 90 天的日期範圍

---

### Requirement: Job list query
系統 SHALL 根據選擇的設備和時間範圍查詢工單清單 (DW_MES_JOB)。

#### Scenario: Query jobs by resources
- **WHEN** 使用者選擇設備並執行查詢
- **THEN** 系統查詢 DW_MES_JOB 表中 RESOURCEID 符合所選設備的工單

#### Scenario: Filter by date
- **WHEN** 使用者指定時間範圍
- **THEN** 系統篩選 CREATEDATE 在指定範圍內的工單

#### Scenario: Job list columns
- **WHEN** 工單查詢完成
- **THEN** 系統顯示欄位包含：RESOURCENAME, JOBID, JOBSTATUS, CREATEDATE, COMPLETEDATE, CAUSECODENAME, REPAIRCODENAME

---

### Requirement: Job transaction history detail
系統 SHALL 提供展開功能，顯示單一工單的完整交易歷史 (DW_MES_JOBTXNHISTORY)。

#### Scenario: Expand job history
- **WHEN** 使用者點擊工單列的展開按鈕
- **THEN** 系統查詢該 JOBID 的所有 JOBTXNHISTORY 記錄並顯示

#### Scenario: History detail columns
- **WHEN** 交易歷史載入完成
- **THEN** 系統顯示欄位包含：TXNDATE, FROMJOBSTATUS, JOBSTATUS, CAUSECODENAME, REPAIRCODENAME, USER_NAME

#### Scenario: History ordering
- **WHEN** 顯示交易歷史
- **THEN** 記錄依 TXNDATE 升序排列 (最早的在前)

---

### Requirement: CSV export with full history
系統 SHALL 提供 CSV 匯出功能，匯出完整到 JOBTXNHISTORY 層級的扁平化資料。

#### Scenario: Export request
- **WHEN** 使用者點擊「匯出 CSV」按鈕
- **THEN** 系統產生包含所有符合條件的工單及其交易歷史的 CSV 檔案

#### Scenario: Export format
- **WHEN** CSV 匯出完成
- **THEN** 檔案格式為 UTF-8 BOM，每筆交易歷史為一列，包含對應的工單資訊

#### Scenario: Export columns
- **WHEN** 檢視匯出的 CSV 內容
- **THEN** 欄位包含：RESOURCENAME, JOBID, JOB_STATUS, JOB_CREATEDATE, TXN_DATE, FROM_STATUS, TO_STATUS, CAUSE_CODE, REPAIR_CODE, USER_NAME

---

### Requirement: Large dataset handling
系統 SHALL 處理大量設備選擇時的查詢效能問題。

#### Scenario: Batch resource filter
- **WHEN** 所選設備數量超過 1000 台
- **THEN** 系統將 RESOURCEID 分批處理，每批最多 1000 個

#### Scenario: Export timeout prevention
- **WHEN** 匯出大量資料
- **THEN** 系統使用串流回應 (streaming response) 避免超時

---

### Requirement: Page navigation
系統 SHALL 將設備維修查詢工具整合至主導航選單。

#### Scenario: Access from menu
- **WHEN** 使用者點擊導航選單中的「設備維修查詢」
- **THEN** 系統導航至 /job-query 頁面
