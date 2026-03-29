## Purpose

This capability defines the spool-only L2 write path for dataset cache domains (reject, hold, resource). Instead of serializing query result DataFrames as Parquet+base64 Redis payloads, all three domains store only a spool metadata pointer in Redis and persist the actual data as a Parquet spool file on disk. A feature flag (`PHASE2_METADATA_ONLY`) controls whether this path is active.

## Requirements

### Requirement: Dataset cache domains SHALL store query results as spool metadata pointers, not Redis DataFrame payloads
The reject, hold, and resource dataset cache modules SHALL use `query_spool_store.store_spooled_df()` as the exclusive L2 write path, eliminating Parquet+base64 Redis payloads.

#### Scenario: Direct-path query result stored as spool
- **WHEN** `execute_primary_query()` completes and produces a result DataFrame via the direct (non-engine) path
- **THEN** the system SHALL call `store_spooled_df(namespace, query_id, df, ttl_seconds=_CACHE_TTL)` to write the spool file and register the metadata pointer
- **THEN** the system SHALL NOT call `redis_df_store.redis_store_df()` for the result DataFrame
- **THEN** the Redis key `{namespace}:{query_id}` (Parquet+base64 payload) SHALL NOT be written

#### Scenario: Redis spool metadata pointer persisted
- **WHEN** `store_spooled_df()` succeeds
- **THEN** Redis SHALL contain a key `{namespace}:spool_meta:{query_id}` with fields: `namespace`, `relative_path`, `row_count`, `columns_hash`, `created_at`, `expires_at`, `file_size_bytes`
- **THEN** the in-process L1 marker SHALL be set to `True` for the query_id
- **THEN** the Redis key SHALL expire after 900 seconds

#### Scenario: Cache hit reads from spool metadata
- **WHEN** `_get_cached_df()` / `_load_df_on_demand()` is called with a query_id that has a spool metadata pointer
- **THEN** the system SHALL call `query_spool_store.load_spooled_df()` to retrieve the DataFrame from the spool file
- **THEN** the system SHALL NOT call `redis_df_store.redis_load_df()` as the primary path

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
