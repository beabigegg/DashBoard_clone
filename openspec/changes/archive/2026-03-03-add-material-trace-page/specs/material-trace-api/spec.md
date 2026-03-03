## ADDED Requirements

### Requirement: Material Trace API SHALL provide forward query endpoint
The API SHALL accept LOT IDs or work order numbers and return corresponding material consumption records from `DW_MES_LOTMATERIALSHISTORY`.

#### Scenario: Forward query by LOT ID
- **WHEN** `POST /api/material-trace/query` is called with `mode: "lot"` and `values: ["GA25060001-A01", "GA25060502"]`
- **THEN** the API SHALL resolve LOT names to CONTAINERIDs via `DW_MES_CONTAINER`
- **THEN** the API SHALL return material consumption records matching those CONTAINERIDs
- **THEN** each record SHALL include CONTAINERID, CONTAINERNAME, PJ_WORKORDER, WORKCENTERNAME, WORKCENTER_GROUP, MATERIALPARTNAME, MATERIALLOTNAME, VENDORLOTNUMBER, QTYREQUIRED, QTYCONSUMED, EQUIPMENTNAME, TXNDATE, PRIMARY_CATEGORY, SECONDARY_CATEGORY

#### Scenario: Forward query by work order
- **WHEN** `POST /api/material-trace/query` is called with `mode: "workorder"` and `values: ["WO-2025-001", "WO-2025-002"]`
- **THEN** the API SHALL query `DW_MES_LOTMATERIALSHISTORY` using `PJ_WORKORDER` index directly
- **THEN** the response format SHALL be identical to LOT ID mode

#### Scenario: Forward query with workcenter group filter
- **WHEN** `POST /api/material-trace/query` includes `workcenter_groups: ["焊接_DB"]`
- **THEN** the API SHALL resolve group names to WORKCENTERNAME list via `filter_cache.get_workcenter_mapping()`
- **THEN** the SQL query SHALL include `AND WORKCENTERNAME IN (...)` filter
- **THEN** results SHALL only contain records from workcenters belonging to the selected groups

#### Scenario: Forward query input limit
- **WHEN** `POST /api/material-trace/query` with `mode: "lot"` or `mode: "workorder"` contains more than 200 values
- **THEN** the API SHALL return HTTP 400 with error message indicating the 200-value limit

### Requirement: Material Trace API SHALL provide reverse query endpoint
The API SHALL accept material lot names and return LOTs that consumed those materials.

#### Scenario: Reverse query by material lot name
- **WHEN** `POST /api/material-trace/query` is called with `mode: "material_lot"` and `values: ["WIRE-LOT-20250101-A"]`
- **THEN** the API SHALL query `DW_MES_LOTMATERIALSHISTORY` using `MATERIALLOTNAME` index
- **THEN** each record SHALL include the same fields as forward query results

#### Scenario: Reverse query with workcenter group filter
- **WHEN** reverse query includes `workcenter_groups` parameter
- **THEN** the same workcenter group filtering logic as forward query SHALL apply

#### Scenario: Reverse query input limit
- **WHEN** `POST /api/material-trace/query` with `mode: "material_lot"` contains more than 50 values
- **THEN** the API SHALL return HTTP 400 with error message indicating the 50-value limit

#### Scenario: Reverse query result limit
- **WHEN** reverse query results exceed 10,000 rows
- **THEN** the API SHALL return exactly 10,000 rows
- **THEN** the response `meta` SHALL include `truncated: true` and `max_rows: 10000`

### Requirement: Material Trace API SHALL validate query parameters
The API SHALL validate input parameters before executing database queries.

#### Scenario: Missing required fields
- **WHEN** `POST /api/material-trace/query` is called without `mode` or `values`
- **THEN** the API SHALL return HTTP 400 with descriptive validation error

#### Scenario: Invalid mode
- **WHEN** `mode` is not one of `lot`, `workorder`, `material_lot`
- **THEN** the API SHALL return HTTP 400

#### Scenario: Empty values
- **WHEN** `values` is an empty array or all values are blank after trimming
- **THEN** the API SHALL return HTTP 400 with error message "請輸入至少一筆查詢條件"

#### Scenario: Unresolvable LOT IDs
- **WHEN** some LOT names cannot be resolved to CONTAINERIDs
- **THEN** the API SHALL proceed with the resolved subset
- **THEN** the response `meta` SHALL include `unresolved` array listing unresolvable LOT names

### Requirement: Material Trace API SHALL support paginated results
The API SHALL support server-side pagination for query results.

#### Scenario: Pagination parameters
- **WHEN** `POST /api/material-trace/query` includes `page` and `per_page`
- **THEN** results SHALL be paginated accordingly
- **THEN** response SHALL include `pagination: { page, per_page, total, total_pages }`

#### Scenario: Default pagination
- **WHEN** `page` or `per_page` is not provided
- **THEN** `page` SHALL default to 1
- **THEN** `per_page` SHALL default to 50

#### Scenario: Per-page cap
- **WHEN** `per_page` exceeds 200
- **THEN** `per_page` SHALL be capped at 200

### Requirement: Material Trace API SHALL provide CSV export endpoint
The API SHALL provide CSV export using the same query parameters as the query endpoint.

#### Scenario: Export request
- **WHEN** `POST /api/material-trace/export` is called with the same parameters as query
- **THEN** the response SHALL be a CSV file with UTF-8 BOM encoding
- **THEN** CSV headers SHALL be in Chinese
- **THEN** all matching records SHALL be included (no pagination, subject to result limits)

#### Scenario: Export result limit
- **WHEN** export results exceed 50,000 rows
- **THEN** the export SHALL be truncated at 50,000 rows
- **THEN** a warning header SHALL indicate truncation

### Requirement: Material Trace API SHALL enrich results with workcenter group
The API SHALL add WORKCENTER_GROUP to each result row based on `filter_cache.get_workcenter_mapping()`.

#### Scenario: Workcenter group enrichment
- **WHEN** query results are returned
- **THEN** each row SHALL include a `WORKCENTER_GROUP` field
- **THEN** the value SHALL be resolved from `filter_cache.get_workcenter_mapping()` using the row's `WORKCENTERNAME`

#### Scenario: Unknown workcenter
- **WHEN** a row's WORKCENTERNAME has no mapping in the workcenter cache
- **THEN** `WORKCENTER_GROUP` SHALL be empty string

### Requirement: Material Trace API SHALL apply rate limiting
The API SHALL rate-limit query and export endpoints to protect Oracle resources.

#### Scenario: Query rate limit
- **WHEN** `/api/material-trace/query` receives excessive requests
- **THEN** requests beyond 30 per 60 seconds SHALL be rejected with HTTP 429

#### Scenario: Export rate limit
- **WHEN** `/api/material-trace/export` receives excessive requests
- **THEN** requests beyond 10 per 60 seconds SHALL be rejected with HTTP 429
