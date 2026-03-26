### Requirement: Cache Telemetry MUST be Queryable for Operations
The system MUST provide cache telemetry suitable for operations diagnostics, including materialized Pareto cache behavior for reject-history workloads.

#### Scenario: Telemetry inspection
- **WHEN** operators request deep health status
- **THEN** cache-related metrics/state SHALL be present and interpretable for troubleshooting

#### Scenario: Materialized Pareto telemetry visibility
- **WHEN** materialized Pareto cache is enabled
- **THEN** telemetry SHALL expose at least hit count/rate, miss count/rate, build count, build failure count, and fallback count
- **THEN** telemetry SHALL expose latest snapshot freshness indicators and aggregate payload size indicators

### Requirement: metrics_history SHALL track cache hit/miss counts
The `MetricsHistoryCollector` SHALL include `cache_hit_count` and `cache_miss_count` columns in each 30-second snapshot.

#### Scenario: Hit/miss counts from route cache
- **WHEN** the collector writes a snapshot
- **THEN** it SHALL read cumulative hit and miss counters from the route-level cache (LayeredCache / MemoryTTLCache)
- **THEN** the `cache_hit_count` and `cache_miss_count` columns SHALL reflect counts since last snapshot (delta, not cumulative)

#### Scenario: Schema migration
- **WHEN** the metrics_history SQLite database lacks `cache_hit_count` or `cache_miss_count` columns
- **THEN** the collector SHALL ALTER TABLE to add them (following existing `_MIGRATION_COLUMNS` pattern)

### Requirement: Dead worker alert condition
The system SHALL emit a WARNING log when RQ queue has pending jobs but no workers are available.

#### Scenario: Dead worker detection
- **WHEN** the metrics_history collector observes `rq_queue_depth > 0` AND `rq_workers_total = 0`
- **THEN** a WARNING log SHALL be emitted: "RQ dead worker alert: queue_depth={n} but no workers available"
- **THEN** this condition SHALL be recorded in the snapshot for dashboard visibility

#### Scenario: Normal operation
- **WHEN** `rq_workers_total > 0` or `rq_queue_depth = 0`
- **THEN** no alert SHALL be emitted

### Requirement: Pareto materialization fallback reasons SHALL be operationally classifiable
Telemetry MUST classify fallback outcomes with stable reason codes so repeated degradations can be monitored and alerted.

#### Scenario: Snapshot miss fallback reason
- **WHEN** request falls back because no snapshot exists
- **THEN** telemetry SHALL record a stable reason code for snapshot miss

#### Scenario: Snapshot stale fallback reason
- **WHEN** request falls back because snapshot fails freshness/version checks
- **THEN** telemetry SHALL record a stable reason code for stale/incompatible snapshot

#### Scenario: Build failure fallback reason
- **WHEN** request falls back because materialization build failed
- **THEN** telemetry SHALL record a stable reason code for build failure

### Requirement: MemoryTTLCache SHALL enforce max_size with LRU eviction
The `MemoryTTLCache` in `core/cache.py` SHALL accept a `max_size` parameter (default 256) and evict the least-recently-used entry when the limit is reached.

#### Scenario: Cache exceeds max_size
- **WHEN** a `set()` call would exceed `max_size` entries
- **THEN** the oldest (least recently accessed) non-expired entry SHALL be evicted before insertion

#### Scenario: Default max_size
- **WHEN** `MemoryTTLCache()` is constructed without explicit `max_size`
- **THEN** max_size SHALL default to 256

### Requirement: Dataset L1 cache max_size SHALL be reduced
The ProcessLevelCache instances for hold/resource/reject/yield-alert datasets SHALL use max_size=3 (was 8).

#### Scenario: hold_dataset_cache L1
- **GIVEN** `services/hold_dataset_cache.py` creates `ProcessLevelCache(ttl_seconds=900, max_size=N)`
- **THEN** N SHALL be 3

#### Scenario: resource_dataset_cache L1
- **GIVEN** `services/resource_dataset_cache.py` creates `ProcessLevelCache(ttl_seconds=900, max_size=N)`
- **THEN** N SHALL be 3

#### Scenario: reject_dataset_cache L1
- **GIVEN** `services/reject_dataset_cache.py` creates `ProcessLevelCache(ttl_seconds=900, max_size=N)`
- **THEN** N SHALL be 3

#### Scenario: yield_alert_dataset_cache L1
- **GIVEN** `services/yield_alert_dataset_cache.py` creates `ProcessLevelCache(max_size=N)`
- **THEN** N SHALL be 2
