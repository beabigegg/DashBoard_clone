## ADDED Requirements

### Requirement: Workcenter Mapping Data Storage

系統 SHALL 將 `DW_MES_SPEC_WORKCENTER_V` 工站對照資料儲存於記憶體快取。

#### Scenario: Mapping data loaded
- **WHEN** 快取載入完成後
- **THEN** 記憶體 SHALL 包含以下資料結構：
  - `workcenter_to_group`: Dict mapping WORK_CENTER → WORK_CENTER_GROUP
  - `workcenter_to_sequence`: Dict mapping WORK_CENTER → WORKCENTERSEQUENCE_GROUP
  - `workcenter_to_short`: Dict mapping WORK_CENTER → WORK_CENTER_SHORT
  - `all_groups`: List of unique WORK_CENTER_GROUP（按 sequence 排序）

#### Scenario: Full table loaded
- **WHEN** 從 Oracle 載入資料時
- **THEN** 系統 SHALL 查詢 `DW_MES_SPEC_WORKCENTER_V` 全表（約 230 筆）
- **AND** 以 WORK_CENTER 為 key 進行去重

---

### Requirement: Workcenter Mapping Background Sync

系統 SHALL 提供背景任務，定期同步 `DW_MES_SPEC_WORKCENTER_V` 至記憶體快取。

#### Scenario: Daily sync
- **WHEN** 應用程式運行中
- **THEN** 背景任務 SHALL 每 `WORKCENTER_MAPPING_SYNC_INTERVAL` 秒（預設 86400 秒 = 24 小時）執行同步

#### Scenario: Initial cache load on startup
- **WHEN** 應用程式啟動時
- **THEN** 系統 SHALL 立即執行一次快取載入

#### Scenario: Force refresh API
- **WHEN** 呼叫 `refresh_workcenter_mapping(force=True)`
- **THEN** 系統 SHALL 立即執行快取同步

---

### Requirement: Workcenter Mapping Query API

系統 SHALL 提供 API 查詢工站對照資訊。

#### Scenario: Get group by workcenter name
- **WHEN** 呼叫 `get_workcenter_group(workcenter_name)`
- **THEN** 系統 SHALL 回傳對應的 WORK_CENTER_GROUP
- **AND** 若 workcenter_name 不存在則回傳 `None`

#### Scenario: Get all workcenter groups
- **WHEN** 呼叫 `get_all_workcenter_groups()`
- **THEN** 系統 SHALL 回傳所有 WORK_CENTER_GROUP 清單（按 sequence 排序）

#### Scenario: Get workcenter short name
- **WHEN** 呼叫 `get_workcenter_short(workcenter_name)`
- **THEN** 系統 SHALL 回傳對應的 WORK_CENTER_SHORT（如 DB, WB, Mold）
- **AND** 若不存在則回傳 `None`

#### Scenario: Get workcenters by group
- **WHEN** 呼叫 `get_workcenters_by_group(group_name)`
- **THEN** 系統 SHALL 回傳屬於該 group 的所有 WORK_CENTER 清單

---

### Requirement: Workcenter Mapping Integration with filter_cache

工站對照 SHALL 整合至現有 filter_cache 模組。

#### Scenario: Replace WIP-based workcenter groups
- **WHEN** filter_cache 載入 workcenter groups 時
- **THEN** 系統 SHALL 優先從 `DW_MES_SPEC_WORKCENTER_V` 載入
- **AND** 若載入失敗則 fallback 到現有 WIP 視圖來源

#### Scenario: Unified workcenter mapping source
- **WHEN** 呼叫 `get_workcenter_mapping()` 或 `get_workcenter_groups()`
- **THEN** 系統 SHALL 使用 SPEC_WORKCENTER_V 作為資料來源

---

### Requirement: Workcenter Mapping Configuration

系統 SHALL 支援透過環境變數配置快取行為。

#### Scenario: Custom sync interval
- **WHEN** 環境變數 `WORKCENTER_MAPPING_SYNC_INTERVAL` 設為 `43200`
- **THEN** 背景任務 SHALL 每 43200 秒（12 小時）執行一次

#### Scenario: Default configuration
- **WHEN** 環境變數未設定
- **THEN** 系統 SHALL 使用預設值：
  - `WORKCENTER_MAPPING_SYNC_INTERVAL`: `86400`（24 小時）
