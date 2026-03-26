## 1. Freshness Gate

- [x] 1.1 Add module-level `_SYNC_INTERVAL: int = 300` variable in `realtime_equipment_cache.py`
- [x] 1.2 In `init_realtime_equipment_cache()`, set `_SYNC_INTERVAL` from `config.get('EQUIPMENT_STATUS_SYNC_INTERVAL', 300)` before starting sync worker
- [x] 1.3 In `refresh_equipment_status_cache()`, after acquiring distributed lock and before Oracle query: if `force` is False, read Redis `equipment_status:meta:updated`, compute age, skip if age < `_SYNC_INTERVAL // 2`

## 2. Wait-First Sync Worker

- [x] 2.1 Rewrite `_sync_worker()` loop from `while not stop: refresh(); wait()` to `while not _STOP_EVENT.wait(timeout=interval): refresh()` so sync thread waits one full interval before first refresh

## 3. Tests

- [x] 3.1 Add test: `test_refresh_skips_when_recently_updated` — mock `meta:updated` as 10s ago, verify Oracle not called
- [x] 3.2 Add test: `test_refresh_proceeds_when_stale` — mock `meta:updated` as 200s ago, verify Oracle called
- [x] 3.3 Add test: `test_refresh_proceeds_when_force` — set `meta:updated` as 10s ago with `force=True`, verify Oracle called
- [x] 3.4 Add test: `test_sync_worker_waits_before_first_refresh` — verify sync worker does not call refresh immediately on start
- [x] 3.5 Run `python -m pytest tests/test_realtime_equipment_cache.py -x -q` — existing + new tests pass
- [x] 3.6 Run `python -m pytest tests/ -x -q` — full test suite pass
