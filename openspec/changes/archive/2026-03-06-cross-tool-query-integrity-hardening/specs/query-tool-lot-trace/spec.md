## ADDED Requirements

### Requirement: High-volume query-tool detail endpoints SHALL support server-side pagination
High-volume detail endpoints (`lot-history` batch mode, batch associations, and equipment lots) SHALL support server-side pagination to bound payload size.

#### Scenario: Paginated lot-history batch query
- **WHEN** client calls lot-history batch endpoint with `page` and `per_page`
- **THEN** backend SHALL return only the requested page of rows
- **THEN** response SHALL include `pagination` object containing `page`, `per_page`, `total`, and `total_pages`

#### Scenario: Paginated equipment lots query
- **WHEN** client queries equipment lots with `page` and `per_page`
- **THEN** backend SHALL apply pagination before returning response payload
- **THEN** `per_page` SHALL be capped by a configurable upper bound

#### Scenario: Default pagination behavior
- **WHEN** pagination parameters are omitted
- **THEN** endpoint SHALL apply documented default page and page size values
- **THEN** response SHALL still include `pagination` metadata

### Requirement: Query-tool detail responses SHALL include quality metadata
Query-tool detail endpoints backed by EventFetcher SHALL expose non-complete states explicitly.

#### Scenario: Truncated EventFetcher result in detail endpoint
- **WHEN** EventFetcher reports truncated records for a detail query
- **THEN** endpoint response SHALL include `quality_meta.status = "truncated"`
- **THEN** response SHALL include limit/observed row context for diagnostics

#### Scenario: Complete EventFetcher result in detail endpoint
- **WHEN** EventFetcher reports complete records
- **THEN** endpoint response SHALL include `quality_meta.status = "complete"`
