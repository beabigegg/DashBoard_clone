## Context

Hold-history fires 4 independent Oracle queries per user interaction (trend, reason-pareto, duration, list), all against `DW_MES_HOLDRELEASEHISTORY` with the same date range + hold_type filter. Resource-history fires 4 Oracle queries (3 parallel in summary + 1 detail), all against `DW_MES_RESOURCESTATUS_SHIFT` with the same filter set. Both pages re-query Oracle on every filter change or pagination.

Reject-history already solved this problem with a two-phase dataset cache pattern (`reject_dataset_cache.py`): one Oracle query caches the full fact set, subsequent views are derived from cache via pandas. This change applies the same pattern to hold-history and resource-history.

## Goals / Non-Goals

**Goals:**
- Reduce Oracle queries from 4 per interaction to 1 per user session (per filter combination)
- Same cache infrastructure as reject-history: L1 (ProcessLevelCache) + L2 (Redis parquet/base64), 15-minute TTL
- Same API pattern: POST /query (primary) + GET /view (supplementary, from cache)
- Maintain all existing UI functionality — same charts, tables, filters, pagination
- Frontend adopts queryId-based two-phase flow

**Non-Goals:**
- Changing the SQL queries themselves (same table, same WHERE logic)
- Adding new visualizations or metrics
- Modifying other pages (reject-history, query-tool, etc.)
- Changing the department endpoint on hold-history (it has unique person-level expansion logic that benefits from its own query — we keep it as a separate call)

## Decisions

### D1: Follow reject_dataset_cache.py architecture exactly

**Decision**: Create `hold_dataset_cache.py` and `resource_dataset_cache.py` following the same module structure:
- `_make_query_id()` — SHA256 hash of primary params
- `_redis_store_df()` / `_redis_load_df()` — parquet/base64 encoding
- `_get_cached_df()` / `_store_df()` — L1 → L2 read-through
- `execute_primary_query()` — Oracle query + cache + derive initial view
- `apply_view()` — read cache + filter + re-derive

**Rationale**: Proven pattern, consistent codebase, shared infrastructure. Alternatives (custom cache format, separate cache layers) add complexity for no benefit.

### D2: Hold-history primary query scope

**Decision**: The primary query fetches ALL hold/release records for the date range (all hold_types). Trend, reason-pareto, duration, and list are all derived from this single cached DataFrame. Department remains a separate API call.

**Rationale**: Trend data already contains all 3 hold_type variants in one query. By caching the raw facts (not pre-aggregated), we can switch hold_type views instantly from cache. Department has unique person-level JOINs and GROUP BY logic that doesn't fit the "filter from flat DataFrame" pattern cleanly.

**Alternatives considered**:
- Cache per hold_type: wastes 3x cache memory, still requires Oracle for type switching
- Include department in cache: complex person-level aggregation doesn't map well to flat DataFrame filtering

### D3: Resource-history primary query scope

**Decision**: The primary query fetches ALL shift-status records for the date range and resource filter combination. KPI, trend, heatmap, workcenter comparison, and detail are all derived from this single cached DataFrame.

**Rationale**: All 4 current queries (kpi, trend, heatmap, detail) use the same base WHERE clause against the same table. The aggregations (GROUP BY date for trend, GROUP BY workcenter×date for heatmap, etc.) are simple pandas operations on the cached raw data.

### D4: Cache TTL = 15 minutes, same as reject-history

**Decision**: Use `_CACHE_TTL = 900` (15 min) for both modules, with L1 `max_size = 8`.

**Rationale**: Matches reject-history. 15 minutes covers typical analysis sessions. Users who need fresh data can re-query (which replaces the cache). Hold-history's existing 12h Redis cache for trend data is more aggressive but stale — 15 minutes is a better balance.

### D5: API contract — POST /query + GET /view

**Decision**: Both pages switch to:
- `POST /api/hold-history/query` → primary query, returns `query_id` + initial view (trend, reason, duration, list page 1)
- `GET /api/hold-history/view` → supplementary filter/pagination from cache
- `POST /api/resource/history/query` → primary query, returns `query_id` + initial view (summary + detail page 1)
- `GET /api/resource/history/view` → supplementary filter/pagination from cache

Old GET endpoints (trend, reason-pareto, duration, list, summary, detail) are removed.

**Rationale**: Same pattern as reject-history. POST for primary (sends filter params in body), GET for view (sends query_id + supplementary params).

### D6: Frontend queryId-based flow

**Decision**: Both `App.vue` files adopt the two-phase pattern:
1. User clicks "查詢" → `POST /query` → store `queryId`
2. Filter change / pagination → `GET /view?query_id=...&filters...` (no Oracle)
3. Cache expired (HTTP 410) → auto re-execute primary query

**Rationale**: Proven pattern from reject-history. Keeps UI responsive after initial query.

## Risks / Trade-offs

- **[Memory]** Caching full DataFrames in L1 (per-worker) uses more RAM than current approach → Mitigated by `max_size=8` LRU eviction (same as reject-history, works well in production)
- **[Staleness]** 15-min TTL means data could be up to 15 minutes old during an analysis session → Acceptable for historical analysis; user can re-query for fresh data
- **[Department endpoint]** Hold-history department still makes a separate Oracle call → Acceptable trade-off; person-level aggregation doesn't fit flat DataFrame model. Could be addressed later.
- **[Breaking API]** Old GET endpoints removed → No external consumers; frontend is the only client
- **[Redis dependency]** If Redis is down, only L1 cache works (per-worker, not cross-worker) → Same behavior as reject-history; L1 still provides 15-min cache per worker
