## ADDED Requirements

### Requirement: WIP cache updater SHALL write Parquet-only to Redis
The `cache_updater.py` WIP update cycle SHALL write only the Parquet representation (`mes_wip:data:parquet`) to Redis. The JSON representation (`mes_wip:data`) SHALL NOT be written.

#### Scenario: Normal WIP cache update
- **WHEN** `cache_updater` completes a WIP data refresh cycle
- **THEN** the updater SHALL call `redis_store_df()` to write `mes_wip:data:parquet`
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

### Requirement: Stale JSON key SHALL be cleaned up on first update
On the first WIP update cycle after deployment, the updater SHALL delete the `mes_wip:data` key if it exists, to reclaim Redis memory.

#### Scenario: Legacy JSON key exists at first update
- **WHEN** the updater runs and `mes_wip:data` key exists in Redis
- **THEN** the updater SHALL delete `mes_wip:data` within the same pipeline
- **THEN** a log at INFO level SHALL record the cleanup

#### Scenario: Legacy JSON key does not exist
- **WHEN** the updater runs and `mes_wip:data` does not exist in Redis
- **THEN** no error or warning SHALL be emitted
