## ADDED Requirements

### Requirement: 本地 LRU 快取

系統 SHALL 實作本地 LRU 快取作為 Redis 的二級 fallback。

#### Scenario: 快取查詢順序
- **WHEN** 查詢快取資料
- **THEN** 系統 SHALL 先查詢 Redis
- **AND** Redis 未命中或失敗時 SHALL 查詢本地快取
- **AND** 本地快取未命中時 SHALL 查詢 Oracle

#### Scenario: 快取回填
- **WHEN** 從 Oracle 取得資料
- **THEN** 系統 SHALL 同時寫入 Redis 和本地快取
- **AND** 本地快取 TTL SHALL 為 60 秒

---

### Requirement: 本地快取容量限制

系統 SHALL 限制本地快取的記憶體使用。

#### Scenario: 預設最大條目數
- **WHEN** 未設定 `LOCAL_CACHE_MAXSIZE` 環境變數
- **THEN** 本地快取預設最大條目數 SHALL 為 500
- **AND** 此值足以容納 WIP 狀態、設備清單、Hold Summary 等多組快取

#### Scenario: 最大條目數限制
- **WHEN** 本地快取條目數達到 maxsize 上限
- **AND** 新增新條目
- **THEN** 系統 SHALL 移除最少使用（LRU）的條目
- **AND** 條目數 SHALL 維持 <= maxsize

#### Scenario: 環境變數配置
- **WHEN** 設定 `LOCAL_CACHE_MAXSIZE=1000`
- **THEN** 本地快取最大條目數 SHALL 為 1000

#### Scenario: 快取鍵設計
- **WHEN** 建立快取條目
- **THEN** 快取鍵 SHALL 包含功能前綴（如 `wip:`, `equipment:`, `hold:`）
- **AND** 不同功能的快取 SHALL 共用同一 LRU 池
- **AND** LRU 策略 SHALL 自動淘汰最少使用的條目（無論功能類型）

---

### Requirement: 本地快取 TTL

系統 SHALL 為本地快取條目設定過期時間。

#### Scenario: 預設 TTL
- **WHEN** 未設定 TTL 環境變數
- **THEN** 本地快取 TTL SHALL 為 60 秒

#### Scenario: 過期條目處理
- **WHEN** 查詢本地快取
- **AND** 條目已過期（超過 TTL）
- **THEN** 系統 SHALL 視為未命中
- **AND** SHALL 移除該過期條目

#### Scenario: TTL 比 Redis 短
- **WHEN** Redis 快取 TTL 為 N 秒
- **THEN** 本地快取 TTL SHALL < N
- **AND** 確保本地快取資料不會比 Redis 舊太多

---

### Requirement: 快取停用控制

系統 SHALL 支援透過環境變數停用本地快取。

#### Scenario: 停用本地快取
- **WHEN** 設定 `LOCAL_CACHE_ENABLED=false`
- **THEN** 本地快取功能 SHALL 停用
- **AND** 快取查詢 SHALL 直接查詢 Redis 或 Oracle

#### Scenario: 預設啟用
- **WHEN** 未設定 `LOCAL_CACHE_ENABLED`
- **THEN** 本地快取 SHALL 預設啟用

---

### Requirement: 快取命中率統計

系統 SHALL 追蹤本地快取的命中率。

#### Scenario: 記錄命中與未命中
- **WHEN** 查詢本地快取
- **THEN** 系統 SHALL 記錄是否命中
- **AND** 統計 SHALL 儲存在記憶體中

#### Scenario: 查詢命中率
- **WHEN** 呼叫 `get_local_cache_stats()`
- **THEN** 回傳值 SHALL 包含：
  - `hits`: 命中次數
  - `misses`: 未命中次數
  - `hit_rate`: 命中率 (hits / (hits + misses))
  - `size`: 目前條目數
