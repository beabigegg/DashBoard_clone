## MODIFIED Requirements

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

## ADDED Requirements

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
