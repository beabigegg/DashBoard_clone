## ADDED Requirements

### Requirement: Resource Cache Data Storage

系統 SHALL 將 `DW_MES_RESOURCE` 全表資料（套用全域篩選後）以 JSON 格式儲存於 Redis。

#### Scenario: Data stored with correct keys
- **WHEN** 快取同步完成後
- **THEN** Redis SHALL 包含以下 keys：
  - `{prefix}:resource:data` - 完整表資料（JSON 陣列，包含全部 78 欄位）
  - `{prefix}:resource:meta:version` - Oracle 資料的 `MAX(LASTCHANGEDATE)`
  - `{prefix}:resource:meta:updated` - 快取更新時間（ISO 8601 格式）
  - `{prefix}:resource:meta:count` - 記錄筆數

#### Scenario: Global filters applied
- **WHEN** 從 Oracle 載入資料時
- **THEN** 系統 SHALL 套用以下篩選條件：
  - 設備類型：`(OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY') OR (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT')`
  - 排除地點：`LOCATIONNAME NOT IN ('ATEC', 'F區', 'F區焊接站', '報廢', '實驗室', '山東', '成型站_F區', '焊接F區', '無錫', '熒茂')`
  - 排除資產狀態：`PJ_ASSETSSTATUS NOT IN ('Disapproved')`

#### Scenario: Atomic update with pipeline
- **WHEN** 快取同步執行時
- **THEN** 系統 SHALL 使用 Redis pipeline 確保所有 keys 原子更新

---

### Requirement: Resource Cache Background Sync

系統 SHALL 提供背景任務，定期同步 `DW_MES_RESOURCE` 至 Redis 快取。

#### Scenario: Periodic sync at configured interval
- **WHEN** 應用程式啟動後
- **THEN** 背景任務 SHALL 每 `RESOURCE_SYNC_INTERVAL` 秒（預設 14400 秒 = 4 小時）檢查是否需要同步

#### Scenario: Version check triggers sync
- **WHEN** 背景任務執行時，Oracle 的 `MAX(LASTCHANGEDATE)` 與 Redis 中儲存的版本不同
- **THEN** 系統 SHALL 執行全表同步
- **AND** 更新 `{prefix}:resource:meta:version` 為新的版本
- **AND** 更新 `{prefix}:resource:meta:updated` 為當前時間

#### Scenario: Version unchanged skips sync
- **WHEN** 背景任務執行時，Oracle 的 `MAX(LASTCHANGEDATE)` 與 Redis 中儲存的版本相同
- **THEN** 系統 SHALL 跳過同步
- **AND** 記錄 debug 日誌

#### Scenario: Initial cache load on startup
- **WHEN** 應用程式啟動時 Redis 中無 resource 快取資料
- **THEN** 系統 SHALL 立即執行一次快取同步

#### Scenario: Force refresh ignores version check
- **WHEN** 呼叫 `refresh_cache(force=True)`
- **THEN** 系統 SHALL 執行全表同步，不論版本是否相同

---

### Requirement: Resource Cache Query API

系統 SHALL 提供 API 從 Redis 快取查詢設備資料。

#### Scenario: Get all resources
- **WHEN** 呼叫 `get_all_resources()`
- **THEN** 系統 SHALL 回傳快取中所有設備資料（List[Dict]，包含全部 78 欄位）

#### Scenario: Get resource by ID
- **WHEN** 呼叫 `get_resource_by_id(resource_id)`
- **THEN** 系統 SHALL 回傳對應的設備資料（Dict）
- **AND** 若 ID 不存在則回傳 `None`

#### Scenario: Get resources by multiple IDs
- **WHEN** 呼叫 `get_resources_by_ids(resource_ids)`
- **THEN** 系統 SHALL 回傳所有匹配的設備資料（List[Dict]）
- **AND** 不存在的 ID 不會出現在結果中

