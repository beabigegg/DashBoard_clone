## ADDED Requirements

### Requirement: 深度健康檢查端點

系統 SHALL 提供 `/health/deep` 端點，回報詳細的系統健康資訊。

#### Scenario: 深度檢查回應格式
- **WHEN** 呼叫 `GET /health/deep`
- **THEN** 回應 body SHALL 包含：
  ```json
  {
    "status": "healthy",
    "checks": {
      "database": { ... },
      "redis": { ... },
      "circuit_breaker": { ... },
      "cache": { ... }
    },
    "metrics": { ... }
  }
  ```

#### Scenario: 深度檢查需要認證
- **WHEN** 呼叫 `GET /health/deep`
- **AND** 使用者未登入
- **THEN** HTTP 狀態碼 SHALL 為 401

#### Scenario: 深度檢查管理員存取
- **WHEN** 呼叫 `GET /health/deep`
- **AND** 使用者為管理員
- **THEN** HTTP 狀態碼 SHALL 為 200
- **AND** 回應 SHALL 包含完整詳細資訊

#### Scenario: 深度檢查非管理員禁止
- **WHEN** 呼叫 `GET /health/deep`
- **AND** 使用者已登入但非管理員
- **THEN** HTTP 狀態碼 SHALL 為 403
- **AND** 回應 SHALL 符合統一錯誤格式

#### Scenario: 深度檢查實作方式
- **WHEN** 實作 `/health/deep` 端點
- **THEN** 路由 SHALL 使用 `@admin_required` 裝飾器
- **AND** 裝飾器 SHALL 處理認證與授權驗證

---

### Requirement: 延遲指標檢查

深度健康檢查 SHALL 包含各服務的延遲指標。

#### Scenario: 資料庫延遲
- **WHEN** 執行深度健康檢查
- **THEN** `checks.database` SHALL 包含 `latency_ms`
- **AND** `latency_ms` SHALL 為執行 ping 查詢的實際耗時

#### Scenario: Redis 延遲
- **WHEN** 執行深度健康檢查
- **AND** Redis 已啟用
- **THEN** `checks.redis` SHALL 包含 `latency_ms`
- **AND** `latency_ms` SHALL 為執行 PING 的實際耗時

#### Scenario: 延遲警告閾值
- **WHEN** 資料庫延遲超過 100ms
- **THEN** `checks.database.status` SHALL 為 `"slow"`
- **AND** `warnings` 陣列 SHALL 包含延遲警告訊息

---

### Requirement: 連線池狀態檢查

深度健康檢查 SHALL 包含資料庫連線池狀態。

#### Scenario: 連線池資訊
- **WHEN** 執行深度健康檢查
- **THEN** `checks.database` SHALL 包含：
  - `pool_size`: 設定的連線池大小
  - `pool_checked_out`: 目前借出的連線數
  - `pool_overflow`: 目前溢出的連線數

#### Scenario: 連線池耗盡警告
- **WHEN** `pool_checked_out` + `pool_overflow` >= `pool_size` + `max_overflow`
- **THEN** `warnings` 陣列 SHALL 包含連線池耗盡警告

---

### Requirement: 熔斷器狀態檢查

深度健康檢查 SHALL 包含熔斷器狀態。

#### Scenario: 熔斷器狀態正常
- **WHEN** 執行深度健康檢查
- **AND** 熔斷器狀態為 CLOSED
- **THEN** `checks.circuit_breaker` SHALL 包含：
  ```json
  {
    "database": "CLOSED",
    "failures": 0
  }
  ```

#### Scenario: 熔斷器狀態 OPEN
- **WHEN** 執行深度健康檢查
- **AND** 熔斷器狀態為 OPEN
- **THEN** `checks.circuit_breaker.database` SHALL 為 `"OPEN"`
- **AND** 整體 `status` SHALL 為 `"degraded"` 或 `"unhealthy"`
- **AND** `warnings` SHALL 包含熔斷器警告

---

### Requirement: 快取新鮮度檢查

深度健康檢查 SHALL 檢查快取資料的新鮮度。

#### Scenario: 快取新鮮度正常
- **WHEN** 執行深度健康檢查
- **AND** 快取更新時間在 2 分鐘內
- **THEN** `checks.cache.status` SHALL 為 `"fresh"`

#### Scenario: 快取資料過期
- **WHEN** 執行深度健康檢查
- **AND** 快取更新時間超過 2 分鐘
- **THEN** `checks.cache.status` SHALL 為 `"stale"`
- **AND** `warnings` SHALL 包含快取過期警告

#### Scenario: 本地快取狀態
- **WHEN** 執行深度健康檢查
- **AND** 本地快取已啟用
- **THEN** `checks.cache` SHALL 包含：
  - `local_enabled`: true
  - `local_hit_rate`: 本地快取命中率
  - `local_size`: 本地快取條目數

---

### Requirement: 效能指標摘要

深度健康檢查 SHALL 包含效能指標摘要。

#### Scenario: 包含延遲百分位數
- **WHEN** 執行深度健康檢查
- **THEN** `metrics` SHALL 包含：
  - `query_p50_ms`: P50 查詢延遲
  - `query_p95_ms`: P95 查詢延遲
  - `query_p99_ms`: P99 查詢延遲
  - `slow_query_count`: 慢查詢數量

#### Scenario: 指標為空
- **WHEN** 執行深度健康檢查
- **AND** 尚無查詢記錄
- **THEN** `metrics` 各欄位 SHALL 為 0
