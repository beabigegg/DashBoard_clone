## ADDED Requirements

### Requirement: Excel column type detection
The system SHALL analyze Excel column values and detect their data type.

#### Scenario: Detect date type
- **WHEN** Excel column contains values matching pattern `YYYY-MM-DD` or `YYYY/MM/DD`
- **THEN** the system SHALL classify the column as type "date"
- **AND** display type label "日期"

#### Scenario: Detect datetime type
- **WHEN** Excel column contains values matching pattern `YYYY-MM-DD HH:MM` or `YYYY-MM-DDTHH:MM`
- **THEN** the system SHALL classify the column as type "datetime"
- **AND** display type label "日期時間"

#### Scenario: Detect number type
- **WHEN** Excel column contains values matching pattern `^-?\d+\.?\d*$`
- **THEN** the system SHALL classify the column as type "number"
- **AND** display type label "數值"

#### Scenario: Detect ID type
- **WHEN** Excel column contains values matching pattern `^[A-Z0-9_-]+$` (uppercase alphanumeric with underscore/hyphen)
- **THEN** the system SHALL classify the column as type "id"
- **AND** display type label "識別碼"

#### Scenario: Default to text type
- **WHEN** Excel column does not match any specific pattern
- **THEN** the system SHALL classify the column as type "text"
- **AND** display type label "文字"

#### Scenario: Type detection sampling
- **WHEN** system performs type detection
- **THEN** the system SHALL sample the first 100 non-empty values
- **AND** classify based on majority pattern match (>80%)

### Requirement: Oracle column metadata retrieval
The system SHALL retrieve column metadata from Oracle database for the selected table.

#### Scenario: Successful metadata retrieval
- **WHEN** user selects a table
- **THEN** the system SHALL query `ALL_TAB_COLUMNS` for column information
- **AND** return: COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE

#### Scenario: Metadata query permission denied
- **WHEN** user lacks permission to query `ALL_TAB_COLUMNS`
- **THEN** the system SHALL fallback to `SELECT * FROM {table} WHERE ROWNUM <= 1` method
- **AND** return column names without type information

### Requirement: Table metadata API endpoint
The system SHALL provide a new API endpoint `/api/excel-query/table-metadata` for retrieving enriched table information.

#### Scenario: Table metadata response
- **WHEN** client calls `POST /api/excel-query/table-metadata` with `{"table_name": "DWH.DW_MES_WIP"}`
- **THEN** the system SHALL return:
  - columns: array of `{name, data_type, is_date, is_number}`
  - time_field: string or null (from TABLES_CONFIG)
  - description: string (from TABLES_CONFIG)
  - row_count: number (from TABLES_CONFIG)

### Requirement: Column type display in UI
The system SHALL display column type information in the query column selection interface.

#### Scenario: Oracle column type badges
- **WHEN** user views the query column selection dropdown
- **THEN** each column SHALL display a type badge:
  - VARCHAR2/CHAR → "文字"
  - NUMBER → "數值"
  - DATE/TIMESTAMP → "日期"

#### Scenario: Excel column type badges
- **WHEN** user views the Excel column selection dropdown
- **THEN** each column SHALL display the detected type badge

### Requirement: Column type matching suggestion
The system SHALL suggest compatible column matches between Excel and Oracle columns.

#### Scenario: Type-compatible suggestion
- **WHEN** user selects an Excel column with detected type "id"
- **THEN** the system SHALL highlight Oracle columns with VARCHAR2 type as "建議"

#### Scenario: Type-incompatible warning
- **WHEN** user selects an Excel date column but Oracle target column is NUMBER type
- **THEN** the system SHALL display warning: "欄位類型不相符，可能導致查詢結果為空"
