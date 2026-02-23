## 1. Backend — Cache Telemetry Infrastructure

- [x] 1.1 Add `stats()` method to `ProcessLevelCache` in `core/cache.py` (returns entries/max_size/ttl_seconds with lock)
- [x] 1.2 Add `_PROCESS_CACHE_REGISTRY`, `register_process_cache()`, and `get_all_process_cache_stats()` to `core/cache.py`
- [x] 1.3 Register `_wip_df_cache` in `core/cache.py`
- [x] 1.4 Add `stats()` + `register_process_cache()` to `services/resource_cache.py`
- [x] 1.5 Add `stats()` + `register_process_cache()` to `services/realtime_equipment_cache.py`
- [x] 1.6 Add `register_process_cache()` to `services/reject_dataset_cache.py`

## 2. Backend — Direct Connection Counter

- [x] 2.1 Add `_DIRECT_CONN_COUNTER`, `_DIRECT_CONN_LOCK`, and `get_direct_connection_count()` to `core/database.py`
- [x] 2.2 Increment counter in `get_db_connection()` and `read_sql_df_slow()` after successful connection creation

## 3. Backend — Performance Detail API

- [x] 3.1 Add `GET /admin/api/performance-detail` endpoint in `routes/admin_routes.py` returning redis, process_caches, route_cache, db_pool, and direct_connections sections
- [x] 3.2 Implement Redis INFO + SCAN namespace key distribution (data, route_cache, equipment_status, reject_dataset, meta, lock, scrap_exclusion) with graceful degradation when Redis is disabled

## 4. Frontend — Page Scaffolding

- [x] 4.1 Create `frontend/src/admin-performance/index.html` and `main.js` (standard Vue SPA entry)
- [x] 4.2 Register `admin-performance` entry in `vite.config.js`
- [x] 4.3 Add `cp` command for `admin-performance.html` in `package.json` build script

## 5. Frontend — Reusable Components

- [x] 5.1 Create `GaugeBar.vue` — horizontal gauge bar with label, value, max, and color threshold props
- [x] 5.2 Create `StatCard.vue` — mini card with numeric value, label, and optional unit/icon
- [x] 5.3 Create `StatusDot.vue` — colored dot indicator (healthy/degraded/error/disabled) with label

## 6. Frontend — App.vue Main Dashboard

- [x] 6.1 Implement data fetching layer: `loadSystemStatus()`, `loadMetrics()`, `loadPerformanceDetail()`, `loadLogs()`, `loadWorkerStatus()` with `Promise.all` parallel fetch and `useAutoRefresh` (30s)
- [x] 6.2 Build header section with gradient background, title, auto-refresh toggle, and manual refresh button
- [x] 6.3 Build status cards section (Database / Redis / Circuit Breaker / Worker PID) using StatusDot
- [x] 6.4 Build query performance panel with P50/P95/P99 stat cards and ECharts latency distribution chart
- [x] 6.5 Build Redis cache detail panel with memory GaugeBar, hit rate, client count, peak memory, and namespace key distribution table
- [x] 6.6 Build memory cache panel with ProcessLevelCache grid cards (entries/max gauge + TTL) and route cache telemetry (L1/L2 hit rate, miss rate, total reads)
- [x] 6.7 Build connection pool panel with saturation GaugeBar and stat card grid (checked_out, checked_in, overflow, max_capacity, pool_size, pool_recycle, pool_timeout, direct connections)
- [x] 6.8 Build worker control panel with PID/uptime/cooldown display, restart button, and confirmation modal
- [x] 6.9 Build system logs panel with level filter, text search, pagination, and log clearing
- [x] 6.10 Create `style.css` with all panel, grid, gauge, card, and responsive layout styles

## 7. Route Integration

- [x] 7.1 Change `/admin/performance` route handler in `admin_routes.py` from `render_template` to `send_from_directory` serving the Vue SPA
- [x] 7.2 Update `routeContracts.js`: change renderMode to `'native'`, rollbackStrategy to `'fallback_to_legacy_route'`, compatibilityPolicy to `'redirect_to_shell_when_spa_enabled'`

## 8. Verification (Phase 1)

- [x] 8.1 Run `cd frontend && npx vite build` — confirm no compilation errors and `admin-performance.html` is produced
- [x] 8.2 Verify all dashboard panels render correctly with live data after service restart

## 9. Backend — Metrics History Store

- [x] 9.1 Create `core/metrics_history.py` with `MetricsHistoryStore` class (SQLite schema, thread-local connections, write_lock, write_snapshot, query_snapshots, cleanup)
- [x] 9.2 Add `MetricsHistoryCollector` class (daemon thread, configurable interval, collect pool/redis/route_cache/latency)
- [x] 9.3 Add module-level `get_metrics_history_store()`, `start_metrics_history(app)`, `stop_metrics_history()` functions

## 10. Backend — Lifecycle Integration

- [x] 10.1 Call `start_metrics_history(app)` in `app.py` after other background services
- [x] 10.2 Call `stop_metrics_history()` in `_shutdown_runtime_resources()` in `app.py`

## 11. Backend — Performance History API

- [x] 11.1 Add `GET /admin/api/performance-history` endpoint in `admin_routes.py` (minutes param, clamped 1-180, returns snapshots array)

## 12. Frontend — Trend Charts

- [x] 12.1 Create `TrendChart.vue` component using vue-echarts VChart (line/area chart, dual yAxis support, time labels, autoresize)
- [x] 12.2 Add `loadPerformanceHistory()` fetch to `App.vue` and integrate into `refreshAll()`
- [x] 12.3 Add 4 TrendChart panels to `App.vue` template (pool saturation, query latency, Redis memory, cache hit rates)
- [x] 12.4 Add trend chart styles to `style.css`

## 13. Verification (Phase 2)

- [x] 13.1 Run `cd frontend && npm run build` — confirm no compilation errors
- [x] 13.2 Verify trend charts render with historical data after service restart + 60s collection
