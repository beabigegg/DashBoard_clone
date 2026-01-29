## ADDED Requirements

### Requirement: Health Check Endpoint

系統 SHALL 提供 `/health` 端點，回報服務健康狀態。

#### Scenario: All services healthy
- **WHEN** 呼叫 `GET /health` 且 Oracle 和 Redis 都正常
- **THEN** 系統 SHALL 回傳 HTTP 200
- **AND** 回應 body 為：
  ```json
  {
    "status": "healthy",
    "services": {
      "database": "ok",
      "redis": "ok"
    }
  }
  ```

#### Scenario: Database unhealthy
- **WHEN** 呼叫 `GET /health` 且 Oracle 連線失敗
- **THEN** 系統 SHALL 回傳 HTTP 503
- **AND** 回應 body 包含：
  ```json
  {
    "status": "unhealthy",
    "services": {
      "database": "error",
      "redis": "ok"
    },
    "errors": ["Database connection failed: <error message>"]
  }
  ```

#### Scenario: Redis unhealthy but service degraded
- **WHEN** 呼叫 `GET /health` 且 Redis 連線失敗但 Oracle 正常
- **THEN** 系統 SHALL 回傳 HTTP 200（因為可降級運作）
- **AND** 回應 body 包含：
  ```json
  {
    "status": "degraded",
    "services": {
      "database": "ok",
      "redis": "error"
    },
    "warnings": ["Redis unavailable, running in fallback mode"]
  }
  ```

#### Scenario: Redis disabled
- **WHEN** 呼叫 `GET /health` 且 `REDIS_ENABLED=false`
- **THEN** 回應 body 的 `services.redis` SHALL 為 `"disabled"`

---

### Requirement: Database Health Check

健康檢查 SHALL 驗證 Oracle 資料庫連線。

#### Scenario: Database ping succeeds
- **WHEN** 執行資料庫健康檢查
- **THEN** 系統 SHALL 執行 `SELECT 1 FROM DUAL`
- **AND** 查詢成功則標記 database 為 `ok`

#### Scenario: Database ping timeout
- **WHEN** 資料庫查詢超過 5 秒
- **THEN** 系統 SHALL 標記 database 為 `error`
- **AND** 記錄超時錯誤

---

### Requirement: Redis Health Check

健康檢查 SHALL 驗證 Redis 連線（當 REDIS_ENABLED=true 時）。

#### Scenario: Redis ping succeeds
- **WHEN** 執行 Redis 健康檢查
- **THEN** 系統 SHALL 執行 Redis `PING` 命令
- **AND** 收到 `PONG` 回應則標記 redis 為 `ok`

#### Scenario: Redis ping fails
- **WHEN** Redis `PING` 命令失敗或超時
- **THEN** 系統 SHALL 標記 redis 為 `error`
- **AND** 服務狀態 SHALL 為 `degraded`（非 `unhealthy`）

---

### Requirement: Cache Status in Health Check

健康檢查 SHALL 包含快取狀態資訊。

#### Scenario: Cache status included
- **WHEN** 呼叫 `GET /health` 且快取可用
- **THEN** 回應 body SHALL 包含 `cache` 區塊：
  ```json
  {
    "cache": {
      "enabled": true,
      "sys_date": "2024-01-15 10:30:00",
      "updated_at": "2024-01-15 10:35:22"
    }
  }
  ```

#### Scenario: Cache not populated
- **WHEN** 呼叫 `GET /health` 且 Redis 可用但快取尚未載入
- **THEN** 回應 body 的 `cache.sys_date` SHALL 為 `null`

---

### Requirement: Health Check Performance

健康檢查 SHALL 快速回應，不影響服務效能。

#### Scenario: Response within timeout
- **WHEN** 呼叫 `GET /health`
- **THEN** 系統 SHALL 在 10 秒內回應
- **AND** 各項檢查的超時時間 SHALL 不超過 5 秒

#### Scenario: No authentication required
- **WHEN** 呼叫 `GET /health`
- **THEN** 系統 SHALL 不要求身份驗證
- **AND** 不記錄到存取日誌（避免日誌污染）
