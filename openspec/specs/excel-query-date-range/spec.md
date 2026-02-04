## ADDED Requirements

### Requirement: Time field auto-detection
The system SHALL automatically identify the time field for each table based on `TABLES_CONFIG.time_field` configuration.

#### Scenario: Table has configured time field
- **WHEN** user selects a table with `time_field` defined in `TABLES_CONFIG`
- **THEN** the system SHALL display the time field name in the UI
- **AND** the date range filter section SHALL be enabled

#### Scenario: Table has no time field
- **WHEN** user selects a table without `time_field` in `TABLES_CONFIG`
- **THEN** the date range filter section SHALL be disabled
- **AND** a message "此資料表無時間欄位" SHALL be displayed

### Requirement: Date range filter UI
The system SHALL provide date range input controls in the advanced conditions section.

#### Scenario: Default date range
- **WHEN** user enables date range filtering
- **THEN** the system SHALL default to the last 90 days
- **AND** both start and end date inputs SHALL be displayed

#### Scenario: Custom date range selection
- **WHEN** user enters a custom start date and end date
- **THEN** the system SHALL validate that start date is before or equal to end date
- **AND** the system SHALL validate that the range does not exceed 365 days

#### Scenario: Date range validation failure
- **WHEN** user enters an invalid date range (start > end or range > 365 days)
- **THEN** the system SHALL display an error message
- **AND** the query execution SHALL be blocked

### Requirement: Date range SQL generation
The system SHALL generate Oracle-compatible date range conditions using parameterized queries.

#### Scenario: Both dates specified
- **WHEN** user specifies both start and end dates
- **THEN** the system SHALL generate SQL: `WHERE {time_column} BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD') AND TO_DATE(:date_to, 'YYYY-MM-DD') + 1`

#### Scenario: Only start date specified
- **WHEN** user specifies only start date
- **THEN** the system SHALL generate SQL: `WHERE {time_column} >= TO_DATE(:date_from, 'YYYY-MM-DD')`

#### Scenario: Only end date specified
- **WHEN** user specifies only end date
- **THEN** the system SHALL generate SQL: `WHERE {time_column} <= TO_DATE(:date_to, 'YYYY-MM-DD') + 1`

### Requirement: Date range combined with IN condition
The system SHALL support combining date range with existing IN clause conditions using AND.

#### Scenario: Combined query execution
- **WHEN** user specifies both date range and IN clause values
- **THEN** the system SHALL generate SQL combining both conditions: `WHERE {search_column} IN (...) AND {time_column} BETWEEN ...`
- **AND** the batch processing logic SHALL apply to the IN clause portion
