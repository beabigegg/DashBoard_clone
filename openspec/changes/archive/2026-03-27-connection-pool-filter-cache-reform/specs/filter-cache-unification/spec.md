## ADDED Requirements

### Requirement: Unified filter cache TTL
All filter caches SHALL use a 24-hour TTL. `CACHE_TTL_FILTER_GENERAL` SHALL be 86400 seconds.

#### Scenario: Filter cache uses 24hr TTL
- **WHEN** `filter_cache` (workcenter groups) writes to Redis
- **THEN** the TTL SHALL be 86400 seconds (24 hours)

#### Scenario: Resource cache uses 24hr TTL
- **WHEN** `resource_cache` (families/departments/locations) writes to Redis
- **THEN** the TTL SHALL be 86400 seconds (24 hours)

### Requirement: Resource statuses from constant
`query_resource_filter_options()` SHALL return status values from the `STATUS_CATEGORIES` constant instead of querying Oracle.

#### Scenario: Status filter uses constant
- **WHEN** `query_resource_filter_options()` is called
- **THEN** the statuses list SHALL be derived from `STATUS_CATEGORIES` keys in `constants.py`
- **AND** no Oracle query SHALL be executed for status values
- **AND** `sql/resource/distinct_statuses.sql` SHALL be removed

### Requirement: Cache updater manages all filter caches
`cache_updater` SHALL initialize and refresh all filter caches at startup and on a 24-hour cycle.

#### Scenario: Startup initialization sequence
- **WHEN** the application starts
- **THEN** `cache_updater` SHALL call init on: filter_cache, resource_cache, container_filter_cache, reason_filter_cache, scrap_exclusion_cache (in order)

#### Scenario: Daily refresh with distributed lock
- **WHEN** the 24-hour refresh cycle triggers
- **THEN** `cache_updater` SHALL acquire a Redis distributed lock per cache key before refreshing
- **AND** if the lock is held by another worker, the refresh SHALL be skipped

#### Scenario: Refresh failure isolation
- **WHEN** one cache refresh fails
- **THEN** other cache refreshes SHALL still proceed independently

### Requirement: Backward-compatible filter options API
`reject_history_service.get_filter_options()` SHALL accept but ignore date parameters to maintain backward compatibility with existing frontend code.

#### Scenario: Date params ignored gracefully
- **WHEN** `get_filter_options()` is called with start_date and end_date parameters
- **THEN** the function SHALL return cached filter options regardless of the date values
- **AND** no error SHALL be raised
