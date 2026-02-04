## ADDED Requirements

### Requirement: Query type selection
The system SHALL provide query type selection with three LIKE modes in addition to the existing IN clause.

#### Scenario: Query type options display
- **WHEN** user views the query configuration section
- **THEN** the system SHALL display the following query type options:
  - 完全符合 (WHERE IN) - default
  - 包含 (LIKE %...%)
  - 開頭符合 (LIKE ...%)
  - 結尾符合 (LIKE %...)

#### Scenario: Query type default
- **WHEN** user opens the Excel query page
- **THEN** the query type SHALL default to "完全符合 (WHERE IN)"

### Requirement: LIKE contains query
The system SHALL support LIKE contains queries that match values anywhere in the column.

#### Scenario: Single keyword contains search
- **WHEN** user selects "包含" query type with keyword "ABC"
- **THEN** the system SHALL generate SQL: `WHERE {column} LIKE '%ABC%'`

#### Scenario: Multiple keywords contains search
- **WHEN** user selects "包含" query type with keywords ["ABC", "DEF", "GHI"]
- **THEN** the system SHALL generate SQL: `WHERE {column} LIKE '%ABC%' OR {column} LIKE '%DEF%' OR {column} LIKE '%GHI%'`

### Requirement: LIKE prefix query
The system SHALL support LIKE prefix queries that match values starting with the search term.

#### Scenario: Prefix search
- **WHEN** user selects "開頭符合" query type with keyword "ABC"
- **THEN** the system SHALL generate SQL: `WHERE {column} LIKE 'ABC%'`

### Requirement: LIKE suffix query
The system SHALL support LIKE suffix queries that match values ending with the search term.

#### Scenario: Suffix search
- **WHEN** user selects "結尾符合" query type with keyword "ABC"
- **THEN** the system SHALL generate SQL: `WHERE {column} LIKE '%ABC'`

### Requirement: LIKE query keyword limit
The system SHALL limit the number of keywords for LIKE queries to prevent performance issues.

#### Scenario: Keyword count within limit
- **WHEN** user provides 100 or fewer keywords for LIKE query
- **THEN** the system SHALL execute the query normally

#### Scenario: Keyword count exceeds limit
- **WHEN** user provides more than 100 keywords for LIKE query
- **THEN** the system SHALL display error: "LIKE 查詢最多支援 100 個關鍵字"
- **AND** the query execution SHALL be blocked

### Requirement: LIKE query performance warning
The system SHALL warn users about potential performance impact when using LIKE contains on large tables.

#### Scenario: Large table warning for contains query
- **WHEN** user selects "包含" query type on a table with row_count > 10,000,000
- **THEN** the system SHALL display warning: "此資料表超過 1000 萬筆，包含查詢可能較慢，建議配合日期範圍縮小查詢範圍"

#### Scenario: No warning for prefix query
- **WHEN** user selects "開頭符合" query type
- **THEN** the system SHALL NOT display performance warning (prefix can use index)

### Requirement: LIKE query special character escaping
The system SHALL properly escape special characters in LIKE patterns.

#### Scenario: Escape underscore
- **WHEN** user searches for keyword containing "_"
- **THEN** the system SHALL escape it as "\_" in the LIKE pattern

#### Scenario: Escape percent
- **WHEN** user searches for keyword containing "%"
- **THEN** the system SHALL escape it as "\%" in the LIKE pattern
