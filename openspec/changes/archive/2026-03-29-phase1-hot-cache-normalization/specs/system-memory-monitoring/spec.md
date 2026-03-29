## ADDED Requirements

### Requirement: Admin performance detail SHALL include L1 cache entry count per domain
The `/admin/api/performance-detail` response `process_cache` section SHALL include the current entry count and max_size for each registered ProcessLevelCache, enabling operators to verify that max_size reduction is effective.

#### Scenario: After max_size reduction deployment
- **WHEN** `GET /admin/api/performance-detail` is called after Phase 1 deployment
- **THEN** each process cache entry SHALL show `max_size: 1` for dataset caches (reject, hold, resource, yield-alert)
- **THEN** each process cache entry SHALL show `current_entries` as 0 or 1
