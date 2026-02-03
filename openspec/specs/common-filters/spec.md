## Requirements

### Requirement: 廠區排除篩選

系統 SHALL 提供 `add_location_exclusion()` 方法，排除設定檔中定義的廠區。

#### Scenario: 排除設定的廠區
- **WHEN** `EXCLUDED_LOCATIONS = ["ATEC", "F區"]`
- **AND** 呼叫 `CommonFilters.add_location_exclusion(builder)`
- **THEN** 產生條件 `(LOCATIONNAME IS NULL OR LOCATIONNAME NOT IN (:p0, :p1))`

#### Scenario: 無排除廠區時不產生條件
- **WHEN** `EXCLUDED_LOCATIONS = []`
- **AND** 呼叫 `CommonFilters.add_location_exclusion(builder)`
- **THEN** 不新增任何條件

### Requirement: 資產狀態排除篩選

系統 SHALL 提供 `add_asset_status_exclusion()` 方法，排除設定檔中定義的資產狀態。

#### Scenario: 排除設定的資產狀態
- **WHEN** `EXCLUDED_ASSET_STATUSES = ["報廢", "閒置"]`
- **AND** 呼叫 `CommonFilters.add_asset_status_exclusion(builder)`
- **THEN** 產生條件 `(PJ_ASSETSSTATUS IS NULL OR PJ_ASSETSSTATUS NOT IN (:p0, :p1))`

### Requirement: WIP 基礎篩選

系統 SHALL 提供 `add_wip_base_filters()` 方法，處理 WIP 查詢的常用篩選條件。

#### Scenario: 工單模糊搜尋
- **WHEN** 呼叫 `CommonFilters.add_wip_base_filters(builder, workorder="WO123")`
- **THEN** 產生 LIKE 條件搜尋 WORKORDER 欄位

#### Scenario: 批號模糊搜尋
- **WHEN** 呼叫 `CommonFilters.add_wip_base_filters(builder, lotid="LOT001")`
- **THEN** 產生 LIKE 條件搜尋 LOTID 欄位

#### Scenario: 多條件組合
- **WHEN** 呼叫 `CommonFilters.add_wip_base_filters(builder, workorder="WO", package="PKG")`
- **THEN** 產生兩個 LIKE 條件，以 AND 連接

### Requirement: 狀態篩選

系統 SHALL 提供 `add_status_filter()` 方法，處理 WIP 狀態篩選。

#### Scenario: 單一狀態篩選
- **WHEN** 呼叫 `CommonFilters.add_status_filter(builder, status="HOLD")`
- **THEN** 產生條件 `STATUS = :p0`

#### Scenario: 多狀態篩選
- **WHEN** 呼叫 `CommonFilters.add_status_filter(builder, statuses=["RUN", "QUEUE"])`
- **THEN** 產生條件 `STATUS IN (:p0, :p1)`

### Requirement: Hold 類型篩選

系統 SHALL 提供 `add_hold_type_filter()` 方法，區分品質與非品質 Hold。

#### Scenario: 品質 Hold 篩選
- **WHEN** 呼叫 `CommonFilters.add_hold_type_filter(builder, hold_type="quality")`
- **THEN** 產生條件排除 `NON_QUALITY_HOLD_REASONS` 中的 Hold 原因

#### Scenario: 非品質 Hold 篩選
- **WHEN** 呼叫 `CommonFilters.add_hold_type_filter(builder, hold_type="non_quality")`
- **THEN** 產生條件僅包含 `NON_QUALITY_HOLD_REASONS` 中的 Hold 原因
