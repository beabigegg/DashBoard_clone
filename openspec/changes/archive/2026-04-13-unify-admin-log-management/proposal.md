## Why

Admin Dashboard 目前有兩個分頁觸及「log」：WorkerTab 的「儲存空間管理」區塊負責 `.log` 檔與 `archive/` 的列表/清理，LogsTab 則顯示結構化日誌（SQLite + MySQL）並提供其專屬的清理按鈕。使用者很難分辨「清空 Log 檔案」與「清理日誌」的差別，且後端合併排序使用 `str(timestamp)` 比較會因 SQLite (`T` 分隔) 與 MySQL DATETIME (空白分隔) 格式不同而錯位，前端各頁面也用不同方式顯示時間戳。

## What Changes

- 把 LogsTab 擴充為唯一的 log 檢視/管理入口：包含結構化日誌表、`.log` 檔清單與清理、`archive/` 清單與清理。
- WorkerTab 移除「Log 檔案」與「Archive」兩個區塊與三顆清理按鈕，僅保留 `metrics_history.sqlite` 的效能快照儲存區，並把 SectionCard 標題改為「效能快照儲存」。
- 後端 `core/log_store.write_log()` 改用 `datetime.now(timezone.utc).isoformat()` 寫入 tz-aware UTC ISO 8601；讀取既有 naive 資料時假設為伺服器本地時區並轉為 UTC（不做 migration）。
- 後端 `routes/admin_routes._query_mysql_logs()` 把 MySQL 回傳的 timestamp 正規化為 UTC ISO 8601 字串。
- 後端 `api_logs` 合併排序改用 `datetime.fromisoformat()` 作為 key，修正跨來源排序錯誤。
- 前端新增/擴充 `frontend/src/core/datetime.js` 共用 `formatLogTime(iso)`，以 `toLocaleString('zh-TW')` 顯示為使用者本地時區；LogsTab 與 WorkerTab 的時間欄位皆改用此 formatter。
- `/admin/api/log-files/cleanup`、`/admin/api/logs/cleanup` 兩個 API 契約不變，只調整前端呼叫位置。

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `admin-dashboard-frontend`: LogsTab 範圍擴大、WorkerTab 範圍縮小、log timestamp 顯示與序列化規則統一。

## Impact

- **前端**：`frontend/src/admin-dashboard/tabs/LogsTab.vue`、`frontend/src/admin-dashboard/tabs/WorkerTab.vue`、`frontend/src/core/datetime.js`（新增或擴充）。
- **後端**：`src/mes_dashboard/core/log_store.py`、`src/mes_dashboard/routes/admin_routes.py`。
- **API**：契約不變；`/admin/api/logs` 回傳的 `timestamp` 欄位語意收斂為 UTC ISO 8601。
- **資料**：不做 migration，舊 naive timestamp 在讀取階段被視為本地時區轉 UTC。
- **使用者體驗**：log 管理路徑一致化；時間顯示在所有 admin 頁面統一為本地時區 `YYYY/MM/DD HH:mm:ss`。
- **測試**：
  - `tests/test_log_store.py` 既有 fixture 使用 `datetime.now().isoformat()` 寫入 naive 時間戳（lines 111/188/357），`write_log()` tz-aware 化後會產生新舊格式並存情境，需更新 assertion 以相容 `+00:00` 後綴；並新增 `_normalize_iso_to_utc` 與 legacy naive read-side normalization 的單元測試。
  - `tests/e2e/test_admin_dashboard_e2e.py` 既有 `TestAdminDashboardWorkerStatus` / `StorageInfo` / `PageLoad` / `SystemStatus`，但 **沒有** `/admin/api/logs` 與兩個 cleanup endpoint 的測試類別（雖模組 docstring 已列入 `/admin/api/logs`）。本變更補齊 `TestAdminDashboardLogs`，驗證 timestamp 欄位符合 `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$`；並新增 `TestAdminLogCleanup` 覆蓋 `/admin/api/log-files/cleanup` 與 `/admin/api/logs/cleanup` 的 accessibility。
  - `frontend/tests/admin-dashboard.test.js` 僅涵蓋 tab config 契約，不受影響；**新增** `frontend/tests/datetime.test.js` 為共用 `formatLogTime` 建立 vitest/node:test 單元測試（有效 ISO、naive ISO、null、亂碼四種輸入）。
  - 專案目前未對 WorkerTab/LogsTab 具備 Playwright browser e2e，不在本變更新增。
