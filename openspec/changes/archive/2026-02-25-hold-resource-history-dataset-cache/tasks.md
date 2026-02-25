## 1. Hold-History Dataset Cache (Backend)

- [x] 1.1 Create `src/mes_dashboard/services/hold_dataset_cache.py` — module scaffolding: imports, logger, ProcessLevelCache (TTL=900, max_size=8), Redis namespace `hold_dataset`, `_make_query_id()`, `_redis_store_df()` / `_redis_load_df()`, `_get_cached_df()` / `_store_df()`
- [x] 1.2 Implement `execute_primary_query(start_date, end_date)` — single Oracle query fetching ALL hold/release facts for date range (all hold_types), cache result, derive initial view (trend, reason_pareto, duration, list page 1) using existing service functions
- [x] 1.3 Implement `apply_view(query_id, hold_type, reason, page, per_page)` — read cached DF, apply hold_type filter, derive trend + reason_pareto + duration + paginated list from filtered DF; return 410 on cache miss
- [x] 1.4 Implement in-memory derivation helpers: `_derive_trend(df, hold_type)`, `_derive_reason_pareto(df, hold_type)`, `_derive_duration(df, hold_type)`, `_derive_list(df, hold_type, reason, page, per_page)` — reuse shift boundary and hold_type classification logic from `hold_history_service.py`

## 2. Hold-History Routes (Backend)

- [x] 2.1 Add `POST /api/hold-history/query` route — parse body `{ start_date, end_date, hold_type }`, call `hold_dataset_cache.execute_primary_query()`, return `{ query_id, trend, reason_pareto, duration, list, summary }`
- [x] 2.2 Add `GET /api/hold-history/view` route — parse query params `query_id, hold_type, reason, page, per_page`, call `hold_dataset_cache.apply_view()`, return derived views or 410 on cache miss
- [x] 2.3 Remove old GET endpoints: `/api/hold-history/trend`, `/api/hold-history/reason-pareto`, `/api/hold-history/duration`, `/api/hold-history/list` — keep page route and department route (if exists)

## 3. Hold-History Frontend

- [x] 3.1 Rewrite `frontend/src/hold-history/App.vue` — two-phase flow: initial load calls `POST /query` → store queryId; hold_type change, reason filter, pagination call `GET /view?query_id=...`; cache expired (410) → auto re-execute primary query
- [x] 3.2 Derive summary KPI cards from trend data returned by query/view response (no separate API call)
- [x] 3.3 Update all chart components to consume data from the unified query/view response instead of individual API results

## 4. Resource-History Dataset Cache (Backend)

- [x] 4.1 Create `src/mes_dashboard/services/resource_dataset_cache.py` — module scaffolding: same cache infrastructure (TTL=900, max_size=8), Redis namespace `resource_dataset`, query ID helpers, L1+L2 cache read/write
- [x] 4.2 Implement `execute_primary_query(params)` — single Oracle query fetching ALL shift-status records for date range + resource filters, cache result, derive initial view (summary: kpi + trend + heatmap + comparison, detail page 1) using existing service functions
- [x] 4.3 Implement `apply_view(query_id, granularity, page, per_page)` — read cached DF, derive summary + paginated detail; return 410 on cache miss
- [x] 4.4 Implement in-memory derivation helpers: `_derive_kpi(df)`, `_derive_trend(df, granularity)`, `_derive_heatmap(df)`, `_derive_comparison(df)`, `_derive_detail(df, page, per_page)` — reuse aggregation logic from `resource_history_service.py`

## 5. Resource-History Routes (Backend)

- [x] 5.1 Add `POST /api/resource/history/query` route — parse body with date range, granularity, resource filters, call `resource_dataset_cache.execute_primary_query()`, return `{ query_id, summary, detail }`
- [x] 5.2 Add `GET /api/resource/history/view` route — parse query params `query_id, granularity, page, per_page`, call `resource_dataset_cache.apply_view()`, return derived views or 410
- [x] 5.3 Remove old GET endpoints: `/api/resource/history/summary`, `/api/resource/history/detail` — keep `/options` and `/export` endpoints

## 6. Resource-History Frontend

- [x] 6.1 Rewrite `frontend/src/resource-history/App.vue` — two-phase flow: query button calls `POST /query` → store queryId; filter changes call `GET /view?query_id=...`; cache expired → auto re-execute
- [x] 6.2 Update `executeCommittedQuery()` to use POST /query instead of parallel GET summary + GET detail
- [x] 6.3 Update all chart/table components to consume data from unified query/view response

## 7. Verification

- [x] 7.1 Run `python -m pytest tests/ -v` — no new test failures
- [x] 7.2 Run `cd frontend && npm run build` — frontend builds successfully
