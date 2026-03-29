## MODIFIED Requirements

### Requirement: WIP cache updater SHALL write Parquet-only to Redis
The `cache_updater.py` WIP update cycle SHALL write only the Parquet representation (`mes_wip:data:parquet`) to Redis. The JSON representation (`mes_wip:data`) SHALL NOT be written.

#### Scenario: Normal WIP cache update
- **WHEN** `cache_updater` completes a WIP data refresh cycle
- **THEN** the updater SHALL call `redis_store_df()` using the canonical raw suffix for the Parquet key so the resulting Redis key is exactly `mes_wip:data:parquet`
- **THEN** the updater SHALL NOT write or rename any key to `mes_wip:data`

#### Scenario: Metadata keys preserved
- **WHEN** `cache_updater` completes a WIP data refresh cycle
- **THEN** `mes_wip:meta:sys_date` and `mes_wip:meta:updated_at` SHALL still be written as before

### Requirement: WIP cache reader SHALL use Parquet-only path
The `get_cached_wip_data()` function in `core/cache.py` SHALL read only from the Parquet Redis key. The JSON fallback branch SHALL be removed.

#### Scenario: Parquet key exists
- **WHEN** `get_cached_wip_data()` is called and `mes_wip:data:parquet` exists in Redis
- **THEN** the function SHALL return the DataFrame parsed from Parquet
- **THEN** no attempt SHALL be made to read `mes_wip:data`

#### Scenario: Parquet key missing
- **WHEN** `get_cached_wip_data()` is called and `mes_wip:data:parquet` does not exist in Redis
- **THEN** the function SHALL return `None`
- **THEN** no attempt SHALL be made to read `mes_wip:data` as fallback

## ADDED Requirements

### Requirement: WIP cache availability probes SHALL inspect the canonical Parquet key
All WIP cache availability and health checks SHALL inspect the same canonical Redis key used by the runtime read/write path.

#### Scenario: Availability probe checks WIP cache
- **WHEN** a health or availability helper verifies whether WIP data is cached
- **THEN** it SHALL check for `mes_wip:data:parquet`
- **THEN** it SHALL NOT treat `mes_wip:data` or a double-prefixed derivative as the primary source of truth
