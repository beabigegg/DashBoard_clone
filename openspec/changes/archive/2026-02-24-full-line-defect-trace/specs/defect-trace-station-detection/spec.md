## ADDED Requirements

### Requirement: Detection SQL SHALL be parameterized by workcenter group
The system SHALL replace hardcoded TMTT station filtering with a `{{ STATION_FILTER }}` template placeholder in `station_detection.sql`. The filter SHALL be built from `WORKCENTER_GROUPS[station]['patterns']` and `['exclude']` defined in `workcenter_groups.py`, generating OR-LIKE clauses with bind parameters.

#### Scenario: Station filter built from workcenter group patterns
- **WHEN** `station='電鍍'` is requested
- **THEN** the system SHALL build a SQL fragment: `UPPER(h.WORKCENTERNAME) LIKE :wc_p0 OR UPPER(h.WORKCENTERNAME) LIKE :wc_p1 OR ...` with bind values `['%掛鍍%', '%滾鍍%', '%條鍍%', '%電鍍%', '%補鍍%', '%TOTAI%', '%BANDL%']`

#### Scenario: Station filter respects exclude patterns
- **WHEN** `station='切割'` is requested (which has `exclude: ['元件切割', 'PKG_SAW']`)
- **THEN** the filter SHALL include patterns for '切割' AND exclude patterns via `AND UPPER(h.WORKCENTERNAME) NOT LIKE :wc_ex0 AND NOT LIKE :wc_ex1`

#### Scenario: Default station is 測試
- **WHEN** no `station` parameter is provided
- **THEN** the system SHALL default to `station='測試'` (patterns: `['TMTT', '測試']`)
- **THEN** results SHALL be equivalent to the previous hardcoded TMTT behavior

### Requirement: station_detection.sql SHALL generalize tmtt_detection.sql
`station_detection.sql` SHALL be a new SQL file that replaces `tmtt_detection.sql` with parameterized station filtering. Column aliases SHALL use `DETECTION_` prefix instead of `TMTT_` prefix.

#### Scenario: SQL column renaming
- **WHEN** `station_detection.sql` is executed
- **THEN** output columns SHALL include `DETECTION_EQUIPMENTID` and `DETECTION_EQUIPMENTNAME` (not `TMTT_EQUIPMENTID` / `TMTT_EQUIPMENTNAME`)

#### Scenario: Both WIP and reject CTEs use station filter
- **WHEN** the SQL is executed
- **THEN** both the WIP history CTE and the reject history CTE SHALL apply `{{ STATION_FILTER }}` to filter by the selected station

### Requirement: Station options endpoint SHALL return all workcenter groups
`GET /api/mid-section-defect/station-options` SHALL return the 12 workcenter groups from `WORKCENTER_GROUPS` as an ordered list with `name` and `order` fields.

#### Scenario: Station options response format
- **WHEN** the endpoint is called
- **THEN** it SHALL return a JSON array of 12 objects: `[{"name": "切割", "order": 0}, {"name": "焊接_DB", "order": 1}, ...]` sorted by order

### Requirement: All API endpoints SHALL accept station and direction parameters
All `/api/mid-section-defect/*` endpoints (`/analysis`, `/analysis/detail`, `/loss-reasons`, `/export`) SHALL accept `station` (string, default `'測試'`) and `direction` (string, `'backward'` | `'forward'`, default `'backward'`) query parameters.

#### Scenario: Parameters passed to service layer
- **WHEN** `/api/mid-section-defect/analysis?station=成型&direction=forward` is called
- **THEN** `query_analysis()` SHALL receive `station='成型'` and `direction='forward'`

#### Scenario: Invalid station rejected
- **WHEN** a station name not in `WORKCENTER_GROUPS` is provided
- **THEN** the endpoint SHALL return HTTP 400 with an error message

### Requirement: Cache key SHALL include station and direction
The cache key for analysis results SHALL include `station` and `direction` to prevent cross-contamination between different query contexts.

#### Scenario: Different station/direction combinations cached separately
- **WHEN** `station=測試, direction=backward` is queried, then `station=成型, direction=forward` is queried
- **THEN** each SHALL have its own independent cache entry