#### Scenario: Get resources by filter
- **WHEN** 呼叫 `get_resources_by_filter(workcenters=['焊接_DB'], is_production=True)`
- **THEN** 系統 SHALL 在 Python 端篩選快取資料
- **AND** 回傳符合所有條件的設備清單

---

### Requirement: Resource Cache Distinct Values API

系統 SHALL 提供 API 取得設備欄位的唯一值清單，供篩選器使用。

#### Scenario: Get distinct values for column
- **WHEN** 呼叫 `get_distinct_values('RESOURCEFAMILYNAME')`
- **THEN** 系統 SHALL 回傳該欄位的唯一值清單（排序後）
- **AND** 自動過濾 `None` 和空字串

#### Scenario: Convenience methods for common columns
- **WHEN** 呼叫 `get_resource_families()`
- **THEN** 系統 SHALL 回傳 `RESOURCEFAMILYNAME` 欄位的唯一值清單
- **AND** `get_workcenters()` 回傳 `WORKCENTERNAME` 唯一值
- **AND** `get_departments()` 回傳 `PJ_DEPARTMENT` 唯一值

---

### Requirement: Resource Cache Status API

系統 SHALL 提供 API 查詢快取狀態。

#### Scenario: Get cache status
- **WHEN** 呼叫 `get_cache_status()`
- **THEN** 系統 SHALL 回傳包含以下欄位的 Dict：
  - `enabled`: 快取是否啟用
  - `loaded`: 快取是否已載入
  - `count`: 快取記錄數
  - `version`: 資料版本（MAX(LASTCHANGEDATE)）
  - `updated_at`: 最後同步時間

#### Scenario: Status when cache not loaded
- **WHEN** 呼叫 `get_cache_status()` 且快取尚未載入
- **THEN** `loaded` SHALL 為 `false`
- **AND** `count` SHALL 為 `0`

---

### Requirement: Resource Cache Fallback

當 Redis 不可用時，系統 SHALL 自動降級到直接查詢 Oracle。

#### Scenario: Redis unavailable triggers fallback
- **WHEN** Redis 連線失敗或超時
- **THEN** 系統 SHALL 直接查詢 Oracle `DW_MES_RESOURCE`
- **AND** 記錄 warning 日誌

#### Scenario: Cache empty triggers fallback
- **WHEN** Redis 可用但 `{prefix}:resource:data` 不存在或為空
- **THEN** 系統 SHALL 直接查詢 Oracle `DW_MES_RESOURCE`

#### Scenario: RESOURCE_CACHE_ENABLED=false disables cache
- **WHEN** 環境變數 `RESOURCE_CACHE_ENABLED` 設為 `false`
- **THEN** 系統 SHALL 完全跳過 Redis，直接查詢 Oracle
- **AND** 背景同步任務 SHALL 不啟動

---

### Requirement: Resource Cache Configuration

系統 SHALL 支援透過環境變數配置快取行為。

#### Scenario: Custom sync interval
- **WHEN** 環境變數 `RESOURCE_SYNC_INTERVAL` 設為 `7200`
- **THEN** 背景任務 SHALL 每 7200 秒（2 小時）執行一次

#### Scenario: Default configuration
- **WHEN** 環境變數未設定
- **THEN** 系統 SHALL 使用預設值：
  - `RESOURCE_CACHE_ENABLED`: `true`
  - `RESOURCE_SYNC_INTERVAL`: `14400`（4 小時）

#### Scenario: Key prefix from environment
- **WHEN** 環境變數 `REDIS_KEY_PREFIX` 設為 `my_app`
- **THEN** 所有 resource 快取 keys SHALL 使用 `my_app:resource:*` 前綴

---

### Requirement: Health Check Integration

健康檢查 SHALL 包含 Resource 快取狀態。

#### Scenario: Resource cache status in health check
- **WHEN** 呼叫 `GET /health` 且 resource 快取可用
- **THEN** 回應 body SHALL 包含 `resource_cache` 區塊：
  ```json
  {
    "resource_cache": {
      "enabled": true,
      "loaded": true,
      "count": 3500,
      "version": "2026-01-29 10:30:00",
      "updated_at": "2026-01-29 14:00:00"
    }
  }
  ```

