## Context

系統目前有兩個 SQLite 資料庫：
- `logs/admin_logs.sqlite` — `logs` 表，由 `LogStore` + `SQLiteLogHandler` 寫入，admin API 查詢
- `logs/metrics_history.sqlite` — `metrics_snapshots` 表，由 `MetricsHistoryCollector` daemon thread 每 30s 寫入，admin API 查詢

現有基礎設施：
- Oracle（SQLAlchemy QueuePool）— business data
- Redis — caching layer
- MySQL（外部既有）— `mysql.theaken.com:33306`，database `db_A060`，目前未使用

目標：SQLite 保留為本地寫入緩衝 + 容錯，新增 MySQL 作為持久化集中儲存。

## Goals / Non-Goals

**Goals:**
- 所有 log/metrics 寫入仍走 SQLite（零延遲，不影響 request path）
- 背景 sync worker 每 10 分鐘將 SQLite 資料批次同步至 MySQL
- MySQL 離線時資料安全保留在 SQLite，自動 retry
- Admin API 查詢合併兩層資料，預設 1000 筆
- MySQL 表使用 `dashboard_` 前綴
- 為未來 login/audit/access control 鋪路

**Non-Goals:**
- 即時寫入 MySQL（會增加 request path 延遲）
- 移除 SQLite（保留作為 buffer + fallback）
- 遷移既有歷史資料（SQLite 資料只有 3-7 天，不需要 data migration）
- Login/audit 表的實作（本次只建立 MySQL 基礎設施）

## Decisions

### Decision 1: SQLite 同步狀態追蹤

**選擇：`synced` 欄位標記法**

SQLite 表新增 `synced INTEGER DEFAULT 0` 欄位：
- 寫入時 `synced=0`（未同步）
- sync 成功後 `UPDATE SET synced=1`
- 定期清除 `synced=1 AND timestamp < 1hr ago` 的記錄

**替代方案：sync 後直接 DELETE** — crash 時可能丟資料（INSERT MySQL 成功、DELETE SQLite 前斷電），恢復後無法 retry。

**理由：** synced 欄位提供 crash recovery 窗口，且讓 query 時可精確排除已同步資料。

### Decision 2: MySQL 冪等寫入

**選擇：`INSERT IGNORE` + `sync_id` 唯一鍵**

每筆 SQLite 記錄生成 `sync_id`（格式：`{hostname}_{sqlite_table}_{sqlite_rowid}`），MySQL 表以 `sync_id` 建立 UNIQUE INDEX。

- 正常流程：INSERT 成功 → 標記 synced=1
- Crash recovery：重新 INSERT → `INSERT IGNORE` 跳過已存在的 → 再標記 synced=1
- 保證冪等，無重複資料

**替代方案：先 SELECT 檢查是否存在** — 多一次 round trip，批次場景效能差。

### Decision 3: 連線管理

**選擇：獨立 SQLAlchemy engine for MySQL**

```python
# core/mysql_client.py
mysql_engine = create_engine(
    f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
    pool_size=3,
    max_overflow=2,
    pool_recycle=1800,
    pool_pre_ping=True,  # 自動重連
)
```

- 與 Oracle engine 完全分離，互不影響
- pool_size=3 足夠（sync worker + admin query，低頻使用）
- pool_pre_ping=True 處理 MySQL 斷線重連

**替代方案：裸 PyMySQL** — 需自行管理連線池和重連，不值得。

### Decision 4: Admin API 合併查詢策略

**選擇：Python 層合併（兩邊各 query 再 merge sort）**

```
1. SQLite: SELECT * FROM logs WHERE synced=0 ORDER BY timestamp DESC
2. MySQL:  SELECT * FROM dashboard_logs ORDER BY timestamp DESC LIMIT 1000
3. Python: merge sort by timestamp DESC, take first 1000
```

**替代方案：FDW / linked server** — SQLite 和 MySQL 之間沒有 federated query 機制。

**理由：** 兩個 DB engine 無法做跨 DB SQL，Python 合併是唯一可行方案且邏輯簡單。

### Decision 5: timestamp 儲存格式

**選擇：MySQL 用 `DATETIME(3)` + SQLite 維持 ISO TEXT**

- MySQL `DATETIME(3)` 支援毫秒精度，無 2038 問題
- SQLite 繼續用 ISO text（現有行為不變）
- Sync 時 Python 層轉換：`datetime.fromisoformat(sqlite_ts)` → MySQL DATETIME

### Decision 6: Sync Worker 生命週期

**選擇：與 MetricsHistoryCollector 相同模式 — daemon thread in app process**

```python
class SyncWorker:
    def __init__(self, interval=600):  # 10 minutes
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop_event.wait(self.interval):
            self._sync_logs()
            self._sync_metrics()
            self._cleanup_synced()
```

