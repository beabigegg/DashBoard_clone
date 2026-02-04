## ADDED Requirements

### Requirement: 熔斷器狀態管理

系統 SHALL 實作 Circuit Breaker 模式，管理資料庫連線的熔斷狀態。

#### Scenario: 初始狀態為 CLOSED
- **WHEN** 系統啟動
- **THEN** 熔斷器狀態 SHALL 為 `CLOSED`
- **AND** 所有資料庫請求 SHALL 正常執行

#### Scenario: 失敗累積觸發 OPEN
- **WHEN** 熔斷器處於 `CLOSED` 狀態
- **AND** 滑動視窗內失敗次數 >= 5
- **AND** 失敗率 >= 50%
- **THEN** 熔斷器狀態 SHALL 轉換為 `OPEN`

#### Scenario: OPEN 狀態拒絕請求
- **WHEN** 熔斷器處於 `OPEN` 狀態
- **AND** 收到資料庫請求
- **THEN** 系統 SHALL 立即回傳錯誤
- **AND** 錯誤代碼 SHALL 為 `SERVICE_UNAVAILABLE`
- **AND** SHALL NOT 嘗試連線資料庫

#### Scenario: OPEN 轉換為 HALF_OPEN
- **WHEN** 熔斷器處於 `OPEN` 狀態
- **AND** 已等待 30 秒（recovery_timeout）
- **THEN** 熔斷器狀態 SHALL 轉換為 `HALF_OPEN`

#### Scenario: HALF_OPEN 探測成功
- **WHEN** 熔斷器處於 `HALF_OPEN` 狀態
- **AND** 探測請求執行成功
- **THEN** 熔斷器狀態 SHALL 轉換為 `CLOSED`
- **AND** 失敗計數 SHALL 重置為 0

#### Scenario: HALF_OPEN 探測失敗
- **WHEN** 熔斷器處於 `HALF_OPEN` 狀態
- **AND** 探測請求執行失敗
- **THEN** 熔斷器狀態 SHALL 轉換為 `OPEN`
- **AND** recovery_timeout SHALL 重新計時

---

### Requirement: 熔斷器參數配置

系統 SHALL 支援透過環境變數配置熔斷器參數。

#### Scenario: 預設參數值
- **WHEN** 未設定熔斷器相關環境變數
- **THEN** failure_threshold SHALL 為 5
- **AND** failure_rate SHALL 為 0.5 (50%)
- **AND** recovery_timeout SHALL 為 30 秒
- **AND** window_size SHALL 為 10

#### Scenario: 環境變數覆蓋
- **WHEN** 設定 `CIRCUIT_BREAKER_FAILURE_THRESHOLD=10`
- **THEN** failure_threshold SHALL 為 10

#### Scenario: 停用熔斷器
- **WHEN** 設定 `CIRCUIT_BREAKER_ENABLED=false`
- **THEN** 熔斷器功能 SHALL 停用
- **AND** 所有請求 SHALL 直接執行，不經過熔斷器檢查

---

### Requirement: 熔斷器狀態查詢

系統 SHALL 提供 API 查詢熔斷器狀態。

#### Scenario: 查詢熔斷器狀態
- **WHEN** 呼叫內部方法 `get_circuit_breaker_status()`
- **THEN** 回傳值 SHALL 包含：
  - `state`: 當前狀態 (CLOSED/OPEN/HALF_OPEN)
  - `failure_count`: 目前失敗次數
  - `success_count`: 目前成功次數
  - `last_failure_time`: 最後失敗時間

---

### Requirement: 熔斷事件日誌

系統 SHALL 記錄熔斷器狀態變化事件。

#### Scenario: 記錄狀態轉換
- **WHEN** 熔斷器狀態發生變化
- **THEN** 系統 SHALL 記錄 WARNING 級別日誌
- **AND** 日誌 SHALL 包含：前狀態、新狀態、觸發原因

#### Scenario: 記錄 OPEN 事件
- **WHEN** 熔斷器轉換為 `OPEN` 狀態
- **THEN** 日誌訊息 SHALL 包含失敗次數與失敗率
