## Why

目前系統使用 SQLite 儲存 admin log 和 metrics history（`logs/admin_logs.sqlite`、`logs/metrics_history.sqlite`），作為本地檔案型 DB 運作良好，但即將新增登入紀錄、操作稽核、權限卡控等功能，需要集中式資料庫支撐。公司既有 MySQL 服務可用但目前專案未接入。

現有 SQLite 的限制：
- 多機部署時無法集中查詢
- 無法支撐未來的 login/audit/access control 需求
- 多 Gunicorn worker 寫入同一檔案需要 threading.Lock 序列化

## What Changes

採用 **雙層架構（Dual-Layer）**：SQLite 作為本地寫入緩衝 + 容錯層，MySQL 作為持久化集中儲存層。

- **寫入路徑不變**：應用程式仍然同步寫入 SQLite（零延遲），不影響 request path
- **新增 Sync Worker**：背景 daemon thread 每 10 分鐘將 SQLite 資料批次同步至 MySQL
- **容錯機制**：MySQL 離線時資料安全保留在 SQLite，下次 sync 自動 retry
- **同步後清理**：成功同步的資料標記 `synced=1`，定期清除以節省空間
- **查詢合併**：Admin API 查詢時合併 SQLite（未同步）+ MySQL（歷史）資料，預設 1000 筆
- **新增 MySQL 連線層**：獨立的 MySQL engine（SQLAlchemy），與現有 Oracle engine 分離
- **Schema 前綴**：所有新表使用 `dashboard_` 前綴，避免影響共用資料庫中的其他表

## Capabilities

### New Capabilities
- `mysql-ops-engine`: MySQL 連線管理 — SQLAlchemy engine、連線池、環境變數設定、健康檢查
- `sqlite-mysql-sync`: 雙層同步機制 — 背景 sync worker、批次 INSERT、冪等去重、sync 狀態追蹤、容錯 retry
- `dual-layer-query`: 合併查詢 — SQLite unsynced + MySQL historical 資料合併、排序、分頁

### Modified Capabilities
- `log-store`: LogStore 新增 `synced` 欄位、調整 query 邏輯支援合併查詢
- `metrics-history`: MetricsHistoryStore 新增 `synced` 欄位、聚合 SQL 支援 MySQL 語法
- `admin-api`: Admin routes 查詢改為雙層合併、storage-info 加入 MySQL 統計

## Impact

- **後端新增 2 個模組**：`core/mysql_client.py`（MySQL 連線管理）、`core/sync_worker.py`（同步引擎）
- **後端修改 3 個模組**：`core/log_store.py`、`core/metrics_history.py`、`routes/admin_routes.py`
- **修改 1 個啟動檔**：`app.py`（初始化 MySQL engine + 啟動 sync worker）
- **新增 1 個腳本**：`scripts/init_mysql.py`（MySQL schema 初始化）
- **環境變數新增**：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`
- **新增依賴**：`PyMySQL`（pip 套件）
- **測試更新**：3 個既有 test 檔需適配、新增 sync worker 測試
- **部署影響**：需確保 MySQL 連線可達；MySQL 離線時系統降級為純 SQLite 模式（現有行為）
