## ADDED Requirements

### Requirement: ProcessLevelCache stats method
Every `ProcessLevelCache` instance SHALL expose a `stats()` method that returns a dict containing `entries` (live entries count), `max_size`, and `ttl_seconds`.

#### Scenario: Stats on active cache
- **WHEN** `stats()` is called on a ProcessLevelCache with 5 live entries (max_size=32, ttl=30s)
- **THEN** it SHALL return `{"entries": 5, "max_size": 32, "ttl_seconds": 30}`

#### Scenario: Stats with expired entries
- **WHEN** `stats()` is called and some entries have exceeded TTL
- **THEN** `entries` SHALL only count entries where `now - timestamp <= ttl`

#### Scenario: Thread safety
- **WHEN** `stats()` is called concurrently with cache writes
- **THEN** it SHALL acquire the cache lock and return consistent data without races

### Requirement: ProcessLevelCache global registry
The system SHALL maintain a module-level registry in `core/cache.py` that maps cache names to `(description, instance)` tuples. Services SHALL register their cache instances at module load time via `register_process_cache(name, instance, description)`.

#### Scenario: Register and retrieve all caches
- **WHEN** multiple services register their caches and `get_all_process_cache_stats()` is called
- **THEN** it SHALL return a dict of `{name: {entries, max_size, ttl_seconds, description}}` for all registered caches

#### Scenario: Cache not registered
- **WHEN** a service's ProcessLevelCache is not registered
- **THEN** it SHALL NOT appear in `get_all_process_cache_stats()` output

### Requirement: Performance detail API endpoint
The system SHALL expose `GET /admin/api/performance-detail` that returns a JSON object with sections: `redis`, `process_caches`, `route_cache`, `db_pool`, and `direct_connections`.

#### Scenario: All systems available
- **WHEN** the API is called and all subsystems are healthy
- **THEN** it SHALL return all 5 sections with current telemetry data

#### Scenario: Redis disabled
- **WHEN** Redis is disabled (`REDIS_ENABLED=false`)
- **THEN** the `redis` section SHALL be `null` or contain `{"enabled": false}`, and other sections SHALL still return normally

### Requirement: Redis namespace key distribution
The performance-detail API SHALL scan Redis keys by namespace prefix and return key counts per namespace. Namespaces SHALL include: `data`, `route_cache`, `equipment_status`, `reject_dataset`, `meta`, `lock`, `scrap_exclusion`.

#### Scenario: Keys exist across namespaces
- **WHEN** Redis contains keys across multiple namespaces
- **THEN** the `redis.namespaces` array SHALL list each namespace with its `name` and `key_count`

#### Scenario: SCAN safety
- **WHEN** scanning Redis keys
- **THEN** the system SHALL use `SCAN` (not `KEYS`) to avoid blocking Redis

### Requirement: Route cache telemetry in performance detail
The performance-detail API SHALL include route cache telemetry from `get_route_cache_status()`, providing `mode`, `l1_size`, `l1_hit_rate`, `l2_hit_rate`, `miss_rate`, and `reads_total`.

#### Scenario: LayeredCache active
- **WHEN** route cache is in layered mode
- **THEN** the `route_cache` section SHALL include L1 and L2 hit rates from telemetry
