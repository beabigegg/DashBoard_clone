## ADDED Requirements

### Requirement: Realtime Equipment Status Data Storage

系統 SHALL 將 `DW_MES_EQUIPMENTSTATUS_WIP_V` 資料（預聚合後）以 JSON 格式儲存於 Redis。

#### Scenario: Data stored with correct keys
- **WHEN** 快取同步完成後
- **THEN** Redis SHALL 包含以下 keys：
  - `{prefix}:equipment_status:data` - 聚合後設備狀態資料（JSON 陣列）
  - `{prefix}:equipment_status:index` - RESOURCEID → array index 的 Hash mapping
  - `{prefix}:equipment_status:meta:updated` - 快取更新時間（ISO 8601 格式）
  - `{prefix}:equipment_status:meta:count` - 記錄筆數

#### Scenario: Data aggregated by RESOURCEID
- **WHEN** 從 Oracle 載入資料時
- **THEN** 系統 SHALL 以 RESOURCEID 為 key 進行聚合
- **AND** 狀態欄位（EQUIPMENTASSETSSTATUS, EQUIPMENTASSETSSTATUSREASON）取任一筆（同 RESOURCEID 應相同）
- **AND** LOT_COUNT 為該 RESOURCEID 的記錄數
- **AND** TOTAL_TRACKIN_QTY 為 LOTTRACKINQTY_PCS 的加總
- **AND** LATEST_TRACKIN_TIME 為 LOTTRACKINTIME 的最大值

#### Scenario: Single record structure
- **WHEN** 查詢單筆聚合後資料
- **THEN** 資料結構 SHALL 包含：
  - `RESOURCEID`: 設備 ID
  - `EQUIPMENTID`: 設備編號
  - `OBJECTCATEGORY`: 設備類別
  - `EQUIPMENTASSETSSTATUS`: 設備狀態
  - `EQUIPMENTASSETSSTATUSREASON`: 狀態原因
  - `STATUS_CATEGORY`: 狀態分類（PRODUCTIVE/STANDBY/DOWN/ENGINEERING/NOT_SCHEDULED/INACTIVE/OTHER）
  - `JOBORDER`: 維修工單號（若有）
  - `JOBSTATUS`: 工單狀態（若有）
  - `SYMPTOMCODE`: 症狀代碼（若有）
  - `CAUSECODE`: 故障原因代碼（若有）
  - `REPAIRCODE`: 維修處置代碼（若有）
  - `LOT_COUNT`: 當前 WIP 批次數
  - `TOTAL_TRACKIN_QTY`: Track-In 總數量
  - `LATEST_TRACKIN_TIME`: 最新 Track-In 時間

#### Scenario: Atomic update with pipeline
- **WHEN** 快取同步執行時
- **THEN** 系統 SHALL 使用 Redis pipeline 確保所有 keys 原子更新

---

### Requirement: Realtime Equipment Status Background Sync

系統 SHALL 提供背景任務，定期同步 `DW_MES_EQUIPMENTSTATUS_WIP_V` 至 Redis 快取。

#### Scenario: Periodic sync at configured interval
- **WHEN** 應用程式啟動後
- **THEN** 背景任務 SHALL 每 `EQUIPMENT_STATUS_SYNC_INTERVAL` 秒（預設 300 秒 = 5 分鐘）執行同步

#### Scenario: Full table sync each time
- **WHEN** 背景任務執行時
- **THEN** 系統 SHALL 執行全表查詢並覆蓋快取
- **AND** 記錄同步耗時與記錄數至 info 日誌

#### Scenario: Initial cache load on startup
- **WHEN** 應用程式啟動時
- **THEN** 系統 SHALL 立即執行一次快取同步

#### Scenario: Force refresh API
- **WHEN** 呼叫 `refresh_equipment_status_cache(force=True)`
- **THEN** 系統 SHALL 立即執行快取同步，不等待下次排程

---

### Requirement: Realtime Equipment Status Query API

系統 SHALL 提供 API 從 Redis 快取查詢即時設備狀態。

#### Scenario: Get all equipment status
- **WHEN** 呼叫 `get_all_equipment_status()`
- **THEN** 系統 SHALL 回傳快取中所有設備狀態資料（List[Dict]）

#### Scenario: Get status by RESOURCEID
- **WHEN** 呼叫 `get_equipment_status_by_id(resource_id)`
- **THEN** 系統 SHALL 使用 index hash 快速查找並回傳對應資料（Dict）
- **AND** 若 ID 不存在則回傳 `None`

#### Scenario: Get status by multiple RESOURCEIDs
- **WHEN** 呼叫 `get_equipment_status_by_ids(resource_ids)`
- **THEN** 系統 SHALL 回傳所有匹配的設備狀態（List[Dict]）
- **AND** 不存在的 ID 不會出現在結果中

---

### Requirement: Realtime Equipment Status Cache Status API

系統 SHALL 提供 API 查詢快取狀態。

#### Scenario: Get cache status
- **WHEN** 呼叫 `get_equipment_status_cache_status()`
- **THEN** 系統 SHALL 回傳包含以下欄位的 Dict：
  - `enabled`: 快取是否啟用
  - `loaded`: 快取是否已載入
  - `count`: 快取記錄數
  - `updated_at`: 最後同步時間

---

### Requirement: Realtime Equipment Status Fallback

當 Redis 不可用時，系統 SHALL 記錄錯誤並回傳空結果。

#### Scenario: Redis unavailable
- **WHEN** Redis 連線失敗或超時
- **THEN** 系統 SHALL 記錄 error 日誌
- **AND** 回傳空列表

#### Scenario: Cache disabled by config
- **WHEN** 環境變數 `REALTIME_EQUIPMENT_CACHE_ENABLED` 設為 `false`
- **THEN** 系統 SHALL 完全跳過 Redis
- **AND** 背景同步任務 SHALL 不啟動
- **AND** 所有查詢 API 回傳空結果

---

### Requirement: Status Category Classification

系統 SHALL 為每個狀態值提供分類標籤。

#### Scenario: Standard E10 status classification
- **WHEN** 狀態值為標準 E10 狀態
- **THEN** 系統 SHALL 依據以下規則分類：
  - `PRD` → `PRODUCTIVE`
  - `SBY` → `STANDBY`
  - `UDT` → `DOWN`
  - `SDT` → `DOWN`
  - `EGT` → `ENGINEERING`
  - `NST` → `NOT_SCHEDULED`

#### Scenario: Non-standard status classification
- **WHEN** 狀態值為非標準狀態
- **THEN** 系統 SHALL 依據以下規則分類：
  - `SCRAP` → `INACTIVE`
  - `設備-LOST` → `INACTIVE`
  - `設備-RUN` → `PRODUCTIVE`
  - 其他未知狀態 → `OTHER`

---

### Requirement: Realtime Equipment Status Configuration

系統 SHALL 支援透過環境變數配置快取行為。

#### Scenario: Custom sync interval
- **WHEN** 環境變數 `EQUIPMENT_STATUS_SYNC_INTERVAL` 設為 `600`
- **THEN** 背景任務 SHALL 每 600 秒（10 分鐘）執行一次

#### Scenario: Default configuration
- **WHEN** 環境變數未設定
- **THEN** 系統 SHALL 使用預設值：
  - `REALTIME_EQUIPMENT_CACHE_ENABLED`: `true`
  - `EQUIPMENT_STATUS_SYNC_INTERVAL`: `300`（5 分鐘）
