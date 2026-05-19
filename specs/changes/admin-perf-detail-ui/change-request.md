# Change Request

## Original Request

admin dashboard performance-detail 頁面顯示 Redis eviction/slowlog 與 DuckDB 記憶體/temp 狀態新欄位。

Context: `fix-admin-dashboard` extended `/admin/api/performance-detail` with 6 new fields:
- `data.redis.evicted_keys` (int|null)
- `data.redis.expired_keys` (int|null)
- `data.redis.mem_fragmentation_ratio` (float|null)
- `data.redis.slowlog` (array of {id, duration_us, command}|null, top-5)
- `data.duckdb.temp_dir_bytes` (int|null)
- `data.duckdb.memory_limit_state` ({memory_limit, threads, temp_dir, connection_ok}|null)

The admin-pages SPA performance-detail view must render these fields. Null values should display gracefully (e.g., "N/A" or "unavailable"). The backend change is already merged and CI passed.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
