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
The ProcessLevelCache instances for hold/resource/reject/yield-alert datasets SHALL use max_size=1 (was 3 for hold/resource/reject, 2 for yield-alert).

#### Scenario: hold_dataset_cache L1
- **GIVEN** `services/hold_dataset_cache.py` creates `ProcessLevelCache(ttl_seconds=900, max_size=N)`
- **THEN** N SHALL be 1

#### Scenario: resource_dataset_cache L1
- **GIVEN** `services/resource_dataset_cache.py` creates `ProcessLevelCache(ttl_seconds=900, max_size=N)`
- **THEN** N SHALL be 1

#### Scenario: reject_dataset_cache L1
- **GIVEN** `services/reject_dataset_cache.py` creates `ProcessLevelCache(ttl_seconds=900, max_size=N)`
- **THEN** N SHALL be 1

#### Scenario: yield_alert_dataset_cache L1
- **GIVEN** `services/yield_alert_dataset_cache.py` creates `ProcessLevelCache(max_size=N)`
- **THEN** N SHALL be 1

### Requirement: Admin API SHALL report spool namespace disk usage
The `/admin/api/performance-detail` response SHALL include a `spool_disk_usage` section listing each spool namespace directory with its file count and total size in bytes.

#### Scenario: Spool directories exist with data
- **WHEN** `GET /admin/api/performance-detail` is called and spool directories contain Parquet files
- **THEN** the response SHALL include `spool_disk_usage` as an array of objects with `namespace`, `file_count`, and `total_bytes` fields

#### Scenario: No spool data
- **WHEN** `GET /admin/api/performance-detail` is called and no spool directories exist
- **THEN** `spool_disk_usage` SHALL be an empty array

#### Scenario: Disk read error
- **WHEN** `os.scandir` fails on a spool directory
- **THEN** that namespace entry SHALL include `"error": "<message>"` instead of file_count/total_bytes

### Requirement: Admin API SHALL report Redis per-namespace memory estimate
The `/admin/api/performance-detail` response SHALL include a `redis_namespace_memory` section with sampled memory estimates for key namespaces.

#### Scenario: Redis MEMORY USAGE available
- **WHEN** `GET /admin/api/performance-detail` is called and Redis supports `MEMORY USAGE`
- **THEN** the response SHALL sample representative keys from namespaces (mes_wip, resource, equipment, reject, hold, yield_alert) and report estimated memory per namespace

#### Scenario: MEMORY USAGE command fails or times out
- **WHEN** `MEMORY USAGE` command fails or exceeds 500ms timeout per key
- **THEN** that namespace entry SHALL include `"error": "<message>"`
- **THEN** the endpoint SHALL NOT fail entirely

### Requirement: WIP cache observability SHALL report against the canonical Parquet key
Admin and diagnostics endpoints SHALL inspect the same canonical WIP Parquet key used by runtime read/write helpers so cache telemetry remains operationally interpretable.

#### Scenario: Admin API samples WIP namespace memory
- **WHEN** `/admin/api/performance-detail` estimates Redis memory for the `mes_wip` namespace
- **THEN** it SHALL sample the canonical `mes_wip:data:parquet` key
- **THEN** it SHALL NOT sample a double-prefixed or legacy JSON key as the representative WIP payload

#### Scenario: Runtime and observability compare the same WIP key
- **WHEN** operators compare runtime cache behavior with admin/health telemetry
- **THEN** both surfaces SHALL refer to the same canonical WIP Parquet key
- **THEN** discrepancies caused only by key naming drift SHALL NOT occur
