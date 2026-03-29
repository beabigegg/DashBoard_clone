## 1. WIP Cache Parquet-Only

- [x] 1.1 Remove JSON write path in `core/cache_updater.py` — stop writing/renaming `mes_wip:data` key, keep only `mes_wip:data:parquet` write
- [x] 1.2 Add legacy JSON key cleanup in `core/cache_updater.py` — delete `mes_wip:data` if exists on first update cycle, with INFO log
- [x] 1.3 Remove JSON fallback read in `core/cache.py` `get_cached_wip_data()` — remove lines 481-486 JSON branch, return None when Parquet key missing
- [ ] 1.4 Verify WIP cache round-trip — confirm updater writes Parquet, reader reads Parquet, WIP overview/detail pages work correctly

## 2. Dataset L1 max_size Reduction

- [x] 2.1 Change `reject_dataset_cache.py` `_CACHE_MAX_SIZE` from 3 to 1
- [x] 2.2 Change `hold_dataset_cache.py` `_CACHE_MAX_SIZE` from 3 to 1
- [x] 2.3 Change `resource_dataset_cache.py` `_CACHE_MAX_SIZE` from 3 to 1
- [x] 2.4 Change `yield_alert_dataset_cache.py` default max_size from 2 to 1
- [ ] 2.5 Verify process cache stats via `/admin/api/performance-detail` show max_size=1 for all dataset caches

## 3. Resource / Equipment Cache Redis TTL

- [x] 3.1 Add `EX 300` to `resource_cache.py` Redis pipeline write (lines 587-592) for all data keys
- [x] 3.2 Add `EX 300` to `realtime_equipment_cache.py` Redis pipeline write (lines 357-364) for all data keys
- [ ] 3.3 Verify resource status page and equipment status page still work with TTL in place
- [ ] 3.4 Verify keys expire after 300s when updater is stopped (manual test or integration test)

## 4. Telemetry — Spool Disk Usage

- [x] 4.1 Add spool namespace disk usage collection function (scan spool directories, count files, sum sizes per namespace)
- [x] 4.2 Integrate spool disk usage into `/admin/api/performance-detail` response as `spool_disk_usage` array
- [x] 4.3 Handle `os.scandir` errors gracefully (per-namespace error field, endpoint does not fail)

## 5. Telemetry — Redis Per-Namespace Memory Estimate

- [x] 5.1 Add Redis `MEMORY USAGE` sampling function (sample representative keys from mes_wip, resource, equipment, reject, hold, yield_alert namespaces)
- [x] 5.2 Integrate Redis memory estimate into `/admin/api/performance-detail` response as `redis_namespace_memory` array
- [x] 5.3 Add timeout protection (500ms per key) and error handling for MEMORY USAGE command

## 6. Validation

- [x] 6.1 Run existing test suite (`pytest tests/ -v`) — confirm no regressions
- [ ] 6.2 Verify `/health` and `/health/deep` endpoints still report correct cache status
- [ ] 6.3 Spot-check gunicorn RSS via admin API before/after deployment to confirm memory reduction
