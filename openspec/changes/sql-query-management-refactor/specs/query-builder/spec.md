## ADDED Requirements

### Requirement: 參數化條件建構

系統 SHALL 提供 `QueryBuilder` 類別，建構參數化的 SQL 條件，避免 SQL 注入風險。

#### Scenario: 建構等值條件
- **WHEN** 呼叫 `builder.add_param_condition("status", "RUN")`
- **THEN** 產生條件 `status = :p0` 且 `params = {"p0": "RUN"}`

#### Scenario: 建構 IN 條件
- **WHEN** 呼叫 `builder.add_in_condition("status", ["RUN", "QUEUE", "HOLD"])`
- **THEN** 產生條件 `status IN (:p0, :p1, :p2)`
- **AND** `params = {"p0": "RUN", "p1": "QUEUE", "p2": "HOLD"}`

#### Scenario: 空值 IN 條件不產生語句
- **WHEN** 呼叫 `builder.add_in_condition("status", [])`
- **THEN** 不新增任何條件

### Requirement: LIKE 條件安全處理

系統 SHALL 在建構 LIKE 條件時，自動跳脫 SQL 萬用字元（`%` 和 `_`）。

#### Scenario: 跳脫 LIKE 萬用字元
- **WHEN** 呼叫 `builder.add_like_condition("name", "test%value")`
- **THEN** 產生條件 `name LIKE :p0 ESCAPE '\'`
- **AND** `params = {"p0": "%test\\%value%"}`

#### Scenario: LIKE 位置控制
- **WHEN** 呼叫 `builder.add_like_condition("name", "prefix", position="start")`
- **THEN** `params = {"p0": "prefix%"}`（不含前綴 %）

### Requirement: WHERE 子句組合

系統 SHALL 自動組合多個條件為完整的 WHERE 子句。

#### Scenario: 多條件 AND 組合
- **WHEN** 新增多個條件後呼叫 `builder.build()`
- **THEN** 產生 `WHERE cond1 AND cond2 AND cond3`

#### Scenario: 無條件時不產生 WHERE
- **WHEN** 未新增任何條件即呼叫 `builder.build()`
- **THEN** `{{ WHERE_CLAUSE }}` 被替換為空字串

### Requirement: NOT IN 條件建構

系統 SHALL 支援 NOT IN 條件，用於排除特定值。

#### Scenario: 建構 NOT IN 條件
- **WHEN** 呼叫 `builder.add_not_in_condition("location", ["ATEC", "F區"])`
- **THEN** 產生條件 `location NOT IN (:p0, :p1)`

#### Scenario: NOT IN 處理 NULL 值
- **WHEN** 呼叫 `builder.add_not_in_condition("location", values, allow_null=True)`
- **THEN** 產生條件 `(location IS NULL OR location NOT IN (...))`
