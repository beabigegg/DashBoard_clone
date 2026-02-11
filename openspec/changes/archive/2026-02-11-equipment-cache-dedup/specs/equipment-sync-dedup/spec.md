## ADDED Requirements

### Requirement: Equipment Sync Refresh SHALL Skip Redundant Oracle Queries Within Same Cycle
When multiple workers attempt to refresh the equipment status cache within the same sync cycle, only the first successful refresh SHALL query Oracle. Subsequent workers that acquire the distributed lock MUST check the freshness of the existing cache and skip the Oracle query if the cache was recently updated.

#### Scenario: Another worker already refreshed within current cycle
- **WHEN** a worker acquires the distributed lock and the `equipment_status:meta:updated` timestamp is less than half the sync interval old
- **THEN** the worker MUST release the lock without querying Oracle and return False

#### Scenario: No recent refresh exists
- **WHEN** a worker acquires the distributed lock and the `equipment_status:meta:updated` timestamp is older than half the sync interval (or missing)
- **THEN** the worker MUST proceed with the full Oracle query and cache update

#### Scenario: Force refresh bypasses freshness gate
- **WHEN** `refresh_equipment_status_cache(force=True)` is called
- **THEN** the freshness gate MUST be skipped and the Oracle query MUST proceed regardless of `meta:updated` age

### Requirement: Sync Worker SHALL Not Duplicate Init Refresh
The background sync worker thread MUST wait for one full sync interval before its first refresh attempt, since `init_realtime_equipment_cache()` already performs an initial refresh at startup.

#### Scenario: Sync worker startup after init
- **WHEN** the sync worker thread starts after `init_realtime_equipment_cache()` completes the initial refresh
- **THEN** the worker MUST wait for the configured interval before attempting its first refresh

#### Scenario: Stop signal during wait
- **WHEN** a stop signal is received while the sync worker is waiting
- **THEN** the worker MUST exit without performing a refresh
