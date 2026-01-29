## ADDED Requirements

### Requirement: Resource Status Merged Query API

系統 SHALL 提供 API 合併 resource-cache 與 realtime-equipment-cache 資料。

#### Scenario: Get merged resource status
- **WHEN** 呼叫 `get_merged_resource_status()`
- **THEN** 系統 SHALL 回傳合併後的設備狀態清單
- **AND** 每筆資料包含 resource-cache 的主檔欄位（RESOURCENAME, WORKCENTERNAME, RESOURCEFAMILYNAME, PJ_DEPARTMENT, PJ_ISPRODUCTION, PJ_ISKEY, PJ_ISMONITOR）
- **AND** 每筆資料包含 realtime-equipment-cache 的即時欄位（EQUIPMENTASSETSSTATUS, EQUIPMENTASSETSSTATUSREASON, STATUS_CATEGORY, JOBORDER, JOBSTATUS, LOT_COUNT, TOTAL_TRACKIN_QTY, LATEST_TRACKIN_TIME）
- **AND** 每筆資料包含 workcenter-mapping-cache 的分組欄位（WORKCENTER_GROUP, WORKCENTER_SHORT）

#### Scenario: Merge by RESOURCEID
- **WHEN** 合併資料時
- **THEN** 系統 SHALL 以 resource-cache 為主表
- **AND** 使用 RESOURCEID 作為 JOIN key 與 realtime-equipment-cache 合併
- **AND** 使用 WORKCENTERNAME 作為 JOIN key 與 workcenter-mapping-cache 合併

#### Scenario: Handle missing realtime status
- **WHEN** resource-cache 中的設備在 realtime-equipment-cache 找不到對應資料
- **THEN** 即時欄位 SHALL 回傳 `None`
- **AND** 記錄 debug 日誌

#### Scenario: Handle missing workcenter group
- **WHEN** WORKCENTERNAME 在 workcenter-mapping-cache 找不到對應
- **THEN** WORKCENTER_GROUP 與 WORKCENTER_SHORT SHALL 回傳 `None`

---

### Requirement: Resource Status Merged Query with Filter

系統 SHALL 支援帶篩選條件的合併查詢。

#### Scenario: Filter by workcenter groups
- **WHEN** 呼叫 `get_merged_resource_status(workcenter_groups=['焊接', '成型'])`
- **THEN** 系統 SHALL 只回傳 WORKCENTER_GROUP 在指定清單中的設備

#### Scenario: Filter by equipment flags
- **WHEN** 呼叫 `get_merged_resource_status(is_production=True, is_key=True)`
- **THEN** 系統 SHALL 只回傳符合 PJ_ISPRODUCTION=1 且 PJ_ISKEY=1 的設備

#### Scenario: Filter by status category
- **WHEN** 呼叫 `get_merged_resource_status(status_categories=['PRODUCTIVE', 'STANDBY'])`
- **THEN** 系統 SHALL 只回傳 STATUS_CATEGORY 在指定清單中的設備

#### Scenario: Combined filters
- **WHEN** 呼叫 `get_merged_resource_status(workcenter_groups=['焊接'], is_production=True, status_categories=['DOWN'])`
- **THEN** 系統 SHALL 回傳同時符合所有條件的設備

---

### Requirement: Resource Status Summary Statistics

系統 SHALL 提供設備狀態統計摘要 API。

#### Scenario: Get status summary
- **WHEN** 呼叫 `get_resource_status_summary()`
- **THEN** 系統 SHALL 回傳包含以下統計的 Dict：
  - `total_count`: 設備總數
  - `by_status_category`: 各 STATUS_CATEGORY 的設備數
  - `by_workcenter_group`: 各 WORKCENTER_GROUP 的設備數
  - `with_active_job`: 有維修工單的設備數
  - `with_wip`: 有 WIP 的設備數（LOT_COUNT > 0）

