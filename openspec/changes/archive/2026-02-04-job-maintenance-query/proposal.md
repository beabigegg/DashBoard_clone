## Why

使用者需要查詢特定設備的維修工單歷史紀錄，目前系統缺乏專門的介面來查詢 DW_MES_JOB 和 DW_MES_JOBTXNHISTORY 資料。此工具讓維護工程師能夠：選擇單一或多台設備、指定時間範圍，查看工單清單及其完整的狀態變更軌跡，並匯出完整的交易歷史資料供分析。

## What Changes

- 新增「設備維修查詢工具」頁面 (`/job-query`)
- 新增設備選擇器，使用 resource_cache 快取的設備資料
- 新增工單查詢 API：透過 RESOURCEID 關聯 DW_MES_JOB
- 新增工單交易歷史 API：透過 JOBID 關聯 DW_MES_JOBTXNHISTORY
- 新增 CSV 匯出功能：完整匯出到 JOBTXNHISTORY 層級（扁平化格式）
- 新增集中管理的 SQL 檔案 (`sql/job_query/`)

## Capabilities

### New Capabilities

- `job-maintenance-query`: 設備維修工單查詢功能，包含設備選擇、時間範圍篩選、工單列表顯示、交易歷史展開、CSV 匯出

### Modified Capabilities

(無修改既有規格)

## Impact

**新增檔案**:
- `src/mes_dashboard/templates/job_query.html` - 前端頁面
- `src/mes_dashboard/routes/job_query_routes.py` - API 端點
- `src/mes_dashboard/services/job_query_service.py` - 查詢邏輯
- `src/mes_dashboard/sql/job_query/*.sql` - SQL 查詢檔案

**依賴**:
- `resource_cache` - 設備快取資料 (既有)
- `DWH.DW_MES_JOB` - 維修工單表 (~125 萬筆)
- `DWH.DW_MES_JOBTXNHISTORY` - 工單交易歷史 (~955 萬筆)

**資料關聯**:
```
RESOURCE (RESOURCEID) → JOB (RESOURCEID) → JOBTXNHISTORY (JOBID)
```
