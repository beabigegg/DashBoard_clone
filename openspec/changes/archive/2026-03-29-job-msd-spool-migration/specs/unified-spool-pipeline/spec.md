## MODIFIED Requirements

### Requirement: Non-realtime reports SHALL converge on RQ→Parquet→DuckDB execution
All non-realtime report queries (reject-history, yield-alert, resource-history, hold-overview, production-history, MSD trace, query-tool trace, material-trace, **job-query, MSD station-detection**) SHALL ultimately execute heavy Oracle work in RQ workers and persist intermediate/final results to parquet spool files. Subsequent aggregation, filtering, pagination, sorting, and export SHALL read from parquet via DuckDB where practical.

#### Scenario: Spool hit
- **WHEN** a valid spool exists for a report query
- **THEN** the route SHALL reuse that spool and avoid re-querying Oracle

#### Scenario: Spool miss
- **WHEN** a report query has no valid spool
- **THEN** the system SHALL execute the Oracle work through the unified spool pipeline
- **THEN** the externally visible HTTP behavior MAY be either compatibility-preserving sync bootstrap or `202 + polling`, depending on the report's existing API contract and migration state

#### Scenario: job_query engine path uses spool
- **WHEN** `job_query_service` uses the batch engine path (long date range via `should_decompose_by_time`)
- **THEN** the engine result SHALL be merged via `merge_chunks_to_spool()` into a parquet spool file
- **THEN** the result SHALL be read from spool via DuckDB, not from a Redis-cached DataFrame

#### Scenario: msd_detect engine path uses spool
- **WHEN** `mid_section_defect_service._fetch_station_detection()` uses the batch engine path (long date range)
- **THEN** the engine result SHALL be merged via `merge_chunks_to_spool()` into a parquet spool file
- **THEN** the result SHALL be read from spool via DuckDB, not from a pandas DataFrame merge
