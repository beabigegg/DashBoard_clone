## Context

目前系統已有設備即時監控 (resource dashboard) 和設備歷史分析 (resource history) 功能，皆使用 `resource_cache` 作為設備主數據來源。維修工單資料存在於：
- `DW_MES_JOB` (~125萬筆) - 工單現況，有 RESOURCEID 可關聯設備
- `DW_MES_JOBTXNHISTORY` (~955萬筆) - 工單交易歷史，透過 JOBID 關聯

現有架構已建立的模式：
- SQL 檔案集中管理於 `sql/<module>/*.sql`
- 使用 `{{ PLACEHOLDER }}` 和 `:param` 參數化查詢
- `read_sql_df()` 搭配連線池執行查詢
- Service 層處理業務邏輯，Routes 層處理 HTTP

## Goals / Non-Goals

**Goals:**
- 提供設備維修工單查詢介面
- 支援單選/多選設備、時間範圍篩選
- 顯示兩層資料：JOB 清單 → JOBTXNHISTORY 明細
- 完整匯出到 JOBTXNHISTORY 層級 (扁平化 CSV)

**Non-Goals:**
- 不修改既有 resource_cache 功能
- 不整合至現有 dashboard (獨立頁面)
- 不提供工單編輯功能 (唯讀查詢)
- 不處理 JOB 以外的維護類型 (如 MAINTENANCE 表)

## Decisions

### 1. 資料關聯策略：兩階段查詢

**選擇**: 先查 JOB，再按需查 JOBTXNHISTORY

**替代方案**:
- 單次 JOIN 查詢：JOB 和 JOBTXNHISTORY 一次 JOIN 回傳
- 問題：JOBTXNHISTORY 資料量大，JOIN 會產生大量重複的 JOB 欄位

**理由**:
- 前端列表只需 JOB 層級，減少傳輸量
- 展開明細時才查 JOBTXNHISTORY，按需載入
- 匯出時使用單獨的 JOIN 查詢，一次產生扁平化資料

### 2. 設備選擇來源：使用 resource_cache

**選擇**: 從 `resource_cache.get_all_resources()` 取得設備清單

**替代方案**:
- 直接查詢 DW_MES_RESOURCE 表
- 問題：每次頁面載入都需查詢資料庫

**理由**:
- 與既有 resource_history 模式一致
- 利用快取減少資料庫負載
- 設備清單已有 RESOURCEID 可直接用於 JOB 關聯

### 3. SQL 管理：集中至 sql/job_query/

**選擇**: 新增 `sql/job_query/` 目錄存放 SQL 檔案

**檔案結構**:
```
sql/job_query/
├── job_list.sql         # 工單清單 (前端列表)
├── job_txn_detail.sql   # 單一工單的交易明細
└── job_txn_export.sql   # 完整匯出 (JOB JOIN HISTORY)
```

**理由**:
- 遵循專案既有的 SQL 集中管理模式
- 便於維護和優化 SQL

### 4. 匯出格式：扁平化 CSV

**選擇**: JOB + JOBTXNHISTORY 扁平化為單一 CSV

**欄位設計**:
```
RESOURCENAME, JOBID, JOB_STATUS, JOB_CREATEDATE,
TXN_DATE, FROM_STATUS, TO_STATUS, CAUSE_CODE, REPAIR_CODE, USER_NAME
```

**理由**:
- 使用者需求是完整到 history 層級
- 扁平化格式便於 Excel 分析
- 每筆交易一列，包含對應的 JOB 資訊

### 5. API 端點設計

| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/job-query/jobs` | POST | 查詢工單列表 |
| `/api/job-query/txn/{job_id}` | GET | 取得單一工單的交易歷史 |
| `/api/job-query/export` | POST | CSV 匯出 (完整到 history) |

**理由**:
- 列表查詢用 POST (帶 resource_ids 陣列)
- 明細查詢用 GET (單一 job_id)
- 匯出用 POST (同列表查詢參數)

## Risks / Trade-offs

### [風險] JOBTXNHISTORY 資料量大，匯出可能超時
**緩解**:
- 限制查詢時間範圍 (最多 365 天)
- 使用串流回應 (streaming response)
- 加入 TXNDATE 索引條件

### [風險] 多選大量設備時 IN 子句過長
**緩解**:
- 分批查詢 (每批 1000 個 RESOURCEID)
- 或使用 CTE 暫存設備清單

### [取捨] 前端不預載所有 JOBTXNHISTORY
**影響**: 展開明細需額外 API 呼叫
**優點**: 減少初始載入時間和傳輸量
