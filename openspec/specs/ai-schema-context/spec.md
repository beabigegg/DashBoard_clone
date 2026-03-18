# ai-schema-context Specification

## Purpose
TBD - created by archiving change ai-text-to-sql-migration. Update Purpose after archive.
## Requirements
### Requirement: Table domain grouping
The module SHALL define a `TABLE_DOMAINS` dictionary mapping domain keys to their associated tables, keyword triggers, and descriptions. Domain keys SHALL include at minimum: `wip_realtime`, `lot_history`, `reject`, `hold`, `equipment`, `material`, `job`, `genealogy`, `yield`, `wip_data`.

#### Scenario: Domain lookup
- **WHEN** Stage 1 returns `domains: ["wip_realtime"]`
- **THEN** the system SHALL resolve tables `DWH.DW_MES_LOT_V` and `DWH.DW_MES_EQUIPMENTSTATUS_WIP_V` from the domain definition

#### Scenario: All 22 authorized tables covered
- **WHEN** all domain table lists are combined
- **THEN** every table in `docs/Oracle_Authorized_Objects.md` (22 objects) SHALL appear in at least one domain

### Requirement: Condensed table schemas from SQL template analysis
The module SHALL provide a `TABLE_SCHEMAS` dictionary mapping each table name to a condensed schema string containing only columns that appear in the project's SQL templates (`sql/**/*.sql`). Each column entry SHALL include column name, data type, and a Chinese business-context comment.

#### Scenario: Schema contains only used columns
- **WHEN** the schema for `DWH.DW_MES_LOT_V` is retrieved
- **THEN** it SHALL contain 10-20 columns (not the full 72 columns from `table_schema_info.json`)
- **AND** every listed column SHALL appear in at least one SQL file under `sql/`

#### Scenario: Schema includes data types from table_schema_info.json
- **WHEN** a column is listed in a table schema
- **THEN** its data type SHALL match the type defined in `data/table_schema_info.json`

### Requirement: Few-shot SQL examples per domain
The module SHALL provide a `SQL_EXAMPLES` dictionary mapping domain keys to lists of example objects. Each example SHALL contain `question` (Chinese natural language) and `sql` (executable Oracle SELECT with bind variables).

#### Scenario: Examples are valid SQL
- **WHEN** any SQL example is examined
- **THEN** it SHALL be a SELECT statement, use only tables from the associated domain, and include `FETCH FIRST N ROWS ONLY`

#### Scenario: Examples cover common user patterns
- **WHEN** the examples for `wip_realtime` domain are examined
- **THEN** they SHALL include at least one equipment-level query and one WIP summary query

### Requirement: Schema extraction development script
The project SHALL include `scripts/extract_sql_schema.py` that scans `sql/**/*.sql`, extracts table and column references, cross-references with `data/table_schema_info.json`, and outputs a frequency-ranked column list per table. This script is a development tool, not used at runtime.

#### Scenario: Script execution
- **WHEN** `scripts/extract_sql_schema.py` is executed
- **THEN** it SHALL output each table name with its columns sorted by usage frequency across SQL files

