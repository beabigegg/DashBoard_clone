## ADDED Requirements

### Requirement: 查詢延遲收集

系統 SHALL 收集所有資料庫查詢的延遲時間。

#### Scenario: 記錄查詢延遲
- **WHEN** 執行資料庫查詢
- **THEN** 系統 SHALL 記錄查詢耗時（毫秒）
- **AND** 記錄 SHALL 儲存在記憶體內滑動視窗

#### Scenario: 滑動視窗大小限制
- **WHEN** 記錄的查詢數量超過 1000 筆
- **THEN** 系統 SHALL 自動移除最舊的記錄
- **AND** 視窗 SHALL 維持最多 1000 筆

---

### Requirement: 延遲百分位數計算

系統 SHALL 計算查詢延遲的百分位數統計。

#### Scenario: 計算 P50/P95/P99
- **WHEN** 呼叫 `get_query_metrics()`
- **THEN** 回傳值 SHALL 包含：
  - `p50_ms`: 第 50 百分位延遲
  - `p95_ms`: 第 95 百分位延遲
  - `p99_ms`: 第 99 百分位延遲
  - `count`: 樣本數量
  - `slow_count`: 慢查詢數量（延遲 > 1 秒）

#### Scenario: 空資料處理
- **WHEN** 尚無查詢記錄
- **THEN** 所有百分位數 SHALL 回傳 0
- **AND** `count` SHALL 為 0

---

### Requirement: 慢查詢統計

系統 SHALL 追蹤慢查詢的數量與比例。

#### Scenario: 慢查詢定義
- **WHEN** 查詢延遲超過 1000 毫秒
- **THEN** 該查詢 SHALL 被標記為慢查詢

#### Scenario: 慢查詢比例計算
- **WHEN** 呼叫 `get_query_metrics()`
- **THEN** 回傳值 SHALL 包含 `slow_rate`
- **AND** `slow_rate` SHALL 為 `slow_count / count`

---

### Requirement: 指標 API 端點

系統 SHALL 提供 API 端點查詢效能指標。

#### Scenario: 取得效能指標
- **WHEN** 呼叫 `GET /admin/api/metrics`
- **AND** 使用者為管理員
- **THEN** 回應 SHALL 包含查詢延遲統計
- **AND** HTTP 狀態碼 SHALL 為 200

#### Scenario: 非管理員禁止存取
- **WHEN** 呼叫 `GET /admin/api/metrics`
- **AND** 使用者非管理員
- **THEN** HTTP 狀態碼 SHALL 為 403

---

### Requirement: Worker 獨立統計

系統 SHALL 在每個 Gunicorn worker 獨立收集指標。

#### Scenario: 各 worker 獨立統計
- **WHEN** 系統運行多個 workers
- **THEN** 每個 worker SHALL 維護獨立的指標資料
- **AND** 百分位數計算 SHALL 基於該 worker 的樣本

#### Scenario: API 回傳當前 worker 指標
- **WHEN** 呼叫 `GET /admin/api/metrics`
- **THEN** 回應 SHALL 標示該資料來自哪個 worker（PID）
- **AND** 回應 SHALL 包含 `worker_pid` 欄位

#### Scenario: 已知限制 - 指標跳動
- **GIVEN** 系統運行 N 個 workers（N > 1）
- **WHEN** 多次呼叫 `GET /admin/api/metrics`
- **THEN** 因 load balancer 分配，數值可能因不同 worker 而有差異
- **AND** 這是已知且接受的行為限制

---

### Requirement: 共享計數器（可選優化）

當 Redis 可用時，系統 MAY 使用 Redis 共享關鍵計數指標。

#### Scenario: Redis 共享總計數
- **WHEN** Redis 已啟用
- **THEN** `total_queries` 計數 MAY 使用 Redis INCR 命令
- **AND** `slow_queries` 計數 MAY 使用 Redis INCR 命令
- **AND** 這些計數 SHALL 跨所有 workers 共享

#### Scenario: Redis 不可用時退化
- **WHEN** Redis 不可用或停用
- **THEN** 系統 SHALL 退化為純 worker 獨立統計
- **AND** 功能 SHALL 繼續正常運作

#### Scenario: 百分位數仍為 worker 獨立
- **WHEN** 使用 Redis 共享計數器
- **THEN** 延遲百分位數（P50/P95/P99）SHALL 仍維持 worker 獨立
- **AND** 百分位數計算需要完整樣本，不適合跨 worker 共享
