## 1. 後端時間戳正規化

- [x] 1.1 在 `src/mes_dashboard/core/log_store.py` 新增 helper `_normalize_iso_to_utc(value)`：接受 `datetime` 物件或字串，naive 視為伺服器本地時區，回傳 `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` 字串
- [x] 1.2 修改 `LogStore.write_log()`（[log_store.py:205](src/mes_dashboard/core/log_store.py#L205)）改用 `datetime.now(timezone.utc).isoformat()` 寫入
- [x] 1.3 `query_logs` / `query_logs_all` 在組裝回傳 dict 前對 `timestamp` 欄位呼叫 `_normalize_iso_to_utc`
- [x] 1.4 在 `src/mes_dashboard/routes/admin_routes.py:_query_mysql_logs` 把 SQL 結果的 `timestamp` 轉成 `_normalize_iso_to_utc(...)`（共用 helper 或就地實作）
- [x] 1.5 修改 `api_logs`（admin_routes.py:248-293）合併排序 key：`datetime.fromisoformat(r["timestamp"])`，無法解析時 fallback `datetime.min.replace(tzinfo=timezone.utc)`
- [x] 1.6 為 `_normalize_iso_to_utc` 與 `api_logs` 排序加單元測試（含 naive、aware、`datetime` 物件、不可解析字串四種輸入）

## 2. 前端共用 datetime formatter

- [x] 2.1 確認 `frontend/src/core/datetime.js` 是否存在；不存在則新建
- [x] 2.2 在該檔匯出 `formatLogTime(iso)`：使用 cached `Intl.DateTimeFormat('zh-TW', { hour12:false, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' })`
- [x] 2.3 對 `null` / `undefined` / 空字串回傳 `'-'`；對非可解析字串回傳原值
- [x] 2.4 加 vitest 單元測試覆蓋有效 ISO、naive ISO、null、亂碼

## 3. LogsTab 接管 log 檔案與 archive

- [x] 3.1 在 `frontend/src/admin-dashboard/tabs/LogsTab.vue` import `useStorageInfo` 與 `formatLogTime`
- [x] 3.2 從 WorkerTab 搬移 `cleanupLogFiles(targets)` 函式與相關 `storagePurging` ref 到 LogsTab
- [x] 3.3 LogsTab 新增「Log 檔案」SectionCard：DataTable 渲染 `storageInfo.log_files` + 「清空 Log 檔案」按鈕（呼叫 `cleanupLogFiles(['logs'])`）
- [x] 3.4 LogsTab 新增「Archive 歷史檔」SectionCard：DataTable 渲染 `storageInfo.archive_files` + 「清空 Archive」按鈕，僅在 `archive_files.length > 0` 時顯示
- [x] 3.5 LogsTab 結構化日誌表格的 `timestamp` cell 改用 `formatLogTime(value)` 顯示
- [x] 3.6 LogsTab `refresh()` 同時 refresh `logsHook` 與 `storageHook`

## 4. WorkerTab 瘦身

- [x] 4.1 移除 `frontend/src/admin-dashboard/tabs/WorkerTab.vue` 中 `Log 檔案` DataTable（lines ~440-450）
- [x] 4.2 移除 `Archive` DataTable 與整個 `storage-actions` 按鈕區塊（lines ~452-478）
- [x] 4.3 移除 `cleanupLogFiles` 函式與相關 import（保留 `purgeMetricsHistory`）
- [x] 4.4 SectionCard 標題 `儲存空間管理` 改為 `效能快照儲存`
- [x] 4.5 `workerStartTimeDisplay` 改用 `formatLogTime(workerData.value?.worker_start_time)`，移除舊的 `try/catch + toLocaleString` 邏輯
- [x] 4.6 確認 `useStorageInfo` 仍保留（給 SQLite 區塊用）

## 5. 測試調整

- [x] 5.1 更新 [tests/test_log_store.py:111](tests/test_log_store.py#L111), [:188](tests/test_log_store.py#L188), [:357](tests/test_log_store.py#L357) 的 fixture：改用 `datetime.now(timezone.utc).isoformat()` 或保留 naive 以覆蓋 read-side normalization
- [x] 5.2 在 `tests/test_log_store.py` 新增 `TestLogStoreTimestampNormalization`：覆蓋 `_normalize_iso_to_utc` 四種輸入（naive str、aware str、`datetime` 物件、亂碼）
- [x] 5.3 在 `tests/test_log_store.py` 新增測試：插入一筆 naive timestamp 直接寫入 SQLite，呼叫 `query_logs` 確認回傳值帶 `+00:00` 後綴
- [x] 5.4 在 `tests/e2e/test_admin_dashboard_e2e.py` 新增 `TestAdminDashboardLogs` class：呼叫 `/admin/api/logs?limit=5`；若 200，對 `data.logs[].timestamp` 以 regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$` 斷言
- [x] 5.5 在同檔新增 `TestAdminLogCleanup` class：對 `/admin/api/log-files/cleanup` 與 `/admin/api/logs/cleanup` 的 POST 做 accessibility 檢查（status in 200/302/401/403）
- [x] 5.6 新增 `frontend/tests/datetime.test.js`（node:test）：覆蓋 `formatLogTime` 有效 ISO / naive ISO / null / 亂碼
- [x] 5.7 新增 merged-sort 單元測試（放 `tests/test_admin_routes_logs.py` 或擴充既有檔）：mock `log_store.query_logs_all` 與 `_query_mysql_logs` 回傳跨格式的同分鐘時間戳，驗證合併後順序符合 datetime 排序

## 6. 驗證

- [x] 6.1 執行 `pytest tests/test_log_store.py tests/test_admin_routes_logs.py -v`
- [x] 6.2 執行 `pytest tests/e2e/test_admin_dashboard_e2e.py -v --run-e2e`
- [x] 6.3 執行 `node --test frontend/tests/datetime.test.js frontend/tests/admin-dashboard.test.js`
- [x] 6.4 `./scripts/start_server.sh start` 後手動測試：登入 admin → 切到 Logs tab，確認三個 SectionCard 都顯示且時間欄位為 `YYYY/MM/DD HH:mm:ss`
- [x] 6.5 切到 Worker tab，確認沒有 `.log` / archive 區塊，只剩效能快照儲存
- [x] 6.6 點擊「清理日誌」、「清空 Log 檔案」、「清空 Archive」三顆按鈕，確認皆成功並有 toast/alert 回饋
- [x] 6.7 用 `curl -s http://localhost:5000/admin/api/logs?limit=5 | jq '.data.logs[].timestamp'` 確認所有 timestamp 結尾為 `+00:00`
