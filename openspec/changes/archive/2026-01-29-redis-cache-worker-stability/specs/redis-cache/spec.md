## ADDED Requirements

### Requirement: Cache Updater Background Task

系統 SHALL 提供背景任務，定期檢查 Oracle `DW_PJ_LOT_V` 的 `SYS_DATE` 並更新 Redis 快取。

#### Scenario: SYS_DATE changed triggers cache update
- **WHEN** 背景任務執行時，Oracle 的 `SYS_DATE` 與 Redis 中儲存的版本不同
- **THEN** 系統 SHALL 載入整個 `DW_PJ_LOT_V` 表並存入 Redis
- **AND** 更新 `{prefix}:meta:sys_date` 為新的 SYS_DATE
- **AND** 更新 `{prefix}:meta:updated_at` 為當前時間

#### Scenario: SYS_DATE unchanged skips update
- **WHEN** 背景任務執行時，Oracle 的 `SYS_DATE` 與 Redis 中儲存的版本相同
- **THEN** 系統 SHALL 跳過快取更新
- **AND** 記錄 debug 日誌

#### Scenario: Background task runs at configured interval
- **WHEN** 應用程式啟動後
- **THEN** 背景任務 SHALL 每 `CACHE_CHECK_INTERVAL` 秒（預設 600 秒）執行一次

#### Scenario: Initial cache load on startup
- **WHEN** 應用程式啟動時 Redis 中無快取資料
- **THEN** 系統 SHALL 立即執行一次快取更新

---

### Requirement: Redis Data Storage

系統 SHALL 將 `DW_PJ_LOT_V` 表資料以 JSON 格式儲存於 Redis。

#### Scenario: Data stored with correct keys
- **WHEN** 快取更新完成後
- **THEN** Redis SHALL 包含以下 keys：
  - `{prefix}:meta:sys_date` - Oracle 資料的 SYS_DATE
  - `{prefix}:meta:updated_at` - 快取更新時間（ISO 8601 格式）
  - `{prefix}:data` - 完整表資料（JSON 陣列）

#### Scenario: Atomic update with pipeline
- **WHEN** 快取更新執行時
- **THEN** 系統 SHALL 使用 Redis pipeline 確保所有 keys 原子更新

---

### Requirement: Cache Read for WIP Queries

所有 WIP API 查詢 SHALL 優先從 Redis 快取讀取資料。

#### Scenario: Cache hit returns data from Redis
- **WHEN** API 收到 WIP 查詢請求且 Redis 快取可用
- **THEN** 系統 SHALL 從 Redis 讀取 `{prefix}:data`
- **AND** 使用 pandas 進行篩選/聚合計算
- **AND** 回傳計算結果

#### Scenario: Cache includes SYS_DATE in response
- **WHEN** API 從快取回傳資料
- **THEN** 回應 SHALL 包含 `dataUpdateDate` 欄位，值為快取的 SYS_DATE

---

### Requirement: Fallback to Oracle on Cache Miss

當 Redis 不可用或無快取資料時，系統 SHALL 自動降級到直接查詢 Oracle。

#### Scenario: Redis unavailable triggers fallback
- **WHEN** Redis 連線失敗或超時
- **THEN** 系統 SHALL 直接查詢 Oracle `DW_PJ_LOT_V`
- **AND** 記錄 warning 日誌

#### Scenario: Cache empty triggers fallback
- **WHEN** Redis 可用但 `{prefix}:data` 不存在
- **THEN** 系統 SHALL 直接查詢 Oracle `DW_PJ_LOT_V`

#### Scenario: REDIS_ENABLED=false disables cache
- **WHEN** 環境變數 `REDIS_ENABLED` 設為 `false`
- **THEN** 系統 SHALL 完全跳過 Redis，直接查詢 Oracle

---

### Requirement: Redis Connection Management

系統 SHALL 使用連接池管理 Redis 連線。

#### Scenario: Connection pool with health check
- **WHEN** 應用程式初始化 Redis 連線
- **THEN** 系統 SHALL 配置：
  - `socket_timeout=5` 秒
  - `socket_connect_timeout=5` 秒
  - `retry_on_timeout=True`
  - `health_check_interval=30` 秒

#### Scenario: Connection from URL
- **WHEN** 應用程式讀取 `REDIS_URL` 環境變數
- **THEN** 系統 SHALL 使用該 URL 建立 Redis 連線
- **AND** 預設值為 `redis://localhost:6379/0`

---

### Requirement: Configurable Key Prefix

系統 SHALL 支援可配置的 Redis key 前綴，以區分不同專案/環境。

#### Scenario: Custom prefix from environment
- **WHEN** 環境變數 `REDIS_KEY_PREFIX` 設為 `my_app`
- **THEN** 所有 Redis keys SHALL 使用 `my_app:` 前綴

#### Scenario: Default prefix
- **WHEN** 環境變數 `REDIS_KEY_PREFIX` 未設定
- **THEN** 系統 SHALL 使用預設前綴 `mes_wip`

---

### Requirement: SQLAlchemy Connection Timeout

SQLAlchemy 連接池的連線 SHALL 設置查詢超時。

#### Scenario: call_timeout set on checkout
- **WHEN** 連線從連接池 checkout
- **THEN** 系統 SHALL 設置 `call_timeout = 55000` 毫秒

#### Scenario: Query exceeds timeout
- **WHEN** Oracle 查詢執行超過 55 秒
- **THEN** 系統 SHALL 拋出超時異常
- **AND** 連線 SHALL 被標記為無效

---

### Requirement: Gunicorn Worker Lifecycle

Gunicorn 配置 SHALL 包含 worker 定期重啟機制。

#### Scenario: max_requests triggers restart
- **WHEN** worker 處理的請求數達到 `max_requests`（預設 1000）
- **THEN** Gunicorn SHALL 優雅重啟該 worker

#### Scenario: max_requests_jitter prevents simultaneous restart
- **WHEN** 多個 worker 同時接近 `max_requests`
- **THEN** 每個 worker 的實際重啟門檻 SHALL 加上 0 到 `max_requests_jitter` 之間的隨機值
