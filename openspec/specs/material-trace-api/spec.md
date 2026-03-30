## Purpose
Define the Material Trace API contract for forward/reverse trace queries and CSV export behavior.
## Requirements
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

### Requirement: Material Trace export SHALL stream CSV output
`POST /api/material-trace/export` SHALL stream CSV content incrementally instead of materializing full CSV bytes in memory before response.

#### Scenario: Streaming export for large result set
- **WHEN** export result contains many rows
- **THEN** response SHALL be produced via streaming generator/chunked writing
- **THEN** service SHALL not require a single in-memory CSV blob for the full dataset

#### Scenario: Streaming export preserves existing CSV contract
- **WHEN** export is streamed
- **THEN** CSV column order, BOM behavior, and filename contract SHALL remain backward-compatible

### Requirement: Material Trace query/export SHALL emit quality metadata
Material Trace query and export responses SHALL explicitly mark complete vs truncated outcomes.

#### Scenario: Forward query truncation metadata
- **WHEN** forward query exceeds configured row guard
- **THEN** query response metadata SHALL include `quality_meta.status = "truncated"`
- **THEN** metadata SHALL include truncation limit context

#### Scenario: Export truncation metadata
- **WHEN** export exceeds configured export max rows
- **THEN** export response SHALL include explicit truncation markers (response headers and metadata)
- **THEN** truncation markers SHALL be machine-readable for frontend/client handling

#### Scenario: Complete query metadata
- **WHEN** query completes without truncation
- **THEN** response SHALL include `quality_meta.status = "complete"`

### Requirement: Material Trace memory-pressure rejection SHALL use service-unavailable semantics
Memory guard failures on Material Trace endpoints SHALL be reported as retryable service overload, not request validation failure.

#### Scenario: Query memory guard rejection
- **WHEN** `POST /api/material-trace/query` hits memory guard
- **THEN** endpoint SHALL return HTTP `503 SERVICE_UNAVAILABLE`
- **THEN** response SHALL include a retryable overload message and `Retry-After` header

#### Scenario: Export memory guard rejection
- **WHEN** `POST /api/material-trace/export` hits memory guard
- **THEN** endpoint SHALL return HTTP `503 SERVICE_UNAVAILABLE`
- **THEN** response contract SHALL remain distinguishable from parameter-validation errors (`400`)

### Requirement: Material trace SHALL migrate to spool-backed execution
Material trace query and export SHALL use canonical heavy-query storage: the reusable result body SHALL live in Parquet spool and all pagination, replay, and export behavior SHALL read from the canonical spool-backed result.

#### Scenario: Spool hit
- **WHEN** a material trace request matches a valid canonical spool-backed result
- **THEN** the route SHALL return paginated/query results from the spool-backed runtime without rerunning Oracle work

#### Scenario: Spool miss
- **WHEN** no canonical spool-backed result exists for the request
- **THEN** the system SHALL create one through the heavy-query execution path before the result becomes reusable
- **THEN** Redis SHALL not become the canonical body store for that result

#### Scenario: Export from canonical result
- **WHEN** a client exports material trace results
- **THEN** the export SHALL read from the same canonical spool-backed result identity used by query pagination and replay
- **THEN** export behavior SHALL not require a separate full-result Redis or in-memory body cache

### Requirement: Material trace row-limit retirement SHALL follow async/runtime migration
The existing `_REVERSE_MAX_ROWS`, `_FORWARD_MAX_ROWS`, and `_EXPORT_MAX_ROWS` limits SHALL only be removed after spool-backed runtime and frontend async handling are in place.

#### Scenario: Legacy path still active
- **WHEN** the legacy sync/materialization path is still in service
- **THEN** current safety limits SHALL remain

#### Scenario: Migration complete
- **WHEN** spool-backed query, pagination, export, and frontend polling support are complete
- **THEN** the legacy row limits MAY be removed