- 在 `app.py` 的 `create_app()` 中啟動，和 MetricsHistoryCollector 一起
- daemon thread 隨主 process 結束自動退出
- 各 Gunicorn worker 各自 sync 自己的 SQLite（每個 worker 有獨立 SQLite 檔案路徑，或共用時以 write_lock 保護 sync）

### Decision 7: MySQL Schema（`dashboard_` 前綴）

```sql
-- dashboard_logs（對應 SQLite logs 表）
CREATE TABLE IF NOT EXISTS dashboard_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_id VARCHAR(255) NOT NULL,
    timestamp DATETIME(3) NOT NULL,
    level VARCHAR(20) NOT NULL,
    logger_name VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    request_id VARCHAR(100),
    user VARCHAR(255),
    ip VARCHAR(45),
    extra TEXT,
    synced_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE INDEX idx_sync_id (sync_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_level (level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- dashboard_metrics_snapshots（對應 SQLite metrics_snapshots 表）
CREATE TABLE IF NOT EXISTS dashboard_metrics_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_id VARCHAR(255) NOT NULL,
    ts DATETIME(3) NOT NULL,
    worker_pid INT NOT NULL,
    pool_saturation DOUBLE,
    pool_checked_out INT,
    pool_checked_in INT,
    pool_overflow INT,
    pool_max_capacity INT,
    redis_used_memory BIGINT,
    redis_hit_rate DOUBLE,
    rc_l1_hit_rate DOUBLE,
    rc_l2_hit_rate DOUBLE,
    rc_miss_rate DOUBLE,
    latency_p50_ms DOUBLE,
    latency_p95_ms DOUBLE,
    latency_p99_ms DOUBLE,
    latency_count INT,
    slow_query_active INT,
    slow_query_waiting INT,
    worker_rss_bytes BIGINT,
    system_mem_available_mb DOUBLE,
    system_mem_used_pct DOUBLE,
    rq_workers_total INT,
    rq_workers_busy INT,
    rq_queue_depth INT,
    heavy_query_slots_active INT,
    synced_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE INDEX idx_sync_id (sync_id),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Decision 8: Metrics 聚合 SQL 的 MySQL 版本

SQLite 現有語法：
```sql
datetime(
    (CAST(strftime('%s', ts, 'utc') AS INTEGER) / :bucket) * :bucket,
    'unixepoch', 'localtime'
) AS ts
```

MySQL 對應：
```sql
FROM_UNIXTIME(
    FLOOR(UNIX_TIMESTAMP(ts) / :bucket) * :bucket
) AS ts
```

聚合 query 需要支援兩種 dialect：
- 查 SQLite unsynced 資料用 SQLite 語法
- 查 MySQL 歷史資料用 MySQL 語法
- Python 層合併結果

### Decision 9: 環境變數與容錯

```
MYSQL_OPS_HOST=mysql.theaken.com
MYSQL_OPS_PORT=33306
MYSQL_OPS_USER=A060
MYSQL_OPS_PASSWORD=WLeSCi0yhtc7
MYSQL_OPS_DATABASE=db_A060
MYSQL_OPS_ENABLED=true
```

使用 `MYSQL_OPS_` 前綴區分於未來可能的其他 MySQL 連線。

`MYSQL_OPS_ENABLED=false` 時：
- Sync worker 不啟動
- Admin API 只查 SQLite（現有行為）
- 系統完全降級為純 SQLite 模式

## File Changes

### New Files
| File | Purpose |
|------|---------|
| `src/mes_dashboard/core/mysql_client.py` | MySQL SQLAlchemy engine、連線池管理、健康檢查 |
| `src/mes_dashboard/core/sync_worker.py` | 雙層同步引擎（SQLite → MySQL）、cleanup、retry |
| `scripts/init_mysql.py` | MySQL schema 初始化腳本（建表 + 索引） |
| `tests/test_sync_worker.py` | Sync worker 單元測試 |

### Modified Files
| File | Changes |
|------|---------|
| `src/mes_dashboard/core/log_store.py` | 新增 `synced` 欄位到 schema、新增 `sync_id` 生成、query 時排除 synced=1、新增 `get_unsynced()` / `mark_synced()` 方法 |
| `src/mes_dashboard/core/metrics_history.py` | 同上：`synced` 欄位、`sync_id`、`get_unsynced()` / `mark_synced()`；聚合 query 排除 synced |
| `src/mes_dashboard/routes/admin_routes.py` | `api_logs()` 合併雙層查詢；`api_performance_history()` 合併雙層查詢；`api_storage_info()` 加入 MySQL 統計 |
| `src/mes_dashboard/app.py` | 初始化 MySQL engine + 啟動 SyncWorker |
| `.env.example` | 新增 `MYSQL_OPS_*` 變數 |
| `environment.yml` | pip 區塊新增 `pymysql` |
| `tests/test_log_store.py` | 適配 synced 欄位 |
| `tests/test_metrics_history.py` | 適配 synced 欄位 |
| `tests/test_watchdog_logging.py` | 確認 import 鏈不受影響 |
