## 1. SQL 檔案

- [x] 1.1 建立 `sql/job_query/` 目錄
- [x] 1.2 建立 `job_list.sql` - 工單清單查詢 (JOB 層級)
- [x] 1.3 建立 `job_txn_detail.sql` - 單一工單的交易歷史查詢
- [x] 1.4 建立 `job_txn_export.sql` - 完整匯出查詢 (JOB JOIN JOBTXNHISTORY)

## 2. Service 層

- [x] 2.1 建立 `services/job_query_service.py`
- [x] 2.2 實作 `get_jobs_by_resources()` - 根據 RESOURCEID 列表查詢工單
- [x] 2.3 實作 `get_job_txn_history()` - 根據 JOBID 查詢交易歷史
- [x] 2.4 實作 `export_jobs_with_history()` - 產生完整匯出的 CSV 串流
- [x] 2.5 實作日期範圍驗證 (最多 365 天)
- [x] 2.6 實作大量 RESOURCEID 分批處理 (每批 1000)

## 3. Routes 層

- [x] 3.1 建立 `routes/job_query_routes.py`
- [x] 3.2 實作 `POST /api/job-query/jobs` - 工單列表查詢
- [x] 3.3 實作 `GET /api/job-query/txn/<job_id>` - 工單交易歷史
- [x] 3.4 實作 `POST /api/job-query/export` - CSV 匯出 (streaming response)
- [x] 3.5 註冊 Blueprint 到 app

## 4. 前端頁面

- [x] 4.1 建立 `templates/job_query.html`
- [x] 4.2 實作設備選擇器 (從 resource_cache 載入，支援多選)
- [x] 4.3 實作日期範圍選擇器 (含「最近 90 天」快速按鈕)
- [x] 4.4 實作工單列表表格 (含分頁)
- [x] 4.5 實作工單列展開功能 (顯示交易歷史)
- [x] 4.6 實作 CSV 匯出按鈕
- [x] 4.7 實作查詢中 loading 狀態

## 5. 導航整合

- [x] 5.1 新增頁面路由 `/job-query`
- [x] 5.2 將「設備維修查詢」加入導航選單

## 6. 測試

- [x] 6.1 Service 層單元測試 (mock 資料庫)
- [x] 6.2 Routes 層 API 測試
- [x] 6.3 手動 E2E 測試 - 完整查詢流程
- [x] 6.4 手動 E2E 測試 - CSV 匯出驗證
