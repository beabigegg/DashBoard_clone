# unified-spool-pipeline Specification

## Purpose
Define the common RQ -> Parquet spool -> DuckDB execution model for heavy non-realtime reports.

## Requirements
### Requirement: Non-realtime reports SHALL converge on RQ→Parquet→DuckDB execution
All non-realtime report queries (reject-history, yield-alert, resource-history, hold-overview, production-history, MSD trace, query-tool trace, material-trace) SHALL ultimately execute heavy Oracle work in RQ workers and persist intermediate/final results to parquet spool files. Subsequent aggregation, filtering, pagination, sorting, and export SHALL read from parquet via DuckDB where practical.

#### Scenario: Spool hit
- **WHEN** a valid spool exists for a report query
- **THEN** the route SHALL reuse that spool and avoid re-querying Oracle

#### Scenario: Spool miss
- **WHEN** a report query has no valid spool
- **THEN** the system SHALL execute the Oracle work through the unified spool pipeline
- **THEN** the externally visible HTTP behavior MAY be either compatibility-preserving sync bootstrap or `202 + polling`, depending on the report's existing API contract and migration state

### Requirement: Unified spool pipeline SHALL support multi-stage jobs
Reports that require multiple Oracle stages SHALL execute those stages within a single logical pipeline with stage-aware progress and stage-level spool metadata.

#### Scenario: Multi-stage execution
- **WHEN** a report requires seed, lineage, events, and aggregation stages
- **THEN** each stage SHALL produce its own spool artifact or registered stage output
- **THEN** the pipeline SHALL expose stage progress through shared async job metadata

### Requirement: Unified spool pipeline SHALL preserve compatibility contracts until migration completes
The adoption of the unified spool pipeline SHALL NOT by itself authorize removal of existing endpoints or changes to response semantics that are still consumed by frontend code, AI function registry entries, tests, or documented API contracts.

#### Scenario: Existing synchronous bootstrap contract
- **WHEN** a route currently returns first-page data synchronously
- **THEN** the route MAY keep that external behavior while moving its internal execution to the unified spool pipeline

#### Scenario: Endpoint retirement
- **WHEN** a legacy endpoint is proposed for removal
- **THEN** all known consumers, tests, and contract documents SHALL be migrated first

### Requirement: Hard limits SHALL only be removed after the corresponding legacy path is retired
Row/CID/RSS guards that currently protect in-memory or sync paths SHALL remain until the relevant query path is fully migrated to the spool-safe execution model.

#### Scenario: Trace events guard retirement
- **WHEN** trace events are guaranteed to execute through RQ/spool-safe paths
- **THEN** CID and sync RSS rejection guards MAY be removed

#### Scenario: Legacy path still active
- **WHEN** a compatibility or sync path still exists
- **THEN** existing protection limits SHALL NOT be removed prematurely