#### Scenario: Resource cache not loaded warning
- **WHEN** 呼叫 `GET /health` 且 resource 快取啟用但未載入
- **THEN** 回應 body 的 `warnings` SHALL 包含 "Resource cache not loaded"

---

### Requirement: Resource History KPI API - Availability%

系統 SHALL 在 KPI API 回應中新增 `availability_pct` 欄位。

#### Scenario: KPI includes availability percentage
- **WHEN** 呼叫 `GET /api/resource/history/summary`
- **THEN** 回應的 `kpi` 物件 SHALL 包含 `availability_pct` 欄位
- **AND** `availability_pct` 計算公式為 `(PRD + SBY + EGT) / (PRD + SBY + EGT + SDT + UDT + NST) * 100`
- **AND** 數值四捨五入至小數點後一位

#### Scenario: Availability percentage handles zero denominator
- **WHEN** 分母 `(PRD + SBY + EGT + SDT + UDT + NST)` 為零
- **THEN** `availability_pct` SHALL 回傳 `0`

---

### Requirement: Resource History Trend API - Availability%

系統 SHALL 在趨勢 API 回應的每個資料點中新增 `availability_pct` 欄位。

#### Scenario: Trend data includes availability percentage
- **WHEN** 呼叫 `GET /api/resource/history/summary`
- **THEN** 回應的 `trend` 陣列中每個物件 SHALL 包含 `availability_pct` 欄位
- **AND** 各資料點的 `availability_pct` 使用該時間區段的 E10 狀態時數計算

#### Scenario: Trend availability calculation formula
- **GIVEN** 單一時間區段的 E10 狀態時數
- **WHEN** 計算該區段的 `availability_pct`
- **THEN** 公式為 `(PRD_HOURS + SBY_HOURS + EGT_HOURS) / (PRD_HOURS + SBY_HOURS + EGT_HOURS + SDT_HOURS + UDT_HOURS + NST_HOURS) * 100`

---

### Requirement: Resource History Detail API - Availability%

系統 SHALL 在明細 API 回應的每筆資料中新增 `availability_pct` 欄位。

#### Scenario: Detail data includes availability percentage
- **WHEN** 呼叫 `GET /api/resource/history/detail`
- **THEN** 回應的 `data` 陣列中每個物件 SHALL 包含 `availability_pct` 欄位

---

### Requirement: CSV Export - Availability%

系統 SHALL 在 CSV 匯出中新增 Availability% 欄位。

#### Scenario: CSV includes availability column
- **WHEN** 匯出 CSV 檔案
- **THEN** CSV 標頭 SHALL 包含 `Availability%` 欄位（位於 `OU%` 之後）
- **AND** 各列的 `Availability%` 使用該機台的 E10 狀態時數計算

---

### Requirement: Frontend Trend Chart - Availability%

系統 SHALL 在趨勢圖中新增 Availability% 趨勢線。

#### Scenario: Chart displays availability trend line
- **WHEN** 顯示設備歷史績效頁面的趨勢圖
- **THEN** 圖表 SHALL 顯示 Availability% 趨勢線
- **AND** Availability% 使用綠色 (`#10B981`) 顯示
- **AND** OU% 保持原有藍色 (`#3B82F6`)

#### Scenario: Chart legend shows both metrics
- **WHEN** 顯示趨勢圖
- **THEN** 圖例 SHALL 包含 "OU%" 與 "Availability%" 兩項

---

### Requirement: Frontend KPI Card - Availability%

系統 SHALL 在 KPI 區新增 Availability% 卡片。

#### Scenario: KPI section displays availability card
- **WHEN** 顯示設備歷史績效頁面
- **THEN** KPI 區 SHALL 顯示 Availability% 卡片
- **AND** 卡片顯示格式為 `XX.X%`
- **AND** 卡片位置在 OU% 卡片之後
