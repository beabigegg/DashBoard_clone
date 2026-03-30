# wip-cache-parquet-only Specification

## Purpose
Normalize the WIP cache to use only the Parquet Redis representation, removing the legacy JSON key to reduce Redis memory consumption and simplify the read path.

## Requirements

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

### Requirement: Stale JSON key SHALL be cleaned up on first update
On the first WIP update cycle after deployment, the updater SHALL delete the `mes_wip:data` key if it exists, to reclaim Redis memory.

#### Scenario: Legacy JSON key exists at first update
- **WHEN** the updater runs and `mes_wip:data` key exists in Redis
- **THEN** the updater SHALL delete `mes_wip:data` within the same pipeline
- **THEN** a log at INFO level SHALL record the cleanup

#### Scenario: Legacy JSON key does not exist
- **WHEN** the updater runs and `mes_wip:data` does not exist in Redis
- **THEN** no error or warning SHALL be emitted

### Requirement: WIP cache availability probes SHALL inspect the canonical Parquet key
All WIP cache availability and health checks SHALL inspect the same canonical Redis key used by the runtime read/write path.

#### Scenario: Availability probe checks WIP cache
- **WHEN** a health or availability helper verifies whether WIP data is cached
- **THEN** it SHALL check for `mes_wip:data:parquet`
- **THEN** it SHALL NOT treat `mes_wip:data` or a double-prefixed derivative as the primary source of truth

### Requirement: WIP snapshot behavior SHALL define the baseline contract for realtime snapshot-plane datasets
The WIP cache contract SHALL act as the baseline for other realtime snapshot-plane datasets that are refreshed in the background and shared across workers through Redis.

#### Scenario: Snapshot-plane baseline
- **WHEN** another realtime dataset is normalized to the snapshot plane
- **THEN** it SHALL follow the same baseline pattern as WIP: background refresh, Redis-backed canonical payload, canonical metadata keys, and no legacy secondary payload representation

### Requirement: WIP snapshot retention SHALL remain decoupled from request-worker memory ownership
WIP freshness SHALL be governed by background refresh cadence and Redis retention, not by long-lived worker-owned full snapshot caches.

#### Scenario: Request reads WIP snapshot
- **WHEN** a worker serves a request using WIP data
- **THEN** it MAY parse the canonical Redis snapshot for request handling
- **THEN** the worker SHALL not become the long-lived authoritative owner of the full WIP snapshot in gunicorn process memory

#### Scenario: TTL and refresh alignment
- **WHEN** WIP uses a periodic background refresh cadence
- **THEN** the Redis retention window SHALL be longer than a single refresh interval
- **THEN** expiration SHALL act as a safety valve for stale data rather than the primary freshness mechanism