#### Scenario: Summary respects filters
- **WHEN** 呼叫 `get_resource_status_summary(workcenter_groups=['焊接'])`
- **THEN** 統計 SHALL 只計算符合篩選條件的設備

---

### Requirement: Resource Status Workcenter Matrix

系統 SHALL 提供工站 × 狀態矩陣 API。

#### Scenario: Get workcenter status matrix
- **WHEN** 呼叫 `get_workcenter_status_matrix()`
- **THEN** 系統 SHALL 回傳 List[Dict]，每筆包含：
  - `workcenter_group`: 工站分組名稱
  - `workcenter_sequence`: 排序序號
  - `total`: 該分組設備總數
  - `PRD`: 狀態為 PRD 的數量
  - `SBY`: 狀態為 SBY 的數量
  - `UDT`: 狀態為 UDT 的數量
  - `SDT`: 狀態為 SDT 的數量
  - `EGT`: 狀態為 EGT 的數量
  - `NST`: 狀態為 NST 的數量
  - `OTHER`: 其他狀態的數量

#### Scenario: Matrix sorted by sequence
- **WHEN** 回傳矩陣資料
- **THEN** 資料 SHALL 按 workcenter_sequence 升序排列

---

### Requirement: Health Check Integration

健康檢查 SHALL 包含即時設備狀態快取狀態。

#### Scenario: Equipment status cache in health check
- **WHEN** 呼叫 `GET /health`
- **THEN** 回應 body SHALL 包含 `equipment_status_cache` 區塊：
  ```json
  {
    "equipment_status_cache": {
      "enabled": true,
      "loaded": true,
      "count": 1803,
      "updated_at": "2026-01-29T14:00:00"
    }
  }
  ```

#### Scenario: Workcenter mapping in health check
- **WHEN** 呼叫 `GET /health`
- **THEN** 回應 body SHALL 包含 `workcenter_mapping` 區塊：
  ```json
  {
    "workcenter_mapping": {
      "loaded": true,
      "workcenter_count": 18,
      "group_count": 8
    }
  }
  ```

---

### Requirement: API Response Extension

機台狀況表 API 回應 SHALL 擴充新欄位。

#### Scenario: Extended response fields
- **WHEN** 呼叫 `GET /api/resource/status`
- **THEN** 每筆設備資料 SHALL 包含以下新增欄位：
  - `WORKCENTER_GROUP`: 工站分組
  - `WORKCENTER_SHORT`: 工站簡稱
  - `STATUS_CATEGORY`: 狀態分類
  - `JOBORDER`: 維修工單號
  - `JOBSTATUS`: 工單狀態
  - `LOT_COUNT`: 當前 WIP 批次數
  - `TOTAL_TRACKIN_QTY`: Track-In 總數量
  - `LATEST_TRACKIN_TIME`: 最新 Track-In 時間

#### Scenario: Backward compatible response
- **WHEN** 呼叫現有 API
- **THEN** 原有欄位 SHALL 保持不變
- **AND** 新欄位為追加，不影響現有消費者

#### Scenario: Null handling for new fields
- **WHEN** 新欄位資料不存在
- **THEN** 該欄位 SHALL 回傳 `null`（而非省略）

---

### Requirement: Filter Options Extension

篩選選項 API SHALL 新增工站分組選項。

#### Scenario: Workcenter groups in filter options
- **WHEN** 呼叫 `GET /api/resource/status/options`
- **THEN** 回應 SHALL 包含 `workcenter_groups` 欄位
- **AND** 內容為所有 WORK_CENTER_GROUP 清單（按 sequence 排序）

#### Scenario: Status categories in filter options
- **WHEN** 呼叫 `GET /api/resource/status/options`
- **THEN** 回應 SHALL 包含 `status_categories` 欄位
- **AND** 內容為 `['PRODUCTIVE', 'STANDBY', 'DOWN', 'ENGINEERING', 'NOT_SCHEDULED', 'INACTIVE', 'OTHER']`
