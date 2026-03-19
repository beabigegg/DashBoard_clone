## 1. MySQL 基礎設施

- [x] 1.1 在 `environment.yml` 的 `pip:` 區塊新增 `pymysql` 依賴
- [x] 1.2 在 `.env.example` 新增 `MYSQL_OPS_HOST`、`MYSQL_OPS_PORT`、`MYSQL_OPS_USER`、`MYSQL_OPS_PASSWORD`、`MYSQL_OPS_DATABASE`、`MYSQL_OPS_ENABLED` 變數模板
- [x] 1.3 在 `.env` 填入實際 MySQL 連線資訊
- [x] 1.4 建立 `src/mes_dashboard/core/mysql_client.py`：
  - `create_mysql_engine()` — 從環境變數讀取設定，建立 SQLAlchemy engine（pool_size=3, max_overflow=2, pool_pre_ping=True, pool_recycle=1800）
  - `get_mysql_engine()` — 全域 singleton
  - `get_mysql_connection()` — context manager，yield connection
  - `check_mysql_health()` — SELECT 1 健康檢查
  - `MYSQL_OPS_ENABLED` — 全域開關旗標
  - `dispose_mysql_engine()` — shutdown 時清理

## 2. MySQL Schema 初始化

- [x] 2.1 建立 `scripts/init_mysql.py`：
  - 連線 MySQL 並建立 `dashboard_logs` 表（含 `sync_id` UNIQUE INDEX、`timestamp` INDEX、`level` INDEX）
  - 建立 `dashboard_metrics_snapshots` 表（含 `sync_id` UNIQUE INDEX、`ts` INDEX）
  - 冪等執行（`CREATE TABLE IF NOT EXISTS`）
  - 可直接以 `python scripts/init_mysql.py` 執行
- [x] 2.2 手動執行 `init_mysql.py` 驗證表建立成功

## 3. SQLite Schema 升級

- [x] 3.1 修改 `core/log_store.py`：
  - `CREATE_TABLE_SQL` 新增 `synced INTEGER DEFAULT 0` 欄位
  - `initialize()` 新增 ALTER TABLE migration（容忍 column 已存在）
  - 新增 `_generate_sync_id(rowid)` 方法（格式：`{hostname}_logs_{rowid}`）
  - `write_log()` 寫入時自動填入 sync_id
  - `query_logs()` 加入 `WHERE synced=0` 條件（只返回未同步資料給 local query）
  - 新增 `query_logs_all()` 方法（含 synced 資料，供合併查詢使用時取 unsynced 部分）
  - 新增 `get_unsynced(batch_size=500)` — 取未同步記錄
  - 新增 `mark_synced(rowids: List[int])` — 批次標記 synced=1
  - 新增 `cleanup_synced(older_than_hours=1)` — 清除已同步的舊記錄
- [x] 3.2 修改 `core/metrics_history.py`：
  - 同 3.1 的模式：新增 `synced`、`sync_id` 欄位
  - ALTER TABLE migration
  - `_generate_sync_id(rowid)` 方法
  - `write_snapshot()` 自動填入 sync_id
  - `query_snapshots_aggregated()` 加入 `WHERE synced=0` 條件
  - 新增 `get_unsynced(batch_size=500)`
  - 新增 `mark_synced(rowids)`
  - 新增 `cleanup_synced(older_than_hours=1)`
- [x] 3.3 更新 `tests/test_log_store.py`：適配 synced 欄位、驗證 get_unsynced/mark_synced/cleanup_synced
- [x] 3.4 更新 `tests/test_metrics_history.py`：同上
- [x] 3.5 確認 `tests/test_watchdog_logging.py` 仍通過（import 鏈不變）

## 4. Sync Worker

- [x] 4.1 建立 `src/mes_dashboard/core/sync_worker.py`：
  - `SyncWorker` class — daemon thread，間隔 10 分鐘（可設 `SYNC_WORKER_INTERVAL` 環境變數）
  - `_sync_logs()` — 從 LogStore.get_unsynced() 取批次 → INSERT IGNORE 至 MySQL dashboard_logs → LogStore.mark_synced()
  - `_sync_metrics()` — 同上，MetricsHistoryStore → dashboard_metrics_snapshots
  - `_cleanup_synced()` — 呼叫 LogStore.cleanup_synced() + MetricsHistoryStore.cleanup_synced()
  - `_run()` loop — sync_logs → sync_metrics → cleanup_synced（每次循環），錯誤時 log warning 但不中斷
  - `start()` / `stop()` 生命週期管理
  - MySQL 離線容錯：連線失敗時 log warning、跳過本輪 sync、下輪自動 retry
- [x] 4.2 建立 `tests/test_sync_worker.py`：
  - 測試正常 sync 流程（SQLite → MySQL → mark synced）
  - 測試 MySQL 離線時 graceful fallback
  - 測試 crash recovery（重複 INSERT IGNORE 不報錯）
  - 測試 cleanup_synced 正確清除已同步記錄

## 5. Admin API 合併查詢

- [x] 5.1 修改 `routes/admin_routes.py` 的 `api_logs()`：
  - 若 MYSQL_OPS_ENABLED：查 SQLite unsynced + 查 MySQL dashboard_logs → Python merge sort by timestamp DESC → 取前 limit 筆（預設 1000）
  - 若 MYSQL_OPS_DISABLED：維持現有純 SQLite 查詢
  - `total` count 合併兩邊
- [x] 5.2 修改 `routes/admin_routes.py` 的 `api_performance_history()`：
  - 若 MYSQL_OPS_ENABLED：查 SQLite unsynced 聚合 + 查 MySQL 聚合（MySQL 語法版本）→ Python merge by ts ASC
  - 若 MYSQL_OPS_DISABLED：維持現有純 SQLite 查詢
- [x] 5.3 修改 `routes/admin_routes.py` 的 `api_storage_info()`：
  - 新增 MySQL 統計區塊（dashboard_logs row count、dashboard_metrics_snapshots row count、MySQL 連線狀態）
- [x] 5.4 修改 `routes/admin_routes.py` 的 `api_logs_cleanup()`：
  - 新增選項支援同時清理 MySQL 資料（可選參數 `include_mysql=true`）

## 6. App 啟動整合

- [x] 6.1 修改 `app.py`：
  - import mysql_client、sync_worker
  - 在 `create_app()` 中：若 MYSQL_OPS_ENABLED，初始化 MySQL engine + 建表（冪等）+ 啟動 SyncWorker
  - 在 shutdown hook 中：stop SyncWorker + dispose MySQL engine
- [x] 6.2 確認 `rq_worker_preload.py` 不受影響（worker 預載不需要 sync worker）

## 7. 端到端驗證

- [x] 7.1 安裝 pymysql 依賴（`conda env update` 或 `pip install pymysql`）
- [x] 7.2 執行 `python scripts/init_mysql.py` 建表
- [x] 7.3 啟動 app，確認 MySQL engine 初始化成功、SyncWorker 啟動
- [x] 7.4 產生一些 log，等待 sync（或手動觸發），確認 MySQL 有資料
- [x] 7.5 Admin API `/admin/api/logs` 確認合併查詢正常
- [x] 7.6 Admin API `/admin/api/performance-history` 確認合併查詢正常
- [x] 7.7 模擬 MySQL 離線（設 MYSQL_OPS_ENABLED=false 或斷連），確認系統降級為純 SQLite 模式
- [x] 7.8 執行全部測試 `pytest tests/ -v` 確認無 regression
