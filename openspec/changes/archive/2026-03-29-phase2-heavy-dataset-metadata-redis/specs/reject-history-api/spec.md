## ADDED Requirements

### Requirement: Reject dataset cache direct-path SHALL store results via spool metadata, not Redis DataFrame payload
The reject_dataset_cache module's direct-path write function (`_store_df()`) SHALL use `store_spooled_df()` to persist query results, eliminating Parquet+base64 Redis storage for the direct query path.

#### Scenario: Direct-path result stored as spool (Phase 2 enabled)
- **WHEN** `_store_df(query_id, df)` is called with `PHASE2_METADATA_ONLY=1`
- **THEN** the system SHALL call `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`
- **THEN** the system SHALL NOT call `_redis_store_df(query_id, df)`
- **THEN** the L1 in-process marker SHALL be set for the query_id

#### Scenario: Direct-path cache load reads from spool
- **WHEN** `_load_df_on_demand(query_id)` is called with `PHASE2_METADATA_ONLY=1` and a spool file exists
- **THEN** the system SHALL return the DataFrame via `load_spooled_df(_REDIS_NAMESPACE, query_id)`
- **THEN** the system SHALL NOT call `redis_load_df()` as the primary lookup

#### Scenario: Engine-path spool write unaffected
- **WHEN** `_store_query_result()` is called for large engine-path results (existing spill logic)
- **THEN** behavior SHALL be unchanged — `store_spooled_df()` / `register_spool_file()` continue to operate as before
- **THEN** the `PHASE2_METADATA_ONLY` flag SHALL NOT affect engine-path spill behavior

#### Scenario: Direct-path rollback (Phase 2 disabled)
- **WHEN** `_store_df(query_id, df)` is called with `PHASE2_METADATA_ONLY=0`
- **THEN** the system SHALL call `_redis_store_df(query_id, df)` (Phase 1 baseline behavior)
