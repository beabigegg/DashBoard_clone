## Purpose

This capability defines the spool-only L2 write path for dataset cache domains (reject, hold, resource). Instead of serializing query result DataFrames as Parquet+base64 Redis payloads, all three domains store only a spool metadata pointer in Redis and persist the actual data as a Parquet spool file on disk. A feature flag (`PHASE2_METADATA_ONLY`) controls whether this path is active.

## Requirements

### Requirement: Dataset cache domains SHALL store query results as spool metadata pointers, not Redis DataFrame payloads
Covered heavy-query domains SHALL use spool metadata pointers as the canonical Redis representation for reusable result bodies. Redis SHALL store metadata, lifecycle state, and lightweight indexes, while the reusable result body SHALL live in Parquet spool.

#### Scenario: Direct-path heavy-query result stored as spool
- **WHEN** a covered heavy-query module completes a direct or chunked primary query and produces a reusable result set
- **THEN** the module SHALL write the result body to Parquet spool and register a Redis metadata pointer
- **THEN** the module SHALL NOT store the full result body in Redis as JSON, pickled payload, or Redis DataFrame blob

#### Scenario: Redis metadata pointer persisted
- **WHEN** a spool-backed result is published
- **THEN** Redis SHALL store only lightweight state such as `query_id`, `relative_path`, `row_count`, `created_at`, `expires_at`, `status`, `file_size_bytes`, and optional stage/index metadata
- **THEN** the Redis metadata SHALL be sufficient for view, export, and async job replay to locate the canonical spool

#### Scenario: Cache hit reads from spool metadata
- **WHEN** a heavy-query result is reused
- **THEN** the module SHALL resolve the result from Redis metadata and the canonical Parquet spool
- **THEN** the module SHALL NOT treat Redis payload storage as the primary reusable result source

#### Scenario: Trace and async domains follow the same rule
- **WHEN** a trace, lineage, history, export, or other heavy async domain produces a replayable result
- **THEN** the result body SHALL follow the same metadata-only Redis rule
- **THEN** Redis SHALL be limited to metadata, state, locks, progress, and lightweight indexes for that result

#### Scenario: Transition fallback during rolling deployment
- **WHEN** `_get_cached_df()` finds no spool metadata pointer for a query_id but a Redis DataFrame key exists (in-flight from old deployment)
- **THEN** the system SHALL attempt `redis_load_df()` as a fallback
- **THEN** the fallback SHALL be logged at DEBUG level

#### Scenario: store_spooled_df failure does not silently hide data loss
- **WHEN** `store_spooled_df()` fails (disk full, permission error)
- **THEN** the system SHALL log an error and return a query response indicating `spool_ready=false`
- **THEN** the system SHALL NOT silently fall back to the old `redis_store_df()` path

### Requirement: Dataset cache metadata-only mode SHALL be controlled by a feature flag
The `PHASE2_METADATA_ONLY` environment variable SHALL control whether the new spool-only write path is active.

#### Scenario: Feature flag enabled (default)
- **WHEN** environment variable `PHASE2_METADATA_ONLY` is set to `1` or not set
- **THEN** all three domains (reject, hold, resource) SHALL use `store_spooled_df()` as the sole L2 write path
- **THEN** `redis_store_df()` SHALL NOT be called for result DataFrames

#### Scenario: Feature flag disabled (rollback)
- **WHEN** environment variable `PHASE2_METADATA_ONLY` is set to `0`
- **THEN** all three domains SHALL fall back to `redis_store_df()` as the L2 write path
- **THEN** behavior SHALL be identical to Phase 1 baseline

### Requirement: Heavy-query metadata SHALL distinguish result body, sidecar data, and control state
Covered modules SHALL separate canonical result bodies from sidecar data and control-plane state so that Redis usage remains bounded and intentional.

#### Scenario: Sidecar data stored in Redis
- **WHEN** a module stores small reusable sidecar data such as linkage maps, stage manifests, or pagination indexes
- **THEN** that data SHALL be materially smaller than the canonical result body
- **THEN** the canonical result body SHALL still remain in Parquet spool

#### Scenario: Inflight and progress state
- **WHEN** a module tracks query execution state
- **THEN** inflight locks, progress records, and async job metadata SHALL be stored as control-plane metadata
- **THEN** those records SHALL not be treated as cache payloads
